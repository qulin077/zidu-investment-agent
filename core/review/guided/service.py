"""Guided Review 编排。Agent 输出 ≠ 正式 Review。写入仍走 repo / lifecycle。"""
from __future__ import annotations

import json
from typing import Any, Dict, Optional

from core.review import flags, lifecycle, repo
from core.review.guided import facts as factmod
from core.review.guided import questions, store as gstore, validator
from core.review.guided.types import ERROR_TYPES, PROMPT_VERSION
from core.store import STORE, Store

MODEL_NAME = "guided-heuristic-gr1"


class GuidedError(repo.ReviewError):
    pass


class GuidedDisabled(GuidedError):
    pass


def _ensure_enabled() -> None:
    if not flags.guided_review_enabled():
        raise GuidedDisabled("GUIDED_REVIEW_ENABLED=false。P1.25 Eval Gate 通过前不开放 Guided Review。")


def _ensure_pending(decision_id: str, store: Store) -> Dict[str, Any]:
    row = repo.require_decision(decision_id, store)
    if row["status"] != lifecycle.REVIEW_PENDING:
        raise GuidedError("只有 REVIEW_PENDING 能开始复盘，当前是 {0}".format(row["status"]))
    return row


def context(decision_id: str, store: Store = STORE) -> Dict[str, Any]:
    _ensure_enabled()
    ctx = factmod.build_context(decision_id, store)
    unresolved = questions.next_unresolved(ctx)
    turn = questions.build_turn(ctx, unresolved) if unresolved else questions.build_turn(ctx, "LESSON")
    validator.assert_valid(turn, ctx)
    return {
        "enabled": True,
        "facts": ctx,
        "unresolved": unresolved,
        "turn": turn,
        "prompt_version": PROMPT_VERSION,
    }


def start(decision_id: str, operator: str = "user", store: Store = STORE) -> Dict[str, Any]:
    _ensure_enabled()
    _ensure_pending(decision_id, store)
    ctx = factmod.build_context(decision_id, store)
    existing = gstore.open_session_for(decision_id, store)
    if existing:
        session_id = existing["id"]
    else:
        session_id = gstore.insert_session(
            decision_id, PROMPT_VERSION, MODEL_NAME, ctx["context_hash"], store,
        )
    unresolved = questions.next_unresolved(ctx)
    payload = questions.build_turn(ctx, unresolved)
    validator.assert_valid(payload, ctx)
    turns = gstore.turns_of(session_id, store)
    if not turns or turns[-1].get("unresolved") != unresolved or turns[-1].get("user_answer"):
        gstore.insert_turn(
            session_id, len(turns) + 1, unresolved, payload["question"],
            json.dumps(payload, ensure_ascii=False), payload, store,
        )
        gstore.update_session(session_id, {"status": "WAITING_USER"}, store)
    session = gstore.get_session(session_id, store) or {}
    try:
        from core.product.events import emit
        emit("REVIEW_STARTED", "guided_review_session", session_id,
             source=operator, metadata={"decision_id": decision_id}, store=store)
    except Exception:  # noqa: BLE001
        pass
    try:
        from core.context.store import diff as context_diff
        ctx_diff = context_diff(decision_id, store)
    except Exception:  # noqa: BLE001
        ctx_diff = {"changes": []}
    return {
        "session_id": session_id,
        "decision_id": decision_id,
        "facts": ctx,
        "turn": payload,
        "unresolved": unresolved,
        "prompt_version": PROMPT_VERSION,
        "model": session.get("model") or MODEL_NAME,
        "context_hash": ctx["context_hash"],
        "context_diff": ctx_diff,
    }


def _session_or_start(decision_id: str, store: Store) -> Dict[str, Any]:
    row = gstore.open_session_for(decision_id, store)
    if row:
        return row
    started = start(decision_id, store=store)
    return gstore.get_session(started["session_id"], store) or {}


def _touch_turn(session_id: str, answer: str, store: Store) -> None:
    turns = gstore.turns_of(session_id, store)
    if not turns:
        return
    last = turns[-1]
    gstore.update_turn(last["id"], {
        "user_answer": answer,
        "answered_at": repo.now(),
    }, store)


def confirm_outcome(
    decision_id: str,
    confirmed: bool = True,
    operator: str = "user",
    store: Store = STORE,
) -> Dict[str, Any]:
    _ensure_enabled()
    _ensure_pending(decision_id, store)
    if not confirmed:
        raise GuidedError("Outcome 未确认，不能继续")
    session = _session_or_start(decision_id, store)
    ctx = factmod.build_context(decision_id, store)
    rid = session.get("review_id") or ctx.get("review_id")
    if not rid:
        rid = repo.add_review(
            decision_id, outcome_confirmed=True, violations_confirmed=False,
            created_by=operator, store=store,
        )
    else:
        repo.amend("review", rid, "outcome_confirmed", 1, "用户确认 outcome", operator, store=store)
    gstore.update_session(session["id"], {"review_id": rid, "status": "WAITING_USER"}, store)
    _touch_turn(session["id"], "outcome_confirmed", store)
    return start(decision_id, operator, store)


def confirm_violations(
    decision_id: str,
    confirmed: bool = True,
    operator: str = "user",
    store: Store = STORE,
) -> Dict[str, Any]:
    _ensure_enabled()
    if not confirmed:
        raise GuidedError("process violation 未确认，不能继续")
    session = _session_or_start(decision_id, store)
    ctx = factmod.build_context(decision_id, store)
    rid = session.get("review_id") or ctx.get("review_id")
    if not rid:
        rid = repo.add_review(
            decision_id, outcome_confirmed=False, violations_confirmed=True,
            created_by=operator, store=store,
        )
    else:
        repo.amend("review", rid, "violations_confirmed", 1, "用户确认 process violation", operator, store=store)
    repo.acknowledge_violations(decision_id, operator, store)
    gstore.update_session(session["id"], {"review_id": rid}, store)
    _touch_turn(session["id"], "violations_confirmed", store)
    return start(decision_id, operator, store)


def answer(
    decision_id: str,
    answer_text: str,
    option_id: str = "",
    operator: str = "user",
    store: Store = STORE,
) -> Dict[str, Any]:
    """记录用户回答，生成 attribution_draft，不写正式 attribution。"""
    _ensure_enabled()
    session = _session_or_start(decision_id, store)
    ctx = factmod.build_context(decision_id, store)
    unresolved = questions.next_unresolved(ctx)
    payload = questions.build_turn(ctx, unresolved)
    combined = "{0} {1}".format(option_id, answer_text).strip()
    _touch_turn(session["id"], combined, store)
    parsed = {
        "option_id": option_id,
        "answer": answer_text,
        "unresolved": unresolved,
        "question": payload.get("question"),
        "candidates": payload.get("attribution_candidates") or [],
    }
    primary = ""
    if unresolved == "ATTRIBUTION":
        gstore.insert_attr_draft(
            session["id"], decision_id, parsed, primary_error="",
            evidence=[c.get("evidence_refs") for c in payload.get("attribution_candidates") or []],
            store=store,
        )
    if unresolved == "LESSON" and answer_text.strip():
        rid = session.get("review_id") or ctx.get("review_id")
        if rid:
            repo.amend("review", rid, "lesson", answer_text.strip(), "用户写下 lesson", operator, store=store)
    gstore.update_session(session["id"], {"status": "DRAFT"}, store)
    return {
        "session_id": session["id"],
        "decision_id": decision_id,
        "recorded": True,
        "unresolved": unresolved,
        "attribution_written": False,
        "agent_conclusion": None,
        "primary_error": primary,
        "note": "回答已记录，尚未写入正式 attribution",
    }


def confirm_attribution(
    decision_id: str,
    primary_error: str,
    evidence: Optional[list] = None,
    counterfactual: str = "",
    operator: str = "user",
    store: Store = STORE,
) -> Dict[str, Any]:
    _ensure_enabled()
    if primary_error not in ERROR_TYPES:
        raise GuidedError("未知 primary_error：{0}".format(primary_error))
    session = _session_or_start(decision_id, store)
    ctx = factmod.build_context(decision_id, store)
    if not ctx.get("outcome_confirmed"):
        raise GuidedError("outcome 未经用户确认")
    if not ctx.get("violations_confirmed"):
        raise GuidedError("process violation 未经用户确认")
    rid = session.get("review_id") or ctx.get("review_id")
    if not rid:
        raise GuidedError("还没有 review 行，不能确认归因")
    cf = counterfactual
    if not cf and ctx.get("counterfactual"):
        cf = (ctx["counterfactual"] or {}).get("statement") or ""
    aid = repo.add_attribution(
        decision_id, rid, primary_error,
        evidence=evidence or [],
        counterfactual=cf,
        user_confirmed=True,
        created_by=operator,
        store=store,
    )
    draft = gstore.latest_attr_draft(decision_id, store)
    if draft:
        gstore.update_attr_draft(draft["id"], {
            "primary_error": primary_error,
            "user_confirmed": 1,
            "confirmed_at": repo.now(),
        }, store)
    gstore.update_session(session["id"], {"status": "DRAFT"}, store)
    _touch_turn(session["id"], "attribution:{0}".format(primary_error), store)
    return {"attribution_id": aid, "primary_error": primary_error, "user_confirmed": True}


def complete(
    decision_id: str,
    lesson: str = "",
    operator: str = "user",
    store: Store = STORE,
) -> Dict[str, Any]:
    _ensure_enabled()
    ctx = factmod.build_context(decision_id, store)
    if not ctx.get("outcome_confirmed"):
        raise GuidedError("outcome 未经用户确认，不能 REVIEWED")
    if not ctx.get("violations_confirmed"):
        raise GuidedError("process violation 未经用户确认，不能 REVIEWED")
    if not ctx.get("attribution_confirmed"):
        raise GuidedError("attribution 未经用户确认，不能 REVIEWED")
    session = gstore.open_session_for(decision_id, store)
    rid = (session or {}).get("review_id") or ctx.get("review_id")
    if lesson and rid:
        repo.amend("review", rid, "lesson", lesson, "复盘 lesson（不升级成规则）", operator, store=store)
    moved = repo.transition(
        decision_id, lifecycle.REVIEWED, "Guided Review 完成", operator, "user", store,
    )
    if session:
        gstore.update_session(session["id"], {
            "status": "CONFIRMED",
            "confirmed_at": repo.now(),
            "review_id": rid or "",
        }, store)
    memory_payload: Dict[str, Any] = {"ok": False, "reason": "not ingested"}
    try:
        from core.review.memory.service import ingest_reviewed

        memory_payload = ingest_reviewed(decision_id, store=store)
    except Exception as exc:  # noqa: BLE001 — Review 已完成，Memory 失败不得回滚
        memory_payload = {"ok": False, "error": str(exc)}
    try:
        from core.product.events import emit
        emit("REVIEW_COMPLETED", "decision", decision_id, source=operator, store=store)
    except Exception:  # noqa: BLE001
        pass
    try:
        from core.context.store import diff as context_diff
        ctx_diff = context_diff(decision_id, store)
    except Exception:  # noqa: BLE001
        ctx_diff = {"changes": []}
    return {
        "decision_id": decision_id,
        "status": lifecycle.REVIEWED,
        "transition": moved,
        "review_id": rid,
        "lesson": lesson or ctx.get("lesson") or "",
        "audit": repo.transitions_of(decision_id, store),
        "memory": memory_payload,
        "context_diff": ctx_diff,
    }
