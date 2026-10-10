"""Mistake → Pattern → Rule Candidate。写入只走这里。Lesson 不自动变 Rule。"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from core.review import lifecycle, repo
from core.review.guided import facts as factmod
from core.review.memory import fingerprint as fp
from core.review.memory import store as mstore
from core.review.memory import summarizer, validator
from core.review.memory.types import CANDIDATE_MIN, RULE_STATUSES
from core.review.memory.validator import MemoryError
from core.store import STORE, Store


def ingest_from_violations(decision_id: str, store: Store = STORE) -> Dict[str, Any]:
    raise MemoryError("Attribution Leakage：不能从 Process Violation 生成 Mistake Instance")


def ingest_reviewed(decision_id: str, store: Store = STORE) -> Dict[str, Any]:
    decision = repo.require_decision(decision_id, store)
    if decision["status"] != lifecycle.REVIEWED:
        return {"ok": False, "reason": "Decision 尚未 REVIEWED", "mistake": None}
    attrs = [a for a in repo.attributions(decision_id, store) if int(a.get("user_confirmed") or 0)]
    if not attrs:
        return {"ok": False, "reason": "attribution 未经用户确认", "mistake": None}
    latest = attrs[-1]
    primary = latest.get("primary_error") or ""
    reviews = repo.reviews(decision_id, store)
    review = reviews[-1] if reviews else {}
    ctx = factmod.build_context(decision_id, store)
    quadrant = ctx.get("quadrant") or ""
    if primary == "NONE" or quadrant == "纪律合格亏损":
        _record_fact(decision_id, quadrant, primary, store)
        return {
            "ok": True,
            "mistake": None,
            "pattern": None,
            "reason": "primary_error=NONE / 纪律合格亏损 不进入 Mistake Memory",
            "quadrant": quadrant,
        }
    existing = mstore.mistake_for_decision(decision_id, store)
    if existing:
        pattern = mstore.get_pattern(fp.pattern_id_for(existing["pattern_key"]), store)
        return {"ok": True, "mistake": existing, "pattern": pattern, "idempotent": True}

    lesson = (review.get("lesson") or "").strip()
    note = (review.get("user_note") or "").strip()
    emotion = fp.emotion_tag_from_text(
        lesson, note, decision.get("thesis") or "", decision.get("market_context") or "",
    )
    codes = list(ctx.get("violation_codes") or [])
    key = fp.pattern_key(primary, codes, emotion)
    mistake_id = "MI-{0}".format(decision_id)
    row = {
        "id": mistake_id,
        "decision_id": decision_id,
        "primary_error": primary,
        "contributing": fp.dumps(fp.loads_list(latest.get("contributing"))),
        "violation_codes": fp.dumps(codes),
        "lesson": lesson,
        "user_note": note,
        "market_context_tags": fp.dumps(fp.context_tags(decision.get("market_context") or "")),
        "behavior_tag": fp.behavior_tag(codes, primary),
        "emotion_tag": emotion,
        "symbol": decision.get("code") or "",
        "holding_period": decision.get("holding_period") or "",
        "earning_type": decision.get("earning_type") or "",
        "pattern_key": key,
        "created_at": repo.now(),
        "source": "review_confirmed",
    }
    mstore.insert("mistake_instance", row, store)
    pattern = _attach_pattern(row, store)
    _maybe_flag_rule_violation(row, pattern, store)
    return {"ok": True, "mistake": row, "pattern": pattern, "reason": ""}


def _record_fact(decision_id: str, quadrant: str, primary: str, store: Store) -> None:
    existing = store.query(
        "SELECT 1 FROM decision_pattern_fact WHERE decision_id = ?", (decision_id,),
    )
    if existing:
        return
    mstore.insert("decision_pattern_fact", {
        "id": mstore.next_fact_id(store),
        "decision_id": decision_id,
        "quadrant": quadrant,
        "primary_error": primary or "NONE",
        "created_at": repo.now(),
    }, store)


def _attach_pattern(mistake: Dict[str, Any], store: Store) -> Dict[str, Any]:
    key = mistake["pattern_key"]
    pid = fp.pattern_id_for(key)
    pattern = mstore.get_pattern(pid, store) or mstore.pattern_by_key(key, store)
    now = repo.now()
    if pattern is None:
        draft = summarizer.summarize([mistake])
        pattern = {
            "id": pid,
            "pattern_key": key,
            "status": "OBSERVED",
            "summary": draft["pattern_summary"],
            "common_trigger": draft["common_trigger"],
            "common_behavior": draft["common_behavior"],
            "occurrence_count": 1,
            "last_seen_at": now,
            "dismissed_evidence_hash": "",
            "created_at": now,
            "confirmed_at": "",
            "dismissed_at": "",
            "confirmed_by": "",
            "merged_into": "",
        }
        mstore.insert("pattern", pattern, store)
        mstore.add_evidence(pid, mistake["id"], mistake["decision_id"], store)
        return pattern

    pid = pattern["id"]
    mstore.add_evidence(pid, mistake["id"], mistake["decision_id"], store)
    evidence = mstore.evidence_of(pid, store)
    ids = [e["decision_id"] for e in evidence]
    count = len(evidence)
    status = pattern["status"]
    ev_hash = fp.evidence_hash(ids)
    if status == "DISMISSED":
        if ev_hash != (pattern.get("dismissed_evidence_hash") or ""):
            status = "CANDIDATE"
    elif status == "OBSERVED" and count >= CANDIDATE_MIN:
        status = "CANDIDATE"
    elif status == "CONFIRMED":
        status = "CONFIRMED"
    elif status == "CANDIDATE":
        status = "CANDIDATE"
    mistakes = _mistakes_for_pattern(pid, store)
    draft = summarizer.summarize(mistakes)
    fields = {
        "status": status,
        "occurrence_count": count,
        "last_seen_at": now,
        "summary": draft["pattern_summary"],
        "common_trigger": draft["common_trigger"],
        "common_behavior": draft["common_behavior"],
    }
    mstore.update("pattern", pid, fields, store)
    pattern.update(fields)
    return pattern


def _mistakes_for_pattern(pattern_id: str, store: Store) -> List[Dict[str, Any]]:
    out = []
    for row in mstore.evidence_of(pattern_id, store):
        item = mstore.get_mistake(row["mistake_id"], store)
        if item:
            out.append(item)
    return out


def _maybe_flag_rule_violation(mistake: Dict[str, Any], pattern: Dict[str, Any], store: Store) -> None:
    for rule in mstore.rules_for_pattern(pattern["id"], store):
        if rule.get("status") != "ACTIVE":
            continue
        confirmed_at = rule.get("confirmed_at") or ""
        if confirmed_at and mistake["created_at"] < confirmed_at:
            continue
        if mstore.violation_for(rule["id"], mistake["decision_id"], store):
            continue
        mstore.insert("rule_violation", {
            "id": mstore.next_violation_id(store),
            "rule_id": rule["id"],
            "decision_id": mistake["decision_id"],
            "detected_at": repo.now(),
            "evidence": fp.dumps({
                "pattern_id": pattern["id"],
                "mistake_id": mistake["id"],
                "primary_error": mistake["primary_error"],
                "violation_codes": fp.loads_list(mistake.get("violation_codes")),
            }),
            "user_confirmed": 0,
            "confirmed_at": "",
        }, store)


def confirm_pattern(pattern_id: str, operator: str = "user", store: Store = STORE) -> Dict[str, Any]:
    pattern = mstore.get_pattern(pattern_id, store)
    if pattern is None:
        raise MemoryError("找不到 pattern {0}".format(pattern_id))
    if pattern["status"] == "OBSERVED":
        raise MemoryError("单次 mistake 不能确认 Pattern")
    if int(pattern.get("occurrence_count") or 0) < CANDIDATE_MIN:
        raise MemoryError("证据不足两笔，不能 CONFIRMED")
    now = repo.now()
    mstore.update("pattern", pattern_id, {
        "status": "CONFIRMED",
        "confirmed_at": now,
        "confirmed_by": operator,
        "dismissed_at": "",
    }, store)
    try:
        from core.product.events import emit
        emit("PATTERN_CONFIRMED", "pattern", pattern_id, source=operator, store=store)
    except Exception:  # noqa: BLE001
        pass
    return mstore.get_pattern(pattern_id, store) or {}


def dismiss_pattern(pattern_id: str, operator: str = "user", store: Store = STORE) -> Dict[str, Any]:
    pattern = mstore.get_pattern(pattern_id, store)
    if pattern is None:
        raise MemoryError("找不到 pattern {0}".format(pattern_id))
    ids = [e["decision_id"] for e in mstore.evidence_of(pattern_id, store)]
    mstore.update("pattern", pattern_id, {
        "status": "DISMISSED",
        "dismissed_at": repo.now(),
        "dismissed_evidence_hash": fp.evidence_hash(ids),
        "confirmed_by": operator,
    }, store)
    try:
        from core.product.events import emit
        emit("PATTERN_DISMISSED", "pattern", pattern_id, source=operator, store=store)
    except Exception:  # noqa: BLE001
        pass
    return mstore.get_pattern(pattern_id, store) or {}


def merge_patterns(source_id: str, target_id: str, store: Store = STORE) -> Dict[str, Any]:
    source = mstore.get_pattern(source_id, store)
    target = mstore.get_pattern(target_id, store)
    if source is None or target is None:
        raise MemoryError("merge 需要两个已存在的 pattern")
    if source_id == target_id:
        raise MemoryError("不能与自己合并")
    before = {e["mistake_id"] for e in mstore.evidence_of(target_id, store)}
    source_ev = mstore.evidence_of(source_id, store)
    mstore.move_evidence(source_id, target_id, store)
    evidence = mstore.evidence_of(target_id, store)
    after = {e["mistake_id"] for e in evidence}
    if before - after:
        raise MemoryError("merge 丢失了 evidence")
    for row in source_ev:
        after.add(row["mistake_id"])
    mistakes = _mistakes_for_pattern(target_id, store)
    draft = summarizer.summarize(mistakes) if mistakes else {}
    count = len(evidence)
    status = target["status"]
    if status != "CONFIRMED":
        status = "CANDIDATE" if count >= CANDIDATE_MIN else "OBSERVED"
    fields = {
        "occurrence_count": count,
        "last_seen_at": repo.now(),
        "status": status,
        "summary": draft.get("pattern_summary") or target.get("summary") or "",
        "common_trigger": draft.get("common_trigger") or target.get("common_trigger") or "",
        "common_behavior": draft.get("common_behavior") or target.get("common_behavior") or "",
    }
    mstore.update("pattern", target_id, fields, store)
    mstore.update("pattern", source_id, {
        "status": "DISMISSED",
        "merged_into": target_id,
        "dismissed_at": repo.now(),
        "occurrence_count": 0,
        "dismissed_evidence_hash": fp.evidence_hash([e["decision_id"] for e in source_ev]),
    }, store)
    return {
        "target": mstore.get_pattern(target_id, store),
        "source": mstore.get_pattern(source_id, store),
        "evidence_count": count,
        "evidence_ids": [e["decision_id"] for e in evidence],
    }


def pattern_detail(pattern_id: str, store: Store = STORE) -> Dict[str, Any]:
    pattern = mstore.get_pattern(pattern_id, store)
    if pattern is None:
        raise MemoryError("找不到 pattern {0}".format(pattern_id))
    cards = []
    for ev in mstore.evidence_of(pattern_id, store):
        cards.append(_evidence_card(ev["decision_id"], store))
    rules = mstore.rules_for_pattern(pattern_id, store)
    return {
        "pattern": pattern,
        "evidence": cards,
        "rules": rules,
        "active_rule": next((r for r in rules if r.get("status") == "ACTIVE"), None),
        "summarizer": summarizer.summarize(_mistakes_for_pattern(pattern_id, store)),
    }


def _evidence_card(decision_id: str, store: Store) -> Dict[str, Any]:
    ctx = factmod.build_context(decision_id, store)
    attrs = repo.attributions(decision_id, store)
    confirmed = [a for a in attrs if int(a.get("user_confirmed") or 0)]
    latest = confirmed[-1] if confirmed else (attrs[-1] if attrs else {})
    plan = ctx.get("plan") or {}
    actual = ctx.get("actual") or {}
    outcome = ctx.get("outcome") or {}
    return {
        "decision_id": decision_id,
        "plan": {
            "target_size_pct": plan.get("target_size_pct"),
            "invalidation": plan.get("invalidation") or "",
            "entry_rule": plan.get("entry_rule") or "",
        },
        "actual": {
            "max_size_pct": actual.get("max_size_pct"),
            "first_price": actual.get("first_price"),
        },
        "outcome": {
            "realized_pct": (outcome or {}).get("realized_pct"),
            "gross_pnl": (outcome or {}).get("gross_pnl"),
        },
        "violations": ctx.get("violation_codes") or [],
        "attribution": latest.get("primary_error") or "",
        "lesson": ctx.get("lesson") or "",
        "quadrant": ctx.get("quadrant") or "",
    }


def list_patterns(store: Store = STORE) -> List[Dict[str, Any]]:
    out = []
    for row in mstore.list_patterns(store):
        rules = mstore.rules_for_pattern(row["id"], store)
        active = [r for r in rules if r.get("status") == "ACTIVE"]
        item = dict(row)
        item["evidence_count"] = int(row.get("occurrence_count") or 0)
        item["active_rule"] = bool(active)
        item["active_rule_id"] = active[0]["id"] if active else ""
        out.append(item)
    return out


def propose_rules(
    pattern_id: str,
    custom: Optional[Dict[str, Any]] = None,
    operator: str = "system",
    store: Store = STORE,
) -> List[Dict[str, Any]]:
    pattern = mstore.get_pattern(pattern_id, store)
    if pattern is None:
        raise MemoryError("找不到 pattern {0}".format(pattern_id))
    if pattern["status"] != "CONFIRMED":
        raise MemoryError("只有 CONFIRMED Pattern 才能生成 Rule Candidate")
    mistakes = _mistakes_for_pattern(pattern_id, store)
    evidence = [m["decision_id"] for m in mistakes]
    drafts = []
    if custom:
        drafts = [custom]
    else:
        drafts = summarizer.rule_candidates(pattern, mistakes)
    created = []
    scope = {
        "error_type": (pattern["pattern_key"].split("|") + [""])[0],
        "violation_code": ((pattern["pattern_key"].split("|") + ["", ""])[1].split(",") + [""])[0],
        "emotion_tag": (pattern["pattern_key"].split("|") + ["", "", ""])[2] if len(pattern["pattern_key"].split("|")) > 2 else "",
        "symbol": "",
        "earning_type": "",
        "market_context": "",
    }
    for draft in drafts:
        text = (draft.get("rule_text") or "").strip()
        trigger = (draft.get("trigger_text") or "").strip()
        expected = (draft.get("expected_behavior") or "").strip()
        ev = draft.get("evidence_decision_ids") or evidence
        validator.assert_rule_ok(text, trigger, expected, ev)
        rid = mstore.next_rule_id(store)
        row = {
            "id": rid,
            "pattern_id": pattern_id,
            "rule_text": text,
            "trigger_text": trigger,
            "expected_behavior": expected,
            "scope_json": fp.dumps(scope),
            "evidence_count": len(ev),
            "evidence_decision_ids": fp.dumps(ev),
            "proposed_by": draft.get("proposed_by") or operator,
            "status": "PROPOSED",
            "created_at": repo.now(),
            "confirmed_at": "",
            "retired_at": "",
            "retire_reason": "",
        }
        mstore.insert("rule", row, store)
        _revise(rid, "", text, "", "PROPOSED", "提出规则候选", operator, store)
        created.append(row)
    return created


def activate_rule(rule_id: str, operator: str = "user", store: Store = STORE) -> Dict[str, Any]:
    rule = mstore.get_rule(rule_id, store)
    if rule is None:
        raise MemoryError("找不到 rule {0}".format(rule_id))
    if rule["status"] not in ("PROPOSED", "DRAFT"):
        raise MemoryError("只有 PROPOSED / DRAFT 能激活，当前是 {0}".format(rule["status"]))
    pattern = mstore.get_pattern(rule["pattern_id"], store)
    if not pattern or pattern["status"] != "CONFIRMED":
        raise MemoryError("Active Rule 必须来自 CONFIRMED Pattern")
    validator.assert_rule_ok(
        rule["rule_text"], rule["trigger_text"], rule["expected_behavior"],
        fp.loads_list(rule.get("evidence_decision_ids")),
    )
    now = repo.now()
    mstore.update("rule", rule_id, {"status": "ACTIVE", "confirmed_at": now}, store)
    _revise(rule_id, rule["rule_text"], rule["rule_text"], rule["status"], "ACTIVE",
            "用户确认 Active Rule", operator, store)
    try:
        from core.product.events import emit
        emit("RULE_ACTIVATED", "rule", rule_id, source=operator, store=store)
    except Exception:  # noqa: BLE001
        pass
    return mstore.get_rule(rule_id, store) or {}


def reject_rule(rule_id: str, operator: str = "user", store: Store = STORE) -> Dict[str, Any]:
    return _set_rule_status(rule_id, "REJECTED", "用户拒绝规则候选", operator, store)


def retire_rule(rule_id: str, reason: str = "", operator: str = "user", store: Store = STORE) -> Dict[str, Any]:
    rule = _set_rule_status(rule_id, "RETIRED", reason or "用户认为不再适用", operator, store)
    mstore.update("rule", rule_id, {"retired_at": repo.now(), "retire_reason": reason or "用户认为不再适用"}, store)
    return mstore.get_rule(rule_id, store) or rule


def revise_rule(rule_id: str, new_text: str, reason: str, operator: str = "user", store: Store = STORE) -> Dict[str, Any]:
    rule = mstore.get_rule(rule_id, store)
    if rule is None:
        raise MemoryError("找不到 rule {0}".format(rule_id))
    validator.assert_rule_ok(
        new_text, rule["trigger_text"], rule["expected_behavior"],
        fp.loads_list(rule.get("evidence_decision_ids")),
    )
    old = rule["rule_text"]
    mstore.update("rule", rule_id, {"rule_text": new_text}, store)
    _revise(rule_id, old, new_text, rule["status"], rule["status"], reason, operator, store)
    return mstore.get_rule(rule_id, store) or {}


def _set_rule_status(rule_id: str, status: str, reason: str, operator: str, store: Store) -> Dict[str, Any]:
    if status not in RULE_STATUSES:
        raise MemoryError("未知 rule status {0}".format(status))
    rule = mstore.get_rule(rule_id, store)
    if rule is None:
        raise MemoryError("找不到 rule {0}".format(rule_id))
    if rule["status"] == status:
        return rule
    mstore.update("rule", rule_id, {"status": status}, store)
    _revise(rule_id, rule["rule_text"], rule["rule_text"], rule["status"], status, reason, operator, store)
    try:
        from core.product.events import emit
        if status == "REJECTED":
            emit("RULE_REJECTED", "rule", rule_id, source=operator, store=store)
        elif status == "RETIRED":
            emit("RULE_RETIRED", "rule", rule_id, source=operator, store=store)
    except Exception:  # noqa: BLE001
        pass
    return mstore.get_rule(rule_id, store) or {}


def _revise(rule_id: str, old_text: str, new_text: str, old_status: str, new_status: str,
            reason: str, operator: str, store: Store) -> None:
    mstore.insert("rule_revision", {
        "id": mstore.next_revision_id(store),
        "rule_id": rule_id,
        "old_text": old_text,
        "new_text": new_text,
        "old_status": old_status,
        "new_status": new_status,
        "reason": reason,
        "changed_at": repo.now(),
        "changed_by": operator,
    }, store)


def confirm_rule_violation(violation_id: str, operator: str = "user", store: Store = STORE) -> Dict[str, Any]:
    rows = store.query("SELECT * FROM rule_violation WHERE id = ?", (violation_id,))
    if not rows:
        raise MemoryError("找不到 rule_violation {0}".format(violation_id))
    mstore.update("rule_violation", violation_id, {
        "user_confirmed": 1,
        "confirmed_at": repo.now(),
    }, store)
    return store.query("SELECT * FROM rule_violation WHERE id = ?", (violation_id,))[0]


def list_rules(store: Store = STORE) -> List[Dict[str, Any]]:
    out = []
    for row in mstore.list_rules(store=store):
        item = dict(row)
        vios = mstore.violations_of(row["id"], store)
        item["violation_count"] = len(vios)
        item["confirmed_violation_count"] = sum(1 for v in vios if int(v.get("user_confirmed") or 0))
        item["last_triggered"] = vios[-1]["detected_at"] if vios else ""
        item["revisions"] = len(mstore.revisions_of(row["id"], store))
        out.append(item)
    return out
