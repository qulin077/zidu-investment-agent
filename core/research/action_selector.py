"""下一步动作。模型只能在白名单里选，FINISH 还要过完成门。"""
from __future__ import annotations

ACTIONS = (
    "SEARCH",
    "READ_SOURCE",
    "EXTRACT_CLAIMS",
    "VERIFY_CLAIM",
    "SEARCH_DISCONFIRMATION",
    "RESOLVE_CONFLICT",
    "BUILD_SECTION",
    "FINISH",
)


def choose(state: dict, llm=None) -> dict:
    if llm is not None and state.get("allow_llm_selector"):
        proposed = _from_llm(llm, state)
    else:
        proposed = _deterministic(state)
    if proposed["action"] not in ACTIONS:
        raise ValueError("ACTION_NOT_ALLOWED")
    return proposed


def apply_finish(action: dict, completion: dict) -> dict:
    if action.get("action") != "FINISH":
        return action
    if completion.get("passed"):
        return {**action, "status": "ALLOWED"}
    return {**action, "action": "SEARCH_DISCONFIRMATION", "status": "FINISH_BLOCKED"}


def _deterministic(state: dict) -> dict:
    if not state.get("sources_read"):
        if not state.get("search_hits"):
            return _action("SEARCH", "还没有检索结果。")
        return _action("READ_SOURCE", "检索结果还不是正文。")
    if not state.get("claims"):
        return _action("EXTRACT_CLAIMS", "正文还没拆成 Claim。")
    if state.get("unverified_claim_ids"):
        return _action("VERIFY_CLAIM", "还有 Claim 没过证据门。")
    if state.get("critical_without_disconfirmation"):
        return _action("SEARCH_DISCONFIRMATION", "关键判断还没找过反证。")
    if state.get("open_conflicts"):
        return _action("RESOLVE_CONFLICT", "口径冲突还并列着。")
    if not state.get("sections_built"):
        return _action("BUILD_SECTION", "行业或公司结构还没收束。")
    return _action("FINISH", "调度器认为可以交完成门。")


def _action(action: str, reason: str) -> dict:
    return {"action": action, "reason_code": reason, "status": "PROPOSED"}


def _from_llm(llm, state: dict) -> dict:
    raw = llm.generate_structured(
        "只输出 JSON：action。action 必须是给定白名单中的一个。",
        json_state(state),
        {"type": "object"},
        temperature=0,
    )
    import json
    data = json.loads(raw)
    action = data.get("action") or ""
    if action not in ACTIONS:
        raise ValueError("ACTION_NOT_ALLOWED")
    return _action(action, "LLM_SELECTOR")


def json_state(state: dict) -> str:
    import json
    kept = {
        "critical_gaps": state.get("critical_gaps") or [],
        "available_actions": list(ACTIONS),
    }
    return json.dumps(kept, ensure_ascii=False)
