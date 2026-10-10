"""Recorder 编排：Envelope → LLM → Grounding → Draft →（确认后）Write Gate。"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from core.llm.client import LLMClient, LLMError, OpenAICompatibleClient
from core.review import flags, lifecycle, repo
from core.review.origin import create_origin
from core.review.recorder import grounding, store as rstore, validator
from core.review.recorder.parser import ParseError, parse_json
from core.review.recorder.prompts import SYSTEM_PROMPT, build_user_prompt
from core.review.recorder.schema import RECORDER_JSON_SCHEMA
from core.review.recorder.types import (
    Envelope,
    PROMPT_VERSION,
    RecorderDraft,
    SCHEMA_VERSION,
)
from core.store import STORE, Store
from core.symbols import resolve_name

WRITE_BLOCKED = "WRITE_BLOCKED"


def _event(kind: str, entity_type: str, entity_id: str, store: Store = STORE, **meta: Any) -> None:
    try:
        from core.product.events import emit
        emit(kind, entity_type, entity_id, source="recorder", metadata=meta, store=store)
    except Exception:  # noqa: BLE001
        return
CRITICAL_COMPARE = (
    "symbol", "thesis", "entry_rule", "invalidation", "target_size_pct", "holding_period",
)


def _primary_client(llm: Optional[LLMClient]) -> LLMClient:
    if llm is not None:
        return llm
    mode = flags.recorder_remote_mode()
    if mode == "remote_primary" and flags.remote_primary_allowed() and flags.has_remote_key():
        return OpenAICompatibleClient()
    from core.review.recorder.heuristic import HeuristicLLM
    return HeuristicLLM()


def _shadow_client() -> Optional[LLMClient]:
    if flags.recorder_remote_mode() != "remote_shadow":
        return None
    if not flags.has_remote_key():
        return None
    return OpenAICompatibleClient()


def _field_map(draft: Dict[str, Any]) -> Dict[str, Any]:
    plan = draft.get("plan") or {}
    return {
        "symbol": (draft.get("symbol") or {}).get("value"),
        "thesis": (draft.get("thesis") or {}).get("value"),
        "entry_rule": (plan.get("entry_rule") or {}).get("value"),
        "invalidation": (plan.get("invalidation") or {}).get("value"),
        "target_size_pct": (plan.get("target_size_pct") or {}).get("value"),
        "holding_period": (plan.get("holding_period") or {}).get("value"),
    }


def _run_shadow(input_id: str, draft_id: str, user_prompt: str, primary: Dict[str, Any], store: Store) -> None:
    client = _shadow_client()
    if client is None:
        return
    try:
        raw = client.generate_structured(
            SYSTEM_PROMPT, user_prompt, RECORDER_JSON_SCHEMA, temperature=0, timeout=45,
        )
        parsed, _ = parse_json(raw)
        shadow = parsed.as_dict()
    except Exception as exc:  # noqa: BLE001 — shadow 失败不得影响主路径
        rstore.insert_shadow(
            input_id, draft_id, getattr(client, "name", "remote"),
            str(exc), {}, [], ["parse_failed"], [],
            [{"detail": str(exc)}], store,
        )
        return
    primary_map = _field_map(primary)
    shadow_map = _field_map(shadow)
    same, diff, critical = [], [], []
    for key in CRITICAL_COMPARE:
        a, b = primary_map.get(key), shadow_map.get(key)
        if str(a) == str(b):
            same.append(key)
        else:
            diff.append(key)
            if key in ("invalidation", "target_size_pct", "symbol", "holding_period", "entry_rule"):
                critical.append({"field": key, "primary": a, "shadow": b})
    envelope = Envelope(raw_text=json.loads(user_prompt).get("envelope", {}).get("raw_text") or "")
    _, issues = grounding.check(parsed, envelope)
    rstore.insert_shadow(
        input_id, draft_id, getattr(client, "name", "remote"),
        raw, shadow, same, diff, critical,
        [i.as_dict() for i in issues], store,
    )


class RecorderError(repo.ReviewError):
    pass


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _open_drafts(code: str, store: Store) -> List[Dict[str, Any]]:
    return rstore.open_drafts_for(code, store)


def resolve_origin(code: str, witnessed_at: str, mode: str, store: Store) -> str:
    """创建时不再看同日未关联成交。mode=posthoc 才 POST_HOC，其余 EX_ANTE 待结算。"""
    from core.review.origin import create_origin
    return create_origin(mode)["origin"]


def _apply_edits(draft: RecorderDraft, edits: Optional[Dict[str, Any]]) -> RecorderDraft:
    if not edits:
        return draft
    mapping = {
        "thesis": draft.thesis,
        "market_context": draft.market_context,
        "symbol": draft.symbol,
        "entry_rule": draft.plan.entry_rule,
        "invalidation": draft.plan.invalidation,
        "target_size_pct": draft.plan.target_size_pct,
        "holding_period": draft.plan.holding_period,
    }
    for key, value in edits.items():
        if key == "expectation":
            if value:
                if draft.expectations:
                    draft.expectations[0].raw_text = str(value)
                    draft.expectations[0].source_quote = str(value)
                    draft.expectations[0].provenance = "USER_EXPLICIT"
                else:
                    from core.review.recorder.types import ExpectationDraft
                    draft.expectations.append(ExpectationDraft(
                        raw_text=str(value), source_quote=str(value),
                    ))
            continue
        target = mapping.get(key)
        if target is None:
            continue
        target.value = value
        target.source_quote = str(value) if value is not None else None
        target.provenance = "USER_EXPLICIT"
    return draft


def _log_edits(draft_id: str, before: Dict[str, Any], after: Dict[str, Any], store: Store) -> None:
    keys = (
        "thesis", "market_context", "symbol",
        "plan.entry_rule", "plan.invalidation", "plan.target_size_pct", "plan.holding_period",
    )

    def pick(payload: Dict[str, Any], path: str) -> Any:
        cur: Any = payload
        for part in path.split("."):
            if not isinstance(cur, dict):
                return None
            cur = cur.get(part)
        if isinstance(cur, dict) and "value" in cur:
            return cur.get("value")
        return cur

    for path in keys:
        old, new = pick(before, path), pick(after, path)
        if str(old) == str(new):
            continue
        with store.connect() as conn:
            conn.execute(
                "INSERT INTO revision (table_name, row_id, field, old_value, new_value,"
                " reason, changed_at, changed_by, source) VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    "recorder_draft", draft_id, path, str(old), str(new),
                    "用户确认前修改 Recorder 草稿", repo.now(), "user", "user",
                ),
            )


def parse(
    raw_text: str,
    known_symbol: str = "",
    known_company: str = "",
    source: str = "web",
    mode: str = "premarket",
    account: str = "",
    draft_id: str = "",
    recorded_at: str = "",
    llm: Optional[LLMClient] = None,
    store: Store = STORE,
) -> Dict[str, Any]:
    """立刻落 recorder_input（见证），再抽草稿。不写 Decision。"""
    text = (raw_text or "").strip()
    if not text:
        raise RecorderError("原文为空")
    witnessed = recorded_at or _now()
    envelope = Envelope(
        raw_text=text,
        recorded_at=witnessed,
        source=source,
        mode=mode,
        known_symbol=known_symbol or "",
        known_company=known_company or "",
        account=account or "",
        draft_id=draft_id or "",
    )
    input_id = rstore.insert_input(
        text, witnessed, source, mode, known_symbol, known_company, account, draft_id,
        store,
    )
    _event("RECORDER_INPUT_RECEIVED", "recorder_input", input_id, store=store, source=source)

    from core.review.recorder.heuristic import resolve_symbols

    code_hint = known_symbol or (resolve_symbols(text)[0][1] if resolve_symbols(text) else "")
    open_rows = _open_drafts(code_hint, store) if code_hint else []
    client = _primary_client(llm)
    user_prompt = build_user_prompt(envelope, open_rows)
    raw_out = ""
    try:
        raw_out = client.generate_structured(
            SYSTEM_PROMPT, user_prompt, RECORDER_JSON_SCHEMA,
            temperature=0, timeout=45,
        )
        parsed, raw_obj = parse_json(raw_out)
    except (ParseError, LLMError, json.JSONDecodeError) as exc:
        draft_id_out = rstore.insert_draft(
            input_id, raw_out or str(exc), {},
            "FAILED", "PARSE_FAILED", [{"detail": str(exc)}],
            PROMPT_VERSION, SCHEMA_VERSION, getattr(client, "name", "unknown"), 0,
            store=store,
        )
        return {
            "input_id": input_id,
            "draft_id": draft_id_out,
            "status": "FAILED",
            "witnessed_at": witnessed,
            "error": str(exc),
            "draft": None,
        }

    parsed = validator.refresh_missing(parsed, text)
    ok, issues = grounding.check(parsed, envelope)
    needs = any(i.code == grounding.NEEDS_CONFIRMATION for i in issues)
    if parsed.intent in ("CHITCHAT", "UNSUPPORTED"):
        status, vstat = "VALIDATED", parsed.intent
        errors: List[Any] = []
    elif not ok:
        status, vstat = "FAILED", "GROUNDING_FAILED"
        errors = [i.as_dict() for i in issues]
    else:
        status = "NEEDS_EDIT" if parsed.missing_fields or needs else "VALIDATED"
        vstat = "NEEDS_CONFIRMATION" if needs else "OK"
        errors = [i.as_dict() for i in issues] if needs else []

    origin_meta = create_origin(mode)
    origin = origin_meta["origin"]
    out_id = rstore.insert_draft(
        input_id, raw_out, parsed.as_dict(),
        status, vstat, errors,
        PROMPT_VERSION, SCHEMA_VERSION, getattr(client, "name", "unknown"), 0,
        origin_resolved=origin, store=store,
    )
    try:
        _run_shadow(input_id, out_id, user_prompt, parsed.as_dict(), store)
    except Exception:
        pass
    ask = None
    if parsed.intent == "CREATE_DECISION":
        if "invalidation" in parsed.missing_fields:
            ask = "你还没有提供失效条件，要补吗？"
        elif "target_size" in parsed.missing_fields:
            ask = "你还没有提供目标仓位，要补吗？"
        elif "holding_period" in parsed.missing_fields:
            ask = "你还没有提供持有周期，要补吗？"
        elif "expectation" in parsed.missing_fields:
            ask = "你还没有提供可验证预期，要补吗？"
    return {
        "input_id": input_id,
        "draft_id": out_id,
        "status": status,
        "witnessed_at": witnessed,
        "origin": origin,
        "model": getattr(client, "name", "unknown"),
        "prompt_version": PROMPT_VERSION,
        "schema_version": SCHEMA_VERSION,
        "grounding_ok": ok,
        "issues": [i.as_dict() for i in issues],
        "draft": parsed.as_dict(),
        "ask": ask,
        "error": None if ok or parsed.intent in ("CHITCHAT", "UNSUPPORTED") else "GROUNDING_FAILED",
    }


def confirm(
    draft_id: str,
    confirmed: bool = False,
    edits: Optional[Dict[str, Any]] = None,
    operator: str = "user",
    store: Store = STORE,
) -> Dict[str, Any]:
    """Write Gate。没有 confirmed 就没有 Decision。"""
    if not confirmed:
        raise RecorderError("没有用户确认，禁止写入 Decision")
    row = rstore.require_draft(draft_id, store)
    if row["status"] in ("FAILED", "REJECTED"):
        raise RecorderError("草稿状态 {0}，Write Gate 拒绝".format(row["status"]))
    if row["status"] == "CONFIRMED" and row.get("decision_id"):
        return {"decision_id": row["decision_id"], "status": "CONFIRMED", "idempotent": True}

    event = rstore.get_input(row["input_event_id"], store)
    if event is None:
        raise RecorderError("找不到对应的 recorder_input")
    envelope = Envelope(
        raw_text=event["raw_text"],
        recorded_at=event["received_at"],
        source=event.get("source") or "web",
        mode=event.get("mode") or "",
        known_symbol=event.get("known_symbol") or "",
        known_company=event.get("known_company") or "",
        account=event.get("account") or "",
        draft_id=event.get("draft_id") or "",
    )
    parsed = RecorderDraft.from_dict(json.loads(row["parsed_json"] or "{}"))
    before = parsed.as_dict()
    parsed = _apply_edits(parsed, edits)
    parsed = validator.refresh_missing(parsed, envelope.raw_text)
    edited_fields = set((edits or {}).keys())
    ok, issues = grounding.check(parsed, envelope)
    # 用户手改的字段不再要求原话子串
    if not ok:
        leftover = [i for i in issues if i.field.split("[")[0].replace("plan.", "") not in edited_fields
                    and i.field not in edited_fields]
        # map entry_rule etc.
        renamed = []
        for issue in leftover:
            short = issue.field.replace("plan.", "").split("[")[0]
            if short in edited_fields or issue.field in edited_fields:
                continue
            renamed.append(issue)
        ok = not renamed
        issues = renamed
    if not ok:
        rstore.update_draft(draft_id, {
            "status": "FAILED",
            "validation_status": "GROUNDING_FAILED",
            "validation_errors": json.dumps([i.as_dict() for i in issues], ensure_ascii=False),
        }, store)
        raise RecorderError("GROUNDING_FAILED：{0}".format("; ".join(i.detail for i in issues)))

    if parsed.intent == "CHITCHAT":
        rstore.update_draft(draft_id, {
            "status": "REJECTED", "confirmed_at": repo.now(), "confirmed_by": operator,
        }, store)
        _event("RECORDER_DRAFT_REJECTED", "recorder_draft", draft_id, store=store, intent="CHITCHAT")
        return {"decision_id": None, "status": "REJECTED", "intent": "CHITCHAT",
                "note": "闲聊不创建 Decision"}
    if parsed.intent == "UNSUPPORTED":
        rstore.update_draft(draft_id, {
            "status": "REJECTED", "confirmed_at": repo.now(), "confirmed_by": operator,
        }, store)
        _event("RECORDER_DRAFT_REJECTED", "recorder_draft", draft_id, store=store, intent="UNSUPPORTED")
        return {"decision_id": None, "status": "REJECTED", "intent": "UNSUPPORTED",
                "note": "Recorder 不回答荐股"}

    _log_edits(draft_id, before, parsed.as_dict(), store)
    origin_meta = create_origin(envelope.mode)
    origin = origin_meta["origin"]
    ready, still_missing = validator.can_plan(parsed)

    if parsed.intent == "UPDATE_DRAFT":
        target = envelope.draft_id
        if not target:
            opens = _open_drafts(str(parsed.symbol.value or envelope.known_symbol or ""), store)
            target = opens[0]["id"] if opens else ""
        if not target:
            raise RecorderError("UPDATE_DRAFT 但没有可改的 Decision")
        if parsed.thesis.filled():
            repo.amend("decision", target, "thesis", parsed.thesis.value,
                       "Recorder 用户确认后更新 thesis", operator, store=store)
        if (parsed.plan.entry_rule.filled() or parsed.plan.invalidation.filled()
                or parsed.plan.target_size_pct.filled() or parsed.plan.holding_period.filled()):
            size = parsed.plan.target_size_pct.value
            repo.add_plan(
                target,
                entry_rule=str(parsed.plan.entry_rule.value or ""),
                invalidation=str(parsed.plan.invalidation.value or ""),
                target_size_pct=float(size) if size is not None else None,
                holding_period=str(parsed.plan.holding_period.value or ""),
                reason_for_revision="Recorder 用户确认后修订计划",
                source="user", created_by=operator, store=store,
            )
        rstore.update_draft(draft_id, {
            "status": "CONFIRMED",
            "confirmed_at": repo.now(),
            "confirmed_by": operator,
            "decision_id": target,
            "origin_resolved": origin,
            "edit_json": json.dumps(edits or {}, ensure_ascii=False),
            "parsed_json": json.dumps(parsed.as_dict(), ensure_ascii=False),
        }, store)
        reminders = []
        try:
            from core.review.memory.reminders import issue_for_new_decision

            reminders = issue_for_new_decision(target, envelope.raw_text, parsed, store)
        except Exception:  # noqa: BLE001
            reminders = []
        _event("RECORDER_DRAFT_CONFIRMED", "recorder_draft", draft_id, store=store, decision_id=target)
        return {"decision_id": target, "status": "CONFIRMED", "intent": "UPDATE_DRAFT",
                "origin": origin, "reminders": reminders}

    code = str(parsed.symbol.value or envelope.known_symbol or "")
    if not code:
        raise RecorderError("没有标的，不能创建 Decision。可继续补字段，但不能写库。")
    name = envelope.known_company or resolve_name(code)
    thesis = str(parsed.thesis.value or "")
    did = repo.create_decision(
        code=code, name=name, thesis=thesis,
        holding_period=str(parsed.plan.holding_period.value or ""),
        market_context=str(parsed.market_context.value or ""),
        opened_on=(event["received_at"] or "")[:10],
        account=envelope.account,
        source="user", created_by=operator,
        origin=origin,
        origin_status=origin_meta["origin_status"],
        origin_confidence=origin_meta["origin_confidence"],
        witnessed_at=event["received_at"],
        recorder_input_id=event["id"],
        recorder_draft_id=draft_id,
        store=store,
    )
    for exp in parsed.expectations:
        if exp.raw_text.strip():
            repo.add_expectation(did, exp.raw_text, source="user", created_by=operator, store=store)
    if (parsed.plan.entry_rule.filled() or parsed.plan.invalidation.filled()
            or parsed.plan.target_size_pct.filled() or parsed.plan.holding_period.filled()):
        size = parsed.plan.target_size_pct.value
        repo.add_plan(
            did,
            entry_rule=str(parsed.plan.entry_rule.value or ""),
            invalidation=str(parsed.plan.invalidation.value or ""),
            target_size_pct=float(size) if size is not None else None,
            holding_period=str(parsed.plan.holding_period.value or ""),
            source="user", created_by=operator, store=store,
        )
    promoted = None
    if origin == "EX_ANTE" and ready:
        try:
            promoted = repo.transition(did, lifecycle.PLANNED, "Recorder 确认后字段齐全",
                                       operator, "user", store)
        except (lifecycle.GuardFailed, lifecycle.IllegalTransition) as exc:
            promoted = {"error": str(exc)}

    rstore.update_draft(draft_id, {
        "status": "CONFIRMED",
        "confirmed_at": repo.now(),
        "confirmed_by": operator,
        "decision_id": did,
        "origin_resolved": origin,
        "edit_json": json.dumps(edits or {}, ensure_ascii=False),
        "parsed_json": json.dumps(parsed.as_dict(), ensure_ascii=False),
    }, store)
    decision = repo.require_decision(did, store)
    reminders: List[Any] = []
    try:
        from core.review.memory.reminders import issue_for_new_decision

        reminders = issue_for_new_decision(did, envelope.raw_text, parsed, store)
    except Exception as exc:  # noqa: BLE001 — Write Gate 已通过，提醒失败不得回滚 Decision
        reminders = []
        reminder_error = str(exc)
    else:
        reminder_error = ""
    _event("RECORDER_DRAFT_CONFIRMED", "recorder_draft", draft_id, store=store, decision_id=did)
    return {
        "decision_id": did,
        "status": decision["status"],
        "origin": origin,
        "intent": parsed.intent,
        "missing_fields": parsed.missing_fields,
        "promoted": promoted,
        "witnessed_at": event["received_at"],
        "prompt_version": row["prompt_version"],
        "model": row["model"],
        "reminders": reminders,
        "reminder_error": reminder_error,
    }


def reject(draft_id: str, operator: str = "user", store: Store = STORE) -> Dict[str, Any]:
    rstore.require_draft(draft_id, store)
    rstore.update_draft(draft_id, {
        "status": "REJECTED",
        "confirmed_at": repo.now(),
        "confirmed_by": operator,
    }, store)
    _event("RECORDER_DRAFT_REJECTED", "recorder_draft", draft_id, store=store)
    return {"draft_id": draft_id, "status": "REJECTED"}


CRITICAL_EDIT_KEYS = {
    "symbol", "invalidation", "target_size", "target_size_pct", "entry_rule",
    "holding_period", "stop", "stop_price", "size",
}


def _parse_stamp(raw: str) -> Optional[datetime]:
    text = (raw or "").replace(" ", "T")
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M"):
        try:
            return datetime.strptime(text[:19], fmt)
        except ValueError:
            continue
    return None


def human_edit_rate(prompt_version: str = "", store: Store = STORE) -> Dict[str, Any]:
    return online_metrics(prompt_version=prompt_version, store=store)


def online_metrics(prompt_version: str = "", store: Store = STORE) -> Dict[str, Any]:
    sql = "SELECT * FROM recorder_draft"
    params: List[Any] = []
    if prompt_version:
        sql += " WHERE prompt_version = ?"
        params.append(prompt_version)
    rows = store.query(sql, params)
    confirmed = [r for r in rows if r.get("status") == "CONFIRMED"]
    rejected = [r for r in rows if r.get("status") == "REJECTED"]
    changed = 0
    extracted = 0
    critical_edits = 0
    critical_extracted = 0
    missing_total = 0
    confirm_seconds: List[float] = []
    for row in confirmed:
        edits = json.loads(row.get("edit_json") or "{}") or {}
        parsed = json.loads(row.get("parsed_json") or "{}")
        n = 0
        for key in ("thesis", "symbol", "market_context"):
            if (parsed.get(key) or {}).get("value") not in (None, ""):
                n += 1
        plan = parsed.get("plan") or {}
        for key in ("entry_rule", "invalidation", "target_size_pct", "holding_period"):
            if (plan.get(key) or {}).get("value") not in (None, ""):
                n += 1
                critical_extracted += 1
        if (parsed.get("symbol") or {}).get("value") not in (None, ""):
            critical_extracted += 1
        extracted += n
        changed += len(edits)
        for key in edits:
            if key in CRITICAL_EDIT_KEYS or key.replace("plan.", "") in CRITICAL_EDIT_KEYS:
                critical_edits += 1
        missing_total += len(parsed.get("missing_fields") or [])
        start = _parse_stamp(row.get("created_at") or "")
        end = _parse_stamp(row.get("confirmed_at") or "")
        if start and end:
            confirm_seconds.append((end - start).total_seconds())
    n_confirmed = len(confirmed)
    n_decided = n_confirmed + len(rejected)
    avg_confirm = round(sum(confirm_seconds) / len(confirm_seconds), 2) if confirm_seconds else None
    return {
        "prompt_version": prompt_version or "all",
        "drafts_n": len(rows),
        "confirmed_n": n_confirmed,
        "rejected_n": len(rejected),
        "draft_confirm_rate": round(n_confirmed / n_decided, 4) if n_decided else None,
        "draft_reject_rate": round(len(rejected) / n_decided, 4) if n_decided else None,
        "field_changed_by_user": changed,
        "agent_extracted_fields": extracted,
        "rate": round(changed / extracted, 4) if extracted else None,
        "human_edit_rate": round(changed / extracted, 4) if extracted else None,
        "critical_field_edit_rate": round(critical_edits / critical_extracted, 4) if critical_extracted else None,
        "critical_fields_edited": critical_edits,
        "missing_field_count": missing_total,
        "time_to_confirm_seconds": avg_confirm,
        "recorder_mode": flags.recorder_remote_mode(),
        "remote_primary_allowed": flags.remote_primary_allowed(),
    }
