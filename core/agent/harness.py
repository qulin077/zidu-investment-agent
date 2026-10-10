"""Durable, bounded outer agent loop.

The model/router chooses actions; the registry executes them; the harness only
owns state, policy boundaries, observations, and stopping.  It never embeds
investment facts or business-specific workflow code.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from core.agent.store import dumps, loads
from core.agent.tool_registry import ToolCall, ToolRegistry
from core.research.store import _ids, now_iso
from core.store import Store

# Emergency guard for the *outer* tool loop, not a research-depth limit.
# Research skills own their evidence-convergence loop and return a terminal
# deliverable when that loop has settled.
MAX_AGENT_STEPS = 12


@dataclass(frozen=True)
class AgentAction:
    kind: str
    name: str
    arguments: dict


@dataclass
class RuntimeResult:
    outcome: dict
    turn_id: str
    steps_used: int
    stop_reason: str
    activities: list


def action_from_route(route: dict, message: str) -> AgentAction:
    mode = (route.get("mode") or "CHAT").upper()
    name = route.get("skill") or "conversation"
    if mode == "SKILL" and (name == "market-scan" or route.get("need_market_data")):
        return AgentAction(
            kind="CALL_TOOL",
            name="market-data-status",
            arguments={
                "message": message,
                "route": route,
                "target_tool": name,
                "confirmed": False,
            },
        )
    return AgentAction(
        kind="CALL_TOOL" if mode == "SKILL" and name != "conversation" else "CHAT",
        name=name,
        arguments={"message": message, "route": route, "confirmed": _explicit_confirmation(route, message)},
    )


class AgentRuntime:
    def __init__(
        self,
        store: Store,
        registry: ToolRegistry,
        *,
        session_id: str,
        event_sink: Optional[Callable[[dict], object]] = None,
        planner=None,
        max_steps: int = MAX_AGENT_STEPS,
    ):
        self.store = store
        self.registry = registry
        self.session_id = session_id
        self.event_sink = event_sink
        self.planner = planner
        self.max_steps = max(1, min(int(max_steps), MAX_AGENT_STEPS))

    def run(self, message: str, route: dict) -> RuntimeResult:
        turn_id = self._start_turn(message, route)
        activities = []
        action = action_from_route(route, message)
        outcome = {}
        stop_reason = ""
        steps_used = 0
        executed = []
        outcomes = []

        for step in range(1, self.max_steps + 1):
            steps_used = step
            self._add_item(turn_id, step * 2 - 1, "ACTION", action.name, "running", {
                "kind": action.kind,
                "arguments": _safe_arguments(action.arguments),
            })
            emitted = self._emit({
                "type": "AGENT_ACTION", "status": "running",
                "summary": "Agent 调用 {0}".format(action.name),
                "metadata": {"turn_id": turn_id, "step": step, "tool": action.name},
            })
            if emitted:
                activities.append(emitted)

            try:
                outcome = self.registry.execute(ToolCall(action.name, action.arguments))
            except Exception:  # The turn must settle even when a workflow crashes.
                outcome = {
                    "ok": False, "status": "FAILED", "error_code": "TOOL_EXECUTION_FAILED",
                    "answer": "这个工具执行失败了，本轮已经安全停止，没有继续写入。",
                }
            outcome["_runtime_tool"] = action.name
            outcomes.append(dict(outcome))
            observation_status = outcome.get("status") or ("COMPLETED" if outcome.get("ok", True) else "FAILED")
            self._add_item(turn_id, step * 2, "OBSERVATION", action.name, observation_status, _observation(outcome))
            emitted = self._emit({
                "type": "AGENT_OBSERVATION",
                "status": "ok" if outcome.get("ok", True) else "gap",
                "summary": "{0}：{1}".format(action.name, _observation_summary(outcome)),
                "metadata": {"turn_id": turn_id, "step": step, "tool": action.name},
            })
            if emitted:
                activities.append(emitted)

            executed.append({
                "tool": action.name,
                "message": action.arguments.get("message") or "",
                "status": observation_status,
            })
            next_action = _next_action(outcome)
            if outcome.get("runtime_terminal"):
                next_action = None
                stop_reason = "DELIVERABLE_READY"
            # Freshness and permission prerequisites are deterministic policy
            # gates.  After a business tool, the model gets control again and
            # may finish or select another tool from the registry.
            if (
                self.planner is not None
                and not outcome.get("runtime_terminal")
                and action.name not in ("conversation", "market-data-status", "market-data-refresh")
            ):
                decision = self.planner.after_observation(
                    message=message,
                    route=route,
                    step=step,
                    action=action,
                    observation=_observation(outcome),
                    tools=self.registry.descriptions(include_internal=False),
                    executed=executed,
                )
                if decision.get("decision") == "FINISH":
                    next_action = None
                elif decision.get("decision") == "CALL_TOOL":
                    candidate = decision.get("action")
                    # A model may select market-scan after another tool.  It
                    # still has to pass the deterministic freshness gate.
                    if candidate is not None and candidate.name == "market-scan":
                        candidate = action_from_route(
                            candidate.arguments.get("route") or {
                                "mode": "SKILL", "skill": "market-scan",
                                "intent": "MARKET_SCAN", "need_market_data": True,
                            },
                            candidate.arguments.get("message") or message,
                        )
                    signature = (candidate.name, candidate.arguments.get("message") or "") if candidate else None
                    prior = {(row["tool"], row["message"]) for row in executed}
                    if candidate is not None and signature not in prior:
                        next_action = candidate
                    elif candidate is not None:
                        stop_reason = "REPEATED_ACTION_BLOCKED"
                        next_action = None
            if not next_action:
                if stop_reason in ("REPEATED_ACTION_BLOCKED", "DELIVERABLE_READY"):
                    pass
                elif observation_status == "AWAITING_APPROVAL":
                    stop_reason = "AWAITING_APPROVAL"
                elif not outcome.get("ok", True):
                    stop_reason = "TOOL_FAILED"
                else:
                    stop_reason = "TOOL_COMPLETED"
                break
            action = next_action
        else:
            stop_reason = "MAX_STEPS"
            outcome = dict(outcome)
            outcome.setdefault("answer", "这轮已经达到 Agent 步数上限，剩余动作没有继续执行。")

        outcome = _select_deliverable(outcomes, outcome)
        self._finish_turn(turn_id, outcome, steps_used, stop_reason)
        return RuntimeResult(outcome, turn_id, steps_used, stop_reason, activities)

    def _start_turn(self, message: str, route: dict) -> str:
        stamp = now_iso()
        with self.store.connect() as conn:
            turn_id = _ids(conn, "agent_turn", "AT", 1)[0]
            conn.execute(
                """INSERT INTO agent_turn
                   (id, session_id, status, input_text, route_json, max_steps, steps_used,
                    stop_reason, started_at, finished_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (turn_id, self.session_id, "RUNNING", message, dumps(route), self.max_steps, 0, "", stamp, ""),
            )
        return turn_id

    def _add_item(self, turn_id: str, seq: int, item_type: str, name: str, status: str, payload: dict) -> None:
        with self.store.connect() as conn:
            item_id = _ids(conn, "agent_item", "AI", 1)[0]
            conn.execute(
                """INSERT INTO agent_item
                   (id, turn_id, session_id, seq, item_type, name, status, payload_json, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (item_id, turn_id, self.session_id, seq, item_type, name, status, dumps(payload), now_iso()),
            )

    def _finish_turn(self, turn_id: str, outcome: dict, steps: int, stop_reason: str) -> None:
        status = "COMPLETED" if outcome.get("ok", True) else outcome.get("status") or "FAILED"
        with self.store.connect() as conn:
            conn.execute(
                """UPDATE agent_turn
                   SET status = ?, steps_used = ?, stop_reason = ?, finished_at = ?
                   WHERE id = ?""",
                (status, steps, stop_reason, now_iso(), turn_id),
            )

    def _emit(self, event: dict):
        return self.event_sink(event) if self.event_sink is not None else None


def _explicit_confirmation(route: dict, message: str) -> bool:
    intent = route.get("intent") or ""
    compact = "".join((message or "").split())
    if intent == "CONFIRM_DECISION":
        return compact in ("确认", "确认保存", "保存", "就这样", "没问题")
    if intent == "CANCEL_DECISION":
        return compact in ("取消", "不记了", "算了", "放弃")
    return False


def _safe_arguments(arguments: dict) -> dict:
    route = arguments.get("route") or {}
    return {
        "message": (arguments.get("message") or "")[:500],
        "intent": route.get("intent") or "",
        "skill": route.get("skill") or "",
        "entity": route.get("entity") or {},
        "confirmed": bool(arguments.get("confirmed")),
        "target_tool": arguments.get("target_tool") or "",
    }


def _observation(outcome: dict) -> dict:
    return {
        "ok": bool(outcome.get("ok", True)),
        "status": outcome.get("status") or "COMPLETED",
        "answer_preview": (outcome.get("answer") or "")[:500],
        "project_id": outcome.get("project_id") or "",
        "research_session_id": outcome.get("research_session_id") or "",
        "decision_id": outcome.get("decision_id") or "",
        "next_action": outcome.get("runtime_next_action") or {},
        "error_code": outcome.get("error_code") or "",
        "market_data_status": outcome.get("market_data_status") or {},
        "open_questions": list(outcome.get("open_questions") or [])[:6],
        "source_count": len(outcome.get("source_refs") or []),
        "research_completion": outcome.get("research_completion") or {},
        "research_delta": outcome.get("research_delta") or {},
        "terminal_deliverable": bool(outcome.get("runtime_terminal")),
    }


def _select_deliverable(outcomes: list, fallback: dict) -> dict:
    """Prevent helper-tool output from hiding a durable primary artifact."""
    primary = next(
        (row for row in reversed(outcomes) if row.get("runtime_primary_deliverable")),
        None,
    )
    if primary is None:
        return fallback
    selected = dict(primary)
    selected["activities"] = [
        activity
        for row in outcomes
        for activity in (row.get("activities") or [])
    ]
    selected["auxiliary_results"] = [
        {
            "tool": row.get("_runtime_tool") or "",
            "status": row.get("status") or ("COMPLETED" if row.get("ok", True) else "FAILED"),
        }
        for row in outcomes
        if row is not primary
    ]
    return selected


def _observation_summary(outcome: dict) -> str:
    if outcome.get("status") == "AWAITING_APPROVAL":
        return "等待用户确认"
    if not outcome.get("ok", True):
        return outcome.get("error_code") or "执行失败"
    if outcome.get("research_session_id"):
        return "研究工具完成"
    if outcome.get("recorder_draft_id"):
        return "已生成待确认草稿"
    return "完成"


def _next_action(outcome: dict) -> Optional[AgentAction]:
    raw = outcome.get("runtime_next_action") or {}
    if not isinstance(raw, dict) or not raw.get("name"):
        return None
    arguments = dict(raw.get("arguments") or {})
    arguments.setdefault("message", "")
    arguments.setdefault("route", {
        "mode": "SKILL" if raw.get("name") != "conversation" else "CHAT",
        "skill": raw.get("name") if raw.get("name") != "conversation" else "",
        "intent": raw.get("intent") or raw.get("name") or "",
    })
    arguments["confirmed"] = _explicit_confirmation(arguments["route"], arguments.get("message") or "")
    return AgentAction(
        kind=raw.get("kind") or "CALL_TOOL",
        name=raw.get("name") or "",
        arguments=arguments,
    )


def list_turns(store: Store, session_id: str, limit: int = 20) -> list:
    rows = store.query(
        """SELECT * FROM agent_turn WHERE session_id = ?
           ORDER BY started_at DESC, id DESC LIMIT ?""",
        (session_id, max(1, min(int(limit), 100))),
    )
    for row in rows:
        row["route"] = loads(row.get("route_json"), {})
    return rows


def get_turn(store: Store, turn_id: str) -> dict:
    rows = store.query("SELECT * FROM agent_turn WHERE id = ?", (turn_id,))
    if not rows:
        return {}
    turn = dict(rows[0])
    turn["route"] = loads(turn.get("route_json"), {})
    items = store.query("SELECT * FROM agent_item WHERE turn_id = ? ORDER BY seq", (turn_id,))
    for item in items:
        item["payload"] = loads(item.get("payload_json"), {})
    turn["items"] = items
    return turn
