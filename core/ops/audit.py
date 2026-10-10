"""Audit consistency checker。只报告，不自动修。"""
from __future__ import annotations

from typing import Any, Dict, List

from core.review import lifecycle, repo
from core.review.memory import store as mstore
from core.store import STORE, Store

SEVERITY = ("PASS", "WARN", "FAIL")


def _issue(level: str, code: str, detail: str, entity: str = "") -> Dict[str, str]:
    return {"level": level, "code": code, "detail": detail, "entity": entity}


def check(store: Store = STORE) -> Dict[str, Any]:
    issues: List[Dict[str, str]] = []
    try:
        decisions = store.query("SELECT * FROM decision")
    except Exception as exc:  # noqa: BLE001
        return {"status": "FAIL", "issues": [_issue("FAIL", "AUDIT_INCONSISTENCY", str(exc))], "counts": {}}

    for d in decisions:
        did = d["id"]
        trans = repo.transitions_of(did, store)
        if trans:
            last = trans[-1]["to_status"]
            if last != d["status"]:
                issues.append(_issue(
                    "FAIL", "AUDIT_INCONSISTENCY",
                    "status={0} last_transition={1}".format(d["status"], last), did,
                ))
        if d["status"] == lifecycle.REVIEWED:
            reviews = repo.reviews(did, store)
            latest = reviews[-1] if reviews else {}
            if not int(latest.get("outcome_confirmed") or 0):
                issues.append(_issue("FAIL", "AUDIT_INCONSISTENCY", "REVIEWED 但 outcome 未确认", did))
            if not int(latest.get("violations_confirmed") or 0):
                issues.append(_issue("FAIL", "AUDIT_INCONSISTENCY", "REVIEWED 但 violations 未确认", did))
            confirmed = [a for a in repo.attributions(did, store) if int(a.get("user_confirmed") or 0)]
            if not confirmed:
                issues.append(_issue("FAIL", "AUDIT_INCONSISTENCY", "REVIEWED 但 attribution 未确认", did))

    try:
        executions = store.query("SELECT id, decision_id, match_status FROM execution")
    except Exception:  # noqa: BLE001
        executions = []
    for ex in executions:
        if ex.get("decision_id") and (ex.get("match_status") or "") == "":
            issues.append(_issue(
                "WARN", "AUDIT_INCONSISTENCY",
                "execution 已挂 Decision 但没有 match_status", ex["id"],
            ))

    try:
        rules = mstore.list_rules(store=store)
    except Exception:  # noqa: BLE001
        rules = []
    for rule in rules:
        if rule.get("status") != "ACTIVE":
            continue
        pat = mstore.get_pattern(rule.get("pattern_id") or "", store)
        if not pat or pat.get("status") != "CONFIRMED":
            issues.append(_issue(
                "FAIL", "AUDIT_INCONSISTENCY",
                "ACTIVE rule 不是来自 CONFIRMED pattern", rule["id"],
            ))

    try:
        revs = store.query("SELECT * FROM revision")
    except Exception:  # noqa: BLE001
        revs = []
    by_row: Dict[str, List[Dict[str, Any]]] = {}
    for r in revs:
        by_row.setdefault("{0}:{1}:{2}".format(r.get("table_name"), r.get("row_id"), r.get("field")), []).append(r)
    for key, rows in by_row.items():
        rows.sort(key=lambda x: x.get("id") or 0)
        last = rows[-1]
        table, row_id, field = key.split(":", 2)
        try:
            current = store.query("SELECT * FROM {0} WHERE id = ?".format(table), (row_id,))
        except Exception:  # noqa: BLE001
            continue
        if not current:
            continue
        live = current[0].get(field)
        if str(live if live is not None else "") != str(last.get("new_value") if last.get("new_value") is not None else ""):
            issues.append(_issue(
                "WARN", "AUDIT_INCONSISTENCY",
                "revision 投影 {0}.{1} 与历史最后值不一致".format(table, field), row_id,
            ))

    fails = [i for i in issues if i["level"] == "FAIL"]
    warns = [i for i in issues if i["level"] == "WARN"]
    status = "FAIL" if fails else ("WARN" if warns else "PASS")
    return {
        "status": status,
        "issues": issues,
        "counts": {"fail": len(fails), "warn": len(warns), "pass_entities": len(decisions)},
    }
