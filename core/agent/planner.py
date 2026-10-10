"""Model-owned action planning for the outer investment-agent loop.

The deterministic semantic router is deliberately only a fallback.  When a
model is available it sees the conversation, current state and tool catalog,
then chooses an action.  After a business tool returns, it sees the observation
and may finish or choose another tool.  Policy gates remain outside the model.
"""
from __future__ import annotations

import json

from core.agent.environment import answer_environment_question, runtime_context
from core.agent.harness import AgentAction

PLANNER_PROMPT_VERSION = "ip2"

INITIAL_PROMPT = """
你是 Investment Agent 的行动规划器，不是意图分类器。根据用户目标、最近对话、当前状态和工具目录，
选择当前最有价值的一步。不要被工具名称限制住：先理解用户真正要解决什么，再决定聊天或调用工具。
只输出 JSON，不输出思维过程。

输出：
- decision: CHAT 或 CALL_TOOL
- tool: CHAT 时留空；CALL_TOOL 时必须是工具目录里的名字
- intent: 一句简短、面向任务的意图描述
- entities: [{mention,type,code}]
- need_network / need_market_data / need_portfolio_context / need_research_memory / need_decision_memory
- write_action
- reply: 仅 CHAT 时填写自然回答；需要澄清时只问一个关键问题
- journal: {save,entry_type,summary}
- confidence

规则：
1. runtime_context 是运行环境提供的可信事实。日期、时间、星期等基础问题直接依据它 CHAT，
   不需要联网，也不能声称自己没有时钟。普通聊天、情绪和抱怨也可以直接 CHAT，不强行研究。
   天气等需要外部实时数据的非投资任务，如果没有对应工具，简短说明能力边界即可；
   不要擅自把话题拉回历史公司、待办或未完成决策。
2. 最新事实必须调用合适工具，不能凭模型记忆回答。
   也不能根据上一轮“刷新失败”的聊天记录推断这一轮仍失败；必须重新调用工具检查当前状态。
3. “今天/现在/最新”的盘面问题选 market-scan，并声明 need_market_data=true；Runtime 会先检查数据。
4. 工具可以在后续 Observation 后继续组合，不必一次规划完整流程。
5. 不给买卖建议、目标价或仓位。
6. 不输出 chain-of-thought，只给结构化行动。
提示词版本 ip2。
""".strip()

NEXT_PROMPT = """
你是 Investment Agent 的下一步行动规划器。工具刚返回一个 Observation。
判断当前信息是否足以结束；如果还缺关键一步，从工具目录选择另一个工具。
只输出 JSON，不输出思维过程。

输出：
- decision: FINISH 或 CALL_TOOL
- tool: CALL_TOOL 时必须来自工具目录
- message: 给下一个工具的具体任务，默认沿用用户原话
- intent: 简短任务意图
- entities: [{mention,type,code}]
- need_network / need_market_data / need_portfolio_context / need_research_memory / need_decision_memory
- write_action

不要重复执行已经成功的编排型研究工具；company-research 和 industry-research 内部已经负责继续搜索、
覆盖检查与报告生成，它们返回档案后应 FINISH，而不是换一种措辞重跑或再用技术面工具覆盖主报告。
Observation 中的 research_completion 是覆盖检查，不是继续递归调用研究工具的理由；缺口应由研究工具内部
标明为待补充或来源不可得。最新事实不足时不要假装完成。
不要绕过数据新鲜度、权限确认或写入闸门。
runtime_context 是可信的当前日期时间，可用于解释相对日期，但不能替代外部市场数据。
提示词版本 ip2。
""".strip()


class ModelActionPlanner:
    def __init__(
        self, llm, *, summary: dict | None = None, history: list | None = None,
        network: str = "replay", now=None, context_state: dict | None = None,
    ):
        self.llm = llm
        self.summary = summary or {}
        self.history = history or []
        self.network = network
        self.context_state = context_state or {}
        self.environment = runtime_context(now)

    def plan_turn(self, message: str, fallback: dict, tools: list) -> dict:
        # Exact confirmation/cancellation is a policy decision, not something a
        # probabilistic planner may reinterpret.
        if fallback.get("intent") in (
            "CONFIRM_DECISION", "CANCEL_DECISION",
            "RESEARCH_INTAKE_RESOLVED", "RESEARCH_INTAKE_CANCELLED",
        ):
            return fallback
        direct_reply = answer_environment_question(message, self.environment)
        if direct_reply:
            planned = dict(fallback)
            planned.update({
                "mode": "CHAT", "skill": "", "intent": "RUNTIME_CONTEXT",
                "reason_code": "ENVIRONMENT_CONTEXT", "domain": "GENERAL",
                "entities": [], "entity": {"name": "", "code": ""},
                "need_network": False, "need_market_data": False,
                "need_portfolio_context": False, "need_research_memory": False,
                "need_decision_memory": False, "write_action": False,
                "reply": direct_reply, "journal": {}, "confidence": 1.0,
            })
            return planned
        payload = {
            "message": message,
            "network": self.network,
            "runtime_context": self.environment,
            "current_state": _state(self.summary, self.context_state),
            "recent_conversation": _history(self.history),
            "tools": tools,
            "fallback_hint": {
                "mode": fallback.get("mode"), "skill": fallback.get("skill"),
                "intent": fallback.get("intent"),
            },
        }
        data = self._ask(INITIAL_PROMPT, payload)
        if not data:
            return fallback
        decision = (data.get("decision") or "").upper()
        names = {row.get("name") for row in tools}
        if decision == "CHAT":
            # CHAT may not short-circuit a fresh-fact request.  The model owns
            # intent understanding, while this validator enforces that current
            # facts are re-observed instead of copied from conversation memory.
            if fallback.get("mode") == "SKILL" and (
                fallback.get("need_market_data")
                or fallback.get("need_network")
                or fallback.get("need_portfolio_context")
            ):
                guarded = dict(fallback)
                guarded["reason_code"] = "MODEL_TOOL_REQUIRED"
                return guarded
            planned = dict(fallback)
            planned.update({
                "mode": "CHAT", "skill": "", "intent": data.get("intent") or "GENERAL_CHAT",
                "reason_code": "MODEL_PLANNER", "domain": "GENERAL",
                "entities": [], "entity": {"name": "", "code": ""},
                "need_network": False, "need_market_data": False,
                "need_portfolio_context": False, "need_research_memory": False,
                "need_decision_memory": False, "write_action": False,
                "reply": (data.get("reply") or "").strip(),
                "journal": data.get("journal") if isinstance(data.get("journal"), dict) else {},
                "confidence": _confidence(data.get("confidence")),
            })
            return planned
        tool = data.get("tool") or ""
        if decision != "CALL_TOOL" or tool not in names:
            return fallback
        return _planned_route(data, fallback, tool)

    def after_observation(
        self, *, message: str, route: dict, step: int, action: AgentAction,
        observation: dict, tools: list, executed: list,
    ) -> dict:
        payload = {
            "user_goal": message,
            "network": self.network,
            "runtime_context": self.environment,
            "current_state": _state(self.summary, self.context_state),
            "route": _route_view(route),
            "step": step,
            "last_action": {"tool": action.name, "message": action.arguments.get("message") or message},
            "observation": observation,
            "executed": executed,
            "tools": tools,
        }
        data = self._ask(NEXT_PROMPT, payload)
        if not data:
            return {}
        decision = (data.get("decision") or "").upper()
        if decision == "FINISH":
            return {"decision": "FINISH"}
        names = {row.get("name") for row in tools}
        tool = data.get("tool") or ""
        if decision != "CALL_TOOL" or tool not in names:
            return {}
        next_route = _planned_route(data, route, tool)
        next_message = (data.get("message") or message).strip()
        return {
            "decision": "CALL_TOOL",
            "action": AgentAction(
                kind="CHAT" if tool == "conversation" else "CALL_TOOL",
                name=tool,
                arguments={"message": next_message, "route": next_route, "confirmed": False},
            ),
        }

    def _ask(self, system: str, payload: dict) -> dict:
        try:
            raw = self.llm.generate_structured(
                system, json.dumps(payload, ensure_ascii=False), {"type": "object"},
                temperature=0, timeout=30,
            )
            data = json.loads(raw) if isinstance(raw, str) else dict(raw or {})
            return data if isinstance(data, dict) else {}
        except AssertionError:
            raise
        except Exception:
            return {}


def _planned_route(data: dict, fallback: dict, tool: str) -> dict:
    planned = dict(fallback)
    entities = []
    for row in data.get("entities") or []:
        if not isinstance(row, dict):
            continue
        mention = (row.get("mention") or row.get("name") or "").strip()
        if mention or row.get("code"):
            entities.append({
                "mention": mention, "type": row.get("type") or "company", "code": row.get("code") or "",
            })
    if not entities and tool in ("company-research", "event-impact", "candidate-discovery"):
        entities = [dict(row) for row in (fallback.get("entities") or []) if isinstance(row, dict)]
    if tool in ("market-scan", "portfolio-monitor", "memory-query", "guided-review"):
        entities = []
    first = entities[0] if entities else {}
    domain = "RESEARCH" if tool in ("company-research", "industry-research", "event-impact", "candidate-discovery") else (
        "DECISION" if tool == "decision-recorder" else "REVIEW" if tool == "guided-review" else "GENERAL"
    )
    planned.update({
        "mode": "SKILL", "skill": tool, "intent": data.get("intent") or tool,
        "reason_code": "MODEL_PLANNER", "domain": domain,
        "entities": entities,
        "entity": {"name": first.get("mention") or "", "code": first.get("code") or ""},
        "need_network": bool(data.get("need_network")),
        # security-snapshot 和 company-research 在解析出具体代码后做单标的数据闸门，
        # 不能误用整个自选池的覆盖率作为前置条件。
        "need_market_data": tool == "market-scan" or (
            tool not in ("security-snapshot", "company-research") and bool(data.get("need_market_data"))
        ),
        "need_portfolio_context": tool == "portfolio-monitor" or bool(data.get("need_portfolio_context")),
        "need_research_memory": tool in ("company-research", "industry-research", "event-impact", "candidate-discovery") or bool(data.get("need_research_memory")),
        "need_decision_memory": tool in ("guided-review", "memory-query", "decision-recorder") or bool(data.get("need_decision_memory")),
        "write_action": tool == "decision-recorder" or bool(data.get("write_action")),
        "reply": "",
        "journal": data.get("journal") if isinstance(data.get("journal"), dict) else {},
        "confidence": _confidence(data.get("confidence")),
    })
    return planned


def _state(summary: dict, context_state: dict | None = None) -> dict:
    state = {
        "active_entity": summary.get("active_entity") or summary.get("entity_name") or "",
        "active_event": summary.get("active_event") or "",
        "active_industry": summary.get("active_industry") or "",
        "last_skill": summary.get("last_skill") or "",
        "pending_research_intake": summary.get("pending_research_intake") or {},
        "research_preferences_by_entity": summary.get("research_preferences_by_entity") or {},
        "open_questions": list(summary.get("open_questions") or [])[:6],
        "conversation_summary": ((summary.get("conversation_compaction") or {}).get("digest") or "")[-2400:],
    }
    state.update(context_state or {})
    return state


def _history(history: list) -> list:
    return [
        {"role": row.get("role") or "user", "content": (row.get("content") or "")[:600]}
        for row in history[-12:]
    ]


def _route_view(route: dict) -> dict:
    return {
        "skill": route.get("skill") or "", "intent": route.get("intent") or "",
        "entity": route.get("entity") or {}, "domain": route.get("domain") or "GENERAL",
    }


def _confidence(value) -> float:
    try:
        return max(0.0, min(float(value), 1.0))
    except (TypeError, ValueError):
        return 0.8
