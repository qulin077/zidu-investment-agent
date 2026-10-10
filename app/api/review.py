"""Review Today API。

UI → 这里 → core.review。写操作一律走 matching / repo / pipeline，
不在这一层改 decision_id。
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from core.review import card, flags, lifecycle, matching, repo
from core.review.guided import service as guided
from core.review.intake import pipeline
from core.review.memory import metrics as memory_metrics
from core.review.memory import reminders as memory_reminders
from core.review.memory import service as memory
from core.review.memory.validator import MemoryError
from core.review.recorder import service as recorder
from core.review.recorder.store import get_draft, get_input, shadows_for
from core.review.today import snapshot, workbench as today_workbench_model
from core.store import STORE, Store

router = APIRouter()


def get_store() -> Store:
    return STORE


def _day(raw: Optional[str]) -> str:
    return (raw or "").strip() or repo.today()


def _err(exc: Exception) -> HTTPException:
    status = 404 if isinstance(exc, repo.ReviewError) and "找不到" in str(exc) else 400
    return HTTPException(status_code=status, detail=str(exc))


@router.get("/api/review/today", summary="Review Today：成交 + 待认领 + 队列")
def review_today(date: Optional[str] = Query(None), store: Store = Depends(get_store)):
    return snapshot(_day(date), store)


@router.get("/api/review/archive", summary="Decision 复盘档案")
def review_archive(
    status: str = Query(""),
    code: str = Query(""),
    limit: int = Query(200, ge=1, le=1000),
    store: Store = Depends(get_store),
):
    """历史 Decision 只读索引；Today 的当日工作不在这里重复呈现。"""
    rows = repo.list_decisions(status=status.strip(), code=code.strip(), limit=limit, store=store)
    items = []
    for row in rows:
        decision_id = row["id"]
        executions = repo.executions(decision_id, store)
        reviews = repo.reviews(decision_id, store)
        outcome = repo.get_outcome(decision_id, store)
        items.append({
            "id": decision_id,
            "opened_on": row.get("opened_on") or "",
            "closed_on": row.get("closed_on") or "",
            "reviewed_at": row.get("reviewed_at") or "",
            "code": row.get("code") or "",
            "name": row.get("name") or "",
            "direction": row.get("direction") or "",
            "status": row.get("status") or "",
            "origin": row.get("origin") or "EX_ANTE",
            "thesis": row.get("thesis") or "",
            "holding_period": row.get("holding_period") or "",
            "execution_count": len(executions),
            "review_count": len(reviews),
            "realized_pnl": outcome.get("realized_pnl") if outcome else None,
        })
    return {"items": items, "total": len(items)}


@router.get("/api/review/executions", summary="当日 execution")
def review_executions(date: Optional[str] = Query(None), store: Store = Depends(get_store)):
    data = snapshot(_day(date), store)
    return {"date": data["date"], "rows": data["executions"]}


@router.get("/api/review/decision/{decision_id}", summary="Decision 详情（复用 card）")
def review_decision(decision_id: str, store: Store = Depends(get_store)):
    try:
        built = card.build(decision_id, store)
        from core.research.decision_link import review_snapshot
        return {
            "decision_id": decision_id,
            "card": card.render(decision_id, store),
            "context": _context_card(decision_id, store),
            "context_diff": _context_diff(decision_id, store),
            "research_link": review_snapshot(decision_id, store),
            **built,
        }
    except repo.ReviewError as exc:
        raise _err(exc) from exc


class ConfirmIn(BaseModel):
    execution_id: str
    decision_id: str
    note: str = ""


class UnmatchedIn(BaseModel):
    execution_id: str
    note: str = ""


class PostHocIn(BaseModel):
    execution_id: str
    thesis: str = ""


@router.post("/api/review/match/confirm", summary="人工确认归属")
def review_confirm(body: ConfirmIn, store: Store = Depends(get_store)):
    try:
        result = matching.confirm(
            body.execution_id, body.decision_id, operator="user",
            note=body.note, store=store,
        )
        result["transitions"] = pipeline._advance_safely(body.decision_id, store)
        return result
    except (repo.ReviewError, lifecycle.IllegalTransition, lifecycle.GuardFailed) as exc:
        raise _err(exc) from exc


@router.post("/api/review/match/unmatched", summary="先不挂")
def review_unmatched(body: UnmatchedIn, store: Store = Depends(get_store)):
    try:
        return matching.leave_unmatched(
            body.execution_id, operator="user", note=body.note, store=store,
        )
    except repo.ReviewError as exc:
        raise _err(exc) from exc


@router.post("/api/review/decision/post-hoc", summary="新建 POST_HOC Decision 并挂上成交")
def review_post_hoc(body: PostHocIn, store: Store = Depends(get_store)):
    try:
        return matching.create_post_hoc(
            body.execution_id, thesis=body.thesis, operator="user", store=store,
        )
    except (repo.ReviewError, lifecycle.IllegalTransition, lifecycle.GuardFailed) as exc:
        raise _err(exc) from exc


class RecorderParseIn(BaseModel):
    raw_text: str
    known_symbol: str = ""
    known_company: str = ""
    mode: str = "premarket"
    account: str = ""
    draft_id: str = ""


class RecorderConfirmIn(BaseModel):
    draft_id: str
    confirmed: bool = False
    edits: dict = {}


class RecorderRejectIn(BaseModel):
    draft_id: str


@router.post("/api/review/recorder/parse", summary="Recorder：原文 → 草稿（不写 Decision）")
def recorder_parse(body: RecorderParseIn, store: Store = Depends(get_store)):
    try:
        return recorder.parse(
            body.raw_text,
            known_symbol=body.known_symbol,
            known_company=body.known_company,
            mode=body.mode,
            account=body.account,
            draft_id=body.draft_id,
            source="web",
            store=store,
        )
    except recorder.RecorderError as exc:
        raise _err(exc) from exc


@router.post("/api/review/recorder/confirm", summary="Recorder Write Gate")
def recorder_confirm(body: RecorderConfirmIn, store: Store = Depends(get_store)):
    try:
        return recorder.confirm(
            body.draft_id, confirmed=body.confirmed,
            edits=body.edits or None, store=store,
        )
    except (recorder.RecorderError, repo.ReviewError, lifecycle.IllegalTransition, lifecycle.GuardFailed) as exc:
        raise _err(exc) from exc


@router.post("/api/review/recorder/reject", summary="放弃 Recorder 草稿")
def recorder_reject(body: RecorderRejectIn, store: Store = Depends(get_store)):
    try:
        return recorder.reject(body.draft_id, store=store)
    except repo.ReviewError as exc:
        raise _err(exc) from exc


@router.get("/api/review/recorder/draft/{draft_id}", summary="读取 Recorder 草稿")
def recorder_draft(draft_id: str, store: Store = Depends(get_store)):
    row = get_draft(draft_id, store)
    if row is None:
        raise HTTPException(status_code=404, detail="找不到草稿")
    event = get_input(row["input_event_id"], store)
    return {"draft": row, "input": event}


@router.get("/api/review/flags", summary="产品开关")
def review_flags():
    return flags.snapshot()


@router.get("/api/recorder/metrics", summary="Recorder 在线指标")
def recorder_metrics(store: Store = Depends(get_store)):
    return recorder.online_metrics(store=store)


class ShadowIn(BaseModel):
    input_id: str = ""
    raw_text: str = ""
    known_symbol: str = ""
    mode: str = "premarket"


@router.post("/api/recorder/shadow", summary="Shadow Recorder：不进 Write Gate")
def recorder_shadow(body: ShadowIn, store: Store = Depends(get_store)):
    if body.input_id:
        rows = shadows_for(body.input_id, store)
        return {"input_id": body.input_id, "shadows": rows, "write_gate": False}
    if not body.raw_text.strip():
        raise HTTPException(status_code=400, detail="需要 input_id 或 raw_text")
    result = recorder.parse(
        body.raw_text, known_symbol=body.known_symbol, mode=body.mode,
        source="shadow", store=store,
    )
    shadows = shadows_for(result.get("input_id") or "", store)
    return {
        "input_id": result.get("input_id"),
        "primary_draft_id": result.get("draft_id"),
        "primary_status": result.get("status"),
        "shadows": shadows,
        "write_gate": False,
        "decision_count": store.count("decision"),
    }


@router.get("/api/recorder/shadow", summary="读取某次输入的 shadow 对照")
def recorder_shadow_get(input_id: str = Query(...), store: Store = Depends(get_store)):
    return {"input_id": input_id, "shadows": shadows_for(input_id, store), "write_gate": False}


def _guided_err(exc: Exception) -> HTTPException:
    if isinstance(exc, guided.GuidedDisabled):
        return HTTPException(status_code=403, detail=str(exc))
    return _err(exc)


@router.get("/api/review/{decision_id}/context", summary="Guided Review 事实卡")
def guided_context(decision_id: str, store: Store = Depends(get_store)):
    try:
        return guided.start(decision_id, store=store)
    except (guided.GuidedError, repo.ReviewError) as exc:
        raise _guided_err(exc) from exc


class ConfirmFlagIn(BaseModel):
    confirmed: bool = True


class AnswerIn(BaseModel):
    answer: str = ""
    option_id: str = ""


class AttributionIn(BaseModel):
    primary_error: str
    evidence: list = []
    counterfactual: str = ""


class CompleteIn(BaseModel):
    lesson: str = ""


@router.post("/api/review/{decision_id}/confirm-outcome")
def guided_confirm_outcome(decision_id: str, body: ConfirmFlagIn, store: Store = Depends(get_store)):
    try:
        return guided.confirm_outcome(decision_id, confirmed=body.confirmed, store=store)
    except (guided.GuidedError, repo.ReviewError, lifecycle.GuardFailed) as exc:
        raise _guided_err(exc) from exc


@router.post("/api/review/{decision_id}/confirm-violations")
def guided_confirm_violations(decision_id: str, body: ConfirmFlagIn, store: Store = Depends(get_store)):
    try:
        return guided.confirm_violations(decision_id, confirmed=body.confirmed, store=store)
    except (guided.GuidedError, repo.ReviewError, lifecycle.GuardFailed) as exc:
        raise _guided_err(exc) from exc


@router.post("/api/review/{decision_id}/answer")
def guided_answer(decision_id: str, body: AnswerIn, store: Store = Depends(get_store)):
    try:
        return guided.answer(decision_id, answer_text=body.answer, option_id=body.option_id, store=store)
    except (guided.GuidedError, repo.ReviewError) as exc:
        raise _guided_err(exc) from exc


@router.post("/api/review/{decision_id}/confirm-attribution")
def guided_confirm_attribution(decision_id: str, body: AttributionIn, store: Store = Depends(get_store)):
    try:
        return guided.confirm_attribution(
            decision_id, body.primary_error, evidence=body.evidence,
            counterfactual=body.counterfactual, store=store,
        )
    except (guided.GuidedError, repo.ReviewError, lifecycle.GuardFailed) as exc:
        raise _guided_err(exc) from exc


@router.post("/api/review/{decision_id}/complete")
def guided_complete(decision_id: str, body: CompleteIn, store: Store = Depends(get_store)):
    try:
        return guided.complete(decision_id, lesson=body.lesson, store=store)
    except (guided.GuidedError, repo.ReviewError, lifecycle.IllegalTransition, lifecycle.GuardFailed) as exc:
        raise _guided_err(exc) from exc


# ------------------------------------------------------------------ P1.4 Memory

def _memory_err(exc: Exception) -> HTTPException:
    if isinstance(exc, MemoryError):
        return HTTPException(status_code=400, detail=str(exc))
    return _err(exc)


@router.get("/api/memory/patterns", summary="Pattern 列表")
def memory_patterns(store: Store = Depends(get_store)):
    return {"rows": memory.list_patterns(store)}


@router.get("/api/memory/patterns/{pattern_id}", summary="Pattern 详情 + 证据")
def memory_pattern_detail(pattern_id: str, store: Store = Depends(get_store)):
    try:
        return memory.pattern_detail(pattern_id, store)
    except MemoryError as exc:
        raise _memory_err(exc) from exc


class PatternOpIn(BaseModel):
    note: str = ""


@router.post("/api/memory/patterns/{pattern_id}/confirm")
def memory_pattern_confirm(pattern_id: str, body: PatternOpIn = PatternOpIn(), store: Store = Depends(get_store)):
    try:
        return memory.confirm_pattern(pattern_id, store=store)
    except MemoryError as exc:
        raise _memory_err(exc) from exc


@router.post("/api/memory/patterns/{pattern_id}/dismiss")
def memory_pattern_dismiss(pattern_id: str, body: PatternOpIn = PatternOpIn(), store: Store = Depends(get_store)):
    try:
        return memory.dismiss_pattern(pattern_id, store=store)
    except MemoryError as exc:
        raise _memory_err(exc) from exc


class MergeIn(BaseModel):
    source_id: str


@router.post("/api/memory/patterns/{pattern_id}/merge")
def memory_pattern_merge(pattern_id: str, body: MergeIn, store: Store = Depends(get_store)):
    try:
        return memory.merge_patterns(body.source_id, pattern_id, store=store)
    except MemoryError as exc:
        raise _memory_err(exc) from exc


@router.get("/api/memory/rules")
def memory_rules(store: Store = Depends(get_store)):
    return {"rows": memory.list_rules(store)}


class ProposeIn(BaseModel):
    pattern_id: str
    rule_text: str = ""
    trigger_text: str = ""
    expected_behavior: str = ""


@router.post("/api/memory/rules/propose")
def memory_rules_propose(body: ProposeIn, store: Store = Depends(get_store)):
    try:
        custom = None
        if body.rule_text.strip():
            custom = {
                "rule_text": body.rule_text,
                "trigger_text": body.trigger_text,
                "expected_behavior": body.expected_behavior,
                "proposed_by": "user",
            }
        return {"rows": memory.propose_rules(body.pattern_id, custom=custom, store=store)}
    except MemoryError as exc:
        raise _memory_err(exc) from exc


class RuleOpIn(BaseModel):
    reason: str = ""
    rule_text: str = ""


@router.post("/api/memory/rules/{rule_id}/activate")
def memory_rule_activate(rule_id: str, body: RuleOpIn = RuleOpIn(), store: Store = Depends(get_store)):
    try:
        return memory.activate_rule(rule_id, store=store)
    except MemoryError as exc:
        raise _memory_err(exc) from exc


@router.post("/api/memory/rules/{rule_id}/reject")
def memory_rule_reject(rule_id: str, body: RuleOpIn = RuleOpIn(), store: Store = Depends(get_store)):
    try:
        return memory.reject_rule(rule_id, store=store)
    except MemoryError as exc:
        raise _memory_err(exc) from exc


@router.post("/api/memory/rules/{rule_id}/retire")
def memory_rule_retire(rule_id: str, body: RuleOpIn = RuleOpIn(), store: Store = Depends(get_store)):
    try:
        return memory.retire_rule(rule_id, reason=body.reason, store=store)
    except MemoryError as exc:
        raise _memory_err(exc) from exc


@router.post("/api/memory/rules/{rule_id}/revise")
def memory_rule_revise(rule_id: str, body: RuleOpIn, store: Store = Depends(get_store)):
    try:
        if not body.rule_text.strip():
            raise MemoryError("修订需要新的 rule_text")
        return memory.revise_rule(rule_id, body.rule_text, body.reason or "用户修订", store=store)
    except MemoryError as exc:
        raise _memory_err(exc) from exc


@router.post("/api/memory/rule-violations/{violation_id}/confirm")
def memory_violation_confirm(violation_id: str, store: Store = Depends(get_store)):
    try:
        return memory.confirm_rule_violation(violation_id, store=store)
    except MemoryError as exc:
        raise _memory_err(exc) from exc


@router.get("/api/memory/reminders")
def memory_reminders_get(decision_id: str = Query(...), store: Store = Depends(get_store)):
    return {"decision_id": decision_id, "rows": memory_reminders.reminders_for_decision(decision_id, store)}


class FeedbackIn(BaseModel):
    value: str


@router.post("/api/memory/reminders/{reminder_id}/feedback")
def memory_reminder_feedback(reminder_id: str, body: FeedbackIn, store: Store = Depends(get_store)):
    try:
        return memory_reminders.feedback(reminder_id, body.value, store=store)
    except MemoryError as exc:
        raise _memory_err(exc) from exc


@router.get("/api/memory/metrics")
def memory_metrics_get(store: Store = Depends(get_store)):
    return memory_metrics.product_metrics(store)


@router.get("/api/today", summary="每日入口：健康 + 未完成 + Recorder 入口数据")
def today_workbench(date: Optional[str] = Query(None), store: Store = Depends(get_store)):
    return today_workbench_model(_day(date), store)


@router.get("/api/product/metrics", summary="产品指标。默认排除 demo/test。")
def product_metrics_get(
    include_demo: bool = Query(False),
    store: Store = Depends(get_store),
):
    from core.product.metrics import collect
    return collect(store, include_demo=include_demo)


@router.get("/api/product/health", summary="System Health")
def product_health(store: Store = Depends(get_store)):
    from core.health.system import collect
    return collect(store)


@router.get("/api/review/decision/{decision_id}/context", summary="Decision Context 快照")
def decision_context(decision_id: str, store: Store = Depends(get_store)):
    return {
        "entry": _context_card(decision_id, store),
        "diff": _context_diff(decision_id, store),
    }


@router.get("/api/review/decision/{decision_id}/context/debug", summary="Context temporal debug")
def decision_context_debug(
    decision_id: str,
    snapshot_type: str = Query("ENTRY_CONTEXT"),
    store: Store = Depends(get_store),
):
    try:
        from core.context.store import debug as ctx_debug
        return ctx_debug(decision_id, snapshot_type, store)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


class ContextRetryIn(BaseModel):
    snapshot_type: str = "ENTRY_CONTEXT"


@router.post("/api/review/decision/{decision_id}/context/retry")
def decision_context_retry(decision_id: str, body: ContextRetryIn, store: Store = Depends(get_store)):
    from core.context.store import freeze
    row = freeze(decision_id, body.snapshot_type, store, retry=True)
    return {"snapshot": row, "original_captured_at": (row or {}).get("captured_at")}


def _context_card(decision_id: str, store: Store):
    try:
        from core.context.store import card as ctx_card
        return ctx_card(decision_id, store=store)
    except Exception as exc:  # noqa: BLE001
        return {"missing": True, "error": str(exc)}


def _context_diff(decision_id: str, store: Store):
    try:
        from core.context.store import diff
        return diff(decision_id, store)
    except Exception as exc:  # noqa: BLE001
        return {"changes": [], "error": str(exc)}
