"""产品指标。每个指标显式声明 numerator / denominator / exclude。默认排除 demo/test。"""
from __future__ import annotations

import json
from datetime import datetime
from statistics import median
from typing import Any, Dict, List, Optional

from core.review import flags
from core.review.memory import metrics as mem_metrics
from core.review.memory import store as mstore
from core.review.recorder import service as recorder
from core.store import STORE, Store

from core.product.events import list_events


def _rate(num: int, den: int):
    if den <= 0:
        return None
    return round(num / float(den), 4)


def _metric(name: str, value, numerator: int, numerator_def: str,
            denominator: int, denominator_def: str, exclude: List[str],
            excluded_n: int = 0, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    row = {
        "name": name,
        "value": value,
        "numerator": numerator,
        "numerator_def": numerator_def,
        "denominator": denominator,
        "denominator_def": denominator_def,
        "exclude": exclude,
        "excluded_n": excluded_n,
    }
    if extra:
        row.update(extra)
    return row


def _is_excluded_row(row: Dict[str, Any]) -> bool:
    if int(row.get("demo") or 0):
        return True
    env = (row.get("environment") or "").lower()
    return env in ("test", "eval", "demo")


def _parse_stamp(raw: str):
    text = (raw or "").replace(" ", "T")
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M"):
        try:
            return datetime.strptime(text[:19], fmt)
        except ValueError:
            continue
    return None


def _prod_decisions(store: Store, include_demo: bool) -> List[Dict[str, Any]]:
    rows = store.query("SELECT * FROM decision")
    if include_demo:
        return rows
    return [r for r in rows if not _is_excluded_row(r)]


def recorder_metrics(store: Store = STORE, include_demo: bool = False) -> Dict[str, Any]:
    drafts = store.query("SELECT * FROM recorder_draft")
    inputs = {r["id"]: r for r in store.query("SELECT * FROM recorder_input")}
    kept, excluded_n = [], 0
    for d in drafts:
        event = inputs.get(d.get("input_event_id") or "")
        source = (event or {}).get("source") or ""
        demo = source in ("eval", "test", "demo", "shadow")
        if (not include_demo) and demo:
            excluded_n += 1
            continue
        kept.append(d)
    confirmed = [d for d in kept if d.get("status") == "CONFIRMED"]
    rejected = [d for d in kept if d.get("status") == "REJECTED"]
    decided = confirmed + rejected
    missing_vals = []
    times = []
    for d in kept:
        try:
            parsed = json.loads(d.get("parsed_json") or "{}")
        except json.JSONDecodeError:
            parsed = {}
        missing_vals.append(len(parsed.get("missing_fields") or []))
        start = _parse_stamp(d.get("created_at") or "")
        end = _parse_stamp(d.get("confirmed_at") or "")
        if start and end and d.get("status") == "CONFIRMED":
            times.append((end - start).total_seconds())
    online = recorder.online_metrics(store=store)
    exclude = ["demo", "test", "eval", "shadow"]
    return {
        "draft_confirm_rate": _metric(
            "draft_confirm_rate", _rate(len(confirmed), len(decided)),
            len(confirmed), "confirmed drafts",
            len(decided), "confirmed + rejected drafts",
            exclude, excluded_n,
        ),
        "draft_reject_rate": _metric(
            "draft_reject_rate", _rate(len(rejected), len(decided)),
            len(rejected), "rejected drafts",
            len(decided), "confirmed + rejected drafts",
            exclude, excluded_n,
        ),
        "critical_field_edit_rate": _metric(
            "critical_field_edit_rate",
            online.get("critical_field_edit_rate"),
            int(online.get("critical_edits") or 0),
            "drafts whose critical fields were edited before confirm",
            int(online.get("critical_extracted") or 0),
            "drafts that extracted at least one critical field",
            exclude, excluded_n,
        ),
        "average_missing_fields": _metric(
            "average_missing_fields",
            round(sum(missing_vals) / len(missing_vals), 4) if missing_vals else None,
            sum(missing_vals), "sum of missing_fields on kept drafts",
            len(missing_vals), "kept drafts after excluding demo/test",
            exclude, excluded_n,
        ),
        "time_to_confirm_seconds": _metric(
            "time_to_confirm",
            round(sum(times) / len(times), 2) if times else None,
            len(times), "confirmed drafts with both created_at and confirmed_at",
            len(confirmed), "confirmed drafts",
            exclude, excluded_n,
            extra={"median": round(median(times), 2) if times else None},
        ),
    }


def review_metrics(store: Store = STORE, include_demo: bool = False) -> Dict[str, Any]:
    sessions = store.query("SELECT * FROM guided_review_session")
    if not include_demo:
        decisions = {d["id"]: d for d in store.query("SELECT id, demo, environment FROM decision")}
        kept, excluded_n = [], 0
        for s in sessions:
            d = decisions.get(s.get("decision_id") or "")
            if d and _is_excluded_row(d):
                excluded_n += 1
                continue
            kept.append(s)
        sessions = kept
    else:
        excluded_n = 0
    started = sessions
    completed = [s for s in sessions if s.get("status") == "CONFIRMED"]
    abandoned = [s for s in sessions if s.get("status") in ("REJECTED",)]
    pending = store.query("SELECT id FROM decision WHERE status = 'REVIEW_PENDING'")
    if not include_demo:
        pending = [r for r in _prod_decisions(store, False) if r.get("status") == "REVIEW_PENDING"]
    times = []
    for s in completed:
        a = _parse_stamp(s.get("created_at") or "")
        b = _parse_stamp(s.get("confirmed_at") or "")
        if a and b:
            times.append((b - a).total_seconds())
    exclude = ["demo", "test", "eval", "system-generated demo"]
    return {
        "review_completion_rate": _metric(
            "review_completion_rate", _rate(len(completed), len(started)),
            len(completed), "completed guided reviews (session CONFIRMED)",
            len(started), "review sessions started",
            exclude, excluded_n,
        ),
        "median_time_to_complete_seconds": _metric(
            "median_time_to_complete",
            round(median(times), 2) if times else None,
            len(times), "completed sessions with timestamps",
            len(completed), "completed guided reviews",
            exclude, excluded_n,
        ),
        "review_pending_backlog": _metric(
            "review_pending_backlog", len(pending),
            len(pending), "decisions currently REVIEW_PENDING",
            1, "point-in-time count (not a rate)",
            exclude, 0,
        ),
        "review_abandon_rate": _metric(
            "review_abandon_rate", _rate(len(abandoned), len(started)),
            len(abandoned), "guided sessions REJECTED / abandoned",
            len(started), "review sessions started",
            exclude, excluded_n,
        ),
    }


def memory_product_metrics(store: Store = STORE, include_demo: bool = False) -> Dict[str, Any]:
    base = mem_metrics.product_metrics(store)
    reminders = mstore.list_reminders(store)
    decisions = _prod_decisions(store, include_demo)
    decision_ids = {d["id"] for d in decisions}
    if not include_demo:
        reminders = [r for r in reminders if r.get("decision_id") in decision_ids or r.get("decision_id") == ""]
    with_fb = [r for r in reminders if r.get("feedback") in ("RELEVANT", "NOT_RELEVANT")]
    dismissed = [r for r in with_fb if r.get("feedback") == "NOT_RELEVANT"]
    per = {}
    for r in reminders:
        per[r["decision_id"]] = per.get(r["decision_id"], 0) + 1
    n_with = len(per)
    exclude = ["demo", "test", "eval"]
    try:
        applicable = store.query(
            "SELECT * FROM rule_applicability WHERE applicability = 'APPLICABLE'"
        )
    except Exception:  # noqa: BLE001
        applicable = []
    confirmed_vios = int(base.get("rule_violations_confirmed") or 0)
    applicable_n = len(applicable)
    return {
        "memory_precision": _metric(
            "memory_precision", base.get("memory_precision"),
            len([r for r in with_fb if r.get("feedback") == "RELEVANT"]),
            "reminders marked RELEVANT",
            len(with_fb), "reminders with RELEVANT or NOT_RELEVANT feedback",
            exclude, 0,
        ),
        "rule_acceptance_rate": _metric(
            "rule_acceptance_rate", base.get("rule_acceptance_rate"),
            int(base.get("active_rule_n") or 0),
            "rules currently ACTIVE",
            int(base.get("rule_candidates_shown") or 0),
            "rules shown as PROPOSED/ACTIVE/REJECTED",
            exclude, 0,
        ),
        "repeated_confirmed_mistake_rate": _metric(
            "repeated_confirmed_mistake_rate", base.get("repeated_confirmed_mistake_rate"),
            int(base.get("repeated_confirmed_mistake_count") or 0),
            "mistakes created after the pattern was CONFIRMED",
            int(base.get("related_reviewed_n") or 0),
            "REVIEWED decisions whose confirmed primary_error matches a CONFIRMED pattern",
            exclude, 0,
        ),
        "rule_violation_recurrence": _metric(
            "rule_violation_recurrence",
            _rate(confirmed_vios, applicable_n) if applicable_n else base.get("rule_violation_recurrence"),
            confirmed_vios,
            "user-confirmed rule_violation rows",
            applicable_n or int(base.get("rule_relevant_decisions") or 0),
            "Active Rule × Decision pairs with applicability=APPLICABLE (not all decisions)",
            exclude + ["NOT_APPLICABLE", "UNKNOWN", "RETIRED rules"],
            0,
        ),
        "reminder_dismiss_rate": _metric(
            "reminder_dismiss_rate", _rate(len(dismissed), len(with_fb)),
            len(dismissed), "reminders marked NOT_RELEVANT",
            len(with_fb), "reminders with explicit feedback",
            exclude, 0,
        ),
        "reminders_per_decision": _metric(
            "reminders_per_decision",
            round(sum(per.values()) / n_with, 4) if n_with else None,
            sum(per.values()), "reminders shown",
            n_with, "decisions that received at least one reminder",
            exclude, 0,
            extra={"cap": 3},
        ),
        "active_rule_n": int(base.get("active_rule_n") or 0),
        "raw": base,
    }


def context_metrics(store: Store = STORE, include_demo: bool = False) -> Dict[str, Any]:
    try:
        rows = store.query("SELECT * FROM decision_context_snapshot WHERE snapshot_type = 'ENTRY_CONTEXT'")
    except Exception:  # noqa: BLE001
        rows = []
    kept, excluded_n = [], 0
    for r in rows:
        if (not include_demo) and _is_excluded_row(r):
            excluded_n += 1
            continue
        kept.append(r)
    full = 0
    fresh = 0
    for r in kept:
        coverage = json.loads(r.get("data_coverage_json") or "{}")
        freshness = json.loads(r.get("data_freshness_json") or "{}")
        keys = ("market", "sentiment", "overseas")
        if all((coverage.get(k) or "") == "full" for k in keys):
            full += 1
        if all((freshness.get(k) or "") == "fresh" for k in keys):
            fresh += 1
    exclude = ["demo", "test", "eval"]
    return {
        "context_coverage_rate": _metric(
            "context_coverage_rate", _rate(full, len(kept)),
            full, "ENTRY_CONTEXT snapshots whose key providers are coverage=full",
            len(kept), "ENTRY_CONTEXT snapshots after excluding demo/test",
            exclude, excluded_n,
        ),
        "fresh_context_rate": _metric(
            "fresh_context_rate", _rate(fresh, len(kept)),
            fresh, "ENTRY_CONTEXT snapshots whose key providers are freshness=fresh",
            len(kept), "ENTRY_CONTEXT snapshots after excluding demo/test",
            exclude, excluded_n,
        ),
    }


def collect(store: Store = STORE, include_demo: bool = False) -> Dict[str, Any]:
    return {
        "include_demo": include_demo,
        "environment": flags.current_environment(),
        "flags": flags.snapshot(),
        "recorder": recorder_metrics(store, include_demo),
        "review": review_metrics(store, include_demo),
        "memory": memory_product_metrics(store, include_demo),
        "context": context_metrics(store, include_demo),
        "data_quality": data_quality_metrics(store, include_demo),
        "research": _research_metrics(store),
        "events_n": len(list_events(include_demo=include_demo, store=store)),
    }


def _research_metrics(store: Store) -> Dict[str, Any]:
    try:
        from core.research.metrics import product_metrics as research_metrics
        return research_metrics(store)
    except Exception:  # noqa: BLE001
        return {}


def data_quality_metrics(store: Store = STORE, include_demo: bool = False) -> Dict[str, Any]:
    from core.context.temporal import parse_dt
    now = parse_dt(datetime.now().isoformat(timespec="seconds"))

    def within_24h(raw: str) -> bool:
        dt = parse_dt(raw or "")
        if not now or not dt:
            return False
        return (now - dt).total_seconds() <= 86400

    try:
        events = store.query("SELECT id, occurred_at, demo, environment FROM product_event")
    except Exception:  # noqa: BLE001
        events = []
    try:
        errors = store.query("SELECT * FROM operational_error WHERE component = 'product_event'")
    except Exception:  # noqa: BLE001
        errors = []
    try:
        pipes = store.query("SELECT * FROM pipeline_run")
    except Exception:  # noqa: BLE001
        pipes = []
    ev_24 = [r for r in events if within_24h(r.get("occurred_at") or "")]
    if not include_demo:
        ev_24 = [r for r in ev_24 if not _is_excluded_row(r)]
    fail_24 = [r for r in errors if within_24h(r.get("occurred_at") or "")]
    pipe_fail = [
        r for r in pipes
        if (r.get("status") or "") == "failed" and within_24h(r.get("started_at") or r.get("finished_at") or "")
    ]
    successes = len(ev_24)
    failures = len(fail_24)
    rate = _rate(successes, successes + failures) if (successes + failures) else None
    exclude = ["demo", "test", "eval"]
    return {
        "event_failures_24h": _metric(
            "event_failures_24h", failures,
            failures, "operational_error product_event insert failures in 24h",
            1, "point-in-time count (not a rate)",
            exclude, 0,
        ),
        "event_write_success_rate": _metric(
            "event_write_success_rate", rate,
            successes, "product_event rows written in 24h",
            successes + failures, "writes attempted (success + operational_error) in 24h",
            exclude, 0,
        ),
        "pipeline_failures_24h": _metric(
            "pipeline_failures_24h", len(pipe_fail),
            len(pipe_fail), "pipeline_run status=failed in 24h",
            1, "point-in-time count (not a rate)",
            exclude, 0,
        ),
        "trusted": failures == 0,
    }
