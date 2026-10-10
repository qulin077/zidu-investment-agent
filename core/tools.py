"""运行时 Tool 表。CLI、MCP、HTTP、Skill 都走这里。

Harness 不是 Tool：research_run 这一个 Tool 内部才跑 DAG。
MCP 不是专家：它只是 Cursor 调用本表的协议。
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

import yaml

from core.config import CONFIG_DIR

RUNTIME_YAML = CONFIG_DIR / "runtime.yaml"

Handler = Callable[[Dict[str, Any]], Dict[str, Any]]


def load_runtime(path=RUNTIME_YAML) -> Dict[str, Any]:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def catalog() -> Dict[str, Any]:
    cfg = load_runtime()
    return {
        "layers": cfg.get("layers") or {},
        "tools": cfg.get("tools") or [],
        "disclaimer": "研究框架，非投资建议。",
    }


def _clip_name_pct(rows: List[Dict[str, Any]], limit: int = 3) -> List[Dict[str, Any]]:
    out = []
    for row in rows[:limit]:
        out.append(
            {
                "name": row.get("name") or row.get("code"),
                "pct_chg": row.get("pct_chg"),
            }
        )
    return out


def _compact_dialogue(data: Dict[str, Any]) -> Dict[str, Any]:
    nxt = data.get("next") or {}
    facts = (data.get("context") or {}).get("facts") or {}
    return {
        "intent": data.get("intent"),
        "room": data.get("room"),
        "followup": data.get("followup"),
        "next_slot": nxt.get("slot"),
        "next_ask": nxt.get("ask"),
        "reply": data.get("reply"),
        "action": data.get("action"),
        "tools": data.get("tools") or [],
        "facts": {k: v for k, v in facts.items() if k != "tool"},
        "window": data.get("window"),
    }


def _compact_replay(data: Dict[str, Any]) -> Dict[str, Any]:
    trades = []
    for row in data.get("trades") or []:
        trades.append(
            {
                "code": row.get("code"),
                "name": row.get("name"),
                "side": row.get("side"),
                "earning_type": row.get("earning_type"),
                "planned": row.get("planned"),
            }
        )
    return {
        "asof": data.get("asof"),
        "n_trades": data.get("n_trades"),
        "unplanned": data.get("unplanned"),
        "missing_earning_type": data.get("missing_earning_type"),
        "pending_predictions": (data.get("predictions") or {}).get("pending_count"),
        "trades": trades,
    }


def _compact_research(data: Dict[str, Any]) -> Dict[str, Any]:
    analysis = data.get("analysis") or {}
    risk = data.get("risk") or {}
    report = data.get("report") or {}
    return {
        "ok": data.get("ok"),
        "topic": data.get("topic"),
        "asof": data.get("asof"),
        "refuse": data.get("refuse"),
        "one_liner": analysis.get("one_liner"),
        "prediction_draft": analysis.get("prediction_draft"),
        "write_to_replay": analysis.get("write_to_replay"),
        "buy_allowed": risk.get("buy_allowed"),
        "buy_blocked_reason": risk.get("buy_blocked_reason"),
        "report_path": report.get("path"),
        "trace": [
            {"agent": step.get("agent"), "ok": step.get("ok"), "ms": step.get("ms")}
            for step in data.get("trace") or []
        ],
    }


def _compact_board(data: Dict[str, Any]) -> Dict[str, Any]:
    movers = data.get("movers") or {}
    positions = data.get("positions") or {}
    health = data.get("health") or {}
    pulse = data.get("pulse") or {}
    vix = pulse.get("vix") or {}
    emotion = pulse.get("emotion") or {}
    return {
        "health_ok": health.get("ok"),
        "asof": movers.get("asof"),
        "vix": vix.get("value"),
        "vix_band": vix.get("band"),
        "emotion": emotion.get("stage"),
        "limit_up": emotion.get("limit_up"),
        "gainers": _clip_name_pct(movers.get("gainers") or []),
        "losers": _clip_name_pct(movers.get("losers") or []),
        "stale_days": positions.get("stale_days"),
        "trade_asof": (data.get("trades") or {}).get("asof"),
        "news_n": len((data.get("news") or {}).get("rows") or []),
    }


def _compact_personas(data: Dict[str, Any]) -> Dict[str, Any]:
    modes = []
    for key, spec in (data.get("modes") or {}).items():
        modes.append(
            {
                "id": key,
                "name": spec.get("name") or key,
                "one_liner": spec.get("one_liner") or "",
                "fail_when": spec.get("fail_when") or "",
            }
        )
    return {"modes": modes}


def _compact_chain(data: Dict[str, Any]) -> Dict[str, Any]:
    money = data.get("money") or {}
    book = data.get("book") or {}
    if data.get("kind") and not data.get("id"):
        return {
            "kind": data.get("kind"),
            "name": data.get("name") or data.get("code"),
            "refuse": data.get("refuse"),
        }
    return {
        "id": data.get("id"),
        "name": data.get("name"),
        "asof": data.get("asof"),
        "money_layer": money.get("name"),
        "money_pct": money.get("avg_pct"),
        "switched": data.get("switched"),
        "book_verdict": book.get("verdict"),
        "stale_warning": book.get("stale_warning"),
        "held": len(book.get("in_chain") or []),
    }


def _dialogue_turn(args: Dict[str, Any]) -> Dict[str, Any]:
    from core.dialogue import turn

    query = str(args.get("q") or "").strip()
    if not query:
        raise ValueError("dialogue_turn 需要 q")
    persist = args.get("persist")
    if persist is None:
        persist = True
    return turn(query, persist=bool(persist))


def _replay_get(args: Dict[str, Any]) -> Dict[str, Any]:
    from app.api.services import replay

    date = args.get("date") or None
    if date == "":
        date = None
    return replay(date)


def _research_run(args: Dict[str, Any]) -> Dict[str, Any]:
    from core.research.harness import run

    query = str(args.get("q") or "").strip()
    if not query:
        raise ValueError("research_run 需要 q")
    write = args.get("write")
    if write is None:
        write = True
    return run(query, write=bool(write))


def _chain_brief(args: Dict[str, Any]) -> Dict[str, Any]:
    from core.chain_brief import brief, resolve

    query = str(args.get("q") or args.get("chain_id") or "").strip()
    if not query:
        raise ValueError("chain_brief 需要 q")
    resolved = resolve(query)
    if resolved.get("kind") == "chain" and resolved.get("id"):
        return brief(resolved["id"])
    return resolved


def _board_get(_args: Dict[str, Any]) -> Dict[str, Any]:
    from app.api.services import board

    return board()


def _personas_get(_args: Dict[str, Any]) -> Dict[str, Any]:
    from app.api.services import personas

    return personas()


HANDLERS: Dict[str, Handler] = {
    "dialogue_turn": _dialogue_turn,
    "replay_get": _replay_get,
    "research_run": _research_run,
    "chain_brief": _chain_brief,
    "board_get": _board_get,
    "personas_get": _personas_get,
}

COMPACTERS: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {
    "dialogue_turn": _compact_dialogue,
    "replay_get": _compact_replay,
    "research_run": _compact_research,
    "chain_brief": _compact_chain,
    "board_get": _compact_board,
    "personas_get": _compact_personas,
}

NEXT_TOOLS = {
    "replay.ingest": "replay_get",
    "replay.score": "replay_get",
    "research.ask": "research_run",
    "mode.set": "personas_get",
    "board.look": "board_get",
}


def next_tools(intent: str, query: str) -> List[Dict[str, Any]]:
    """总控认完意图之后，模型/网页该调的下一个 Tool。"""
    name = NEXT_TOOLS.get(intent)
    if not name:
        return []
    args: Dict[str, Any] = {}
    if name in ("research_run", "chain_brief", "dialogue_turn"):
        args["q"] = query
    return [{"name": name, "args": args}]


def spec(name: str) -> Optional[Dict[str, Any]]:
    for item in catalog().get("tools") or []:
        if item.get("name") == name:
            return item
    return None


def call(name: str, args: Optional[Dict[str, Any]] = None, compact: bool = True) -> Dict[str, Any]:
    if name not in HANDLERS:
        raise KeyError("未知 Tool：{0}".format(name))
    payload = HANDLERS[name](args or {})
    if compact and name in COMPACTERS:
        payload = COMPACTERS[name](payload)
    return payload
