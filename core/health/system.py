"""System Health：每天能不能用，而不是静默坏掉。"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from core.config import ACCOUNT_SNAPSHOT_CSV, HOLDINGS_SNAPSHOT_CSV, QUOTES_DIR
from core.review import flags, repo
from core.store import STORE, Store

STALE_DAYS = 7
EVENT_FAIL_WARN = 1
EVENT_FAIL_FAIL = 4
PIPELINE_STUCK_SECONDS = 1800


def _age_days(as_of: str, today: str) -> Optional[int]:
    if not as_of:
        return None
    try:
        a = datetime.strptime(str(as_of)[:10], "%Y-%m-%d")
        b = datetime.strptime(str(today)[:10], "%Y-%m-%d")
    except ValueError:
        return None
    return (b - a).days


def _file_asof(path: Path) -> str:
    if not path.exists():
        return ""
    try:
        import pandas as pd
        df = pd.read_csv(path, nrows=5)
        for col in ("日期", "date"):
            if col in df.columns:
                full = pd.read_csv(path, usecols=[col])
                return str(full[col].astype(str).max())[:10]
    except Exception:  # noqa: BLE001
        return ""
    return ""


def _status(ok: bool, detail: str, age: Optional[int] = None) -> Dict[str, Any]:
    return {"ok": ok, "status": "PASS" if ok else "FAIL", "detail": detail, "age_days": age}


def _tri(status: str, detail: str) -> Dict[str, Any]:
    return {"ok": status != "FAIL", "status": status, "detail": detail, "age_days": None}


def _parse_stamp(raw: str):
    from core.context.temporal import parse_dt
    return parse_dt(raw or "")


def _event_logging(store: Store, now_raw: str) -> Dict[str, Any]:
    now = _parse_stamp(now_raw)
    try:
        rows = store.query(
            "SELECT * FROM operational_error WHERE component = 'product_event'"
        )
    except Exception:  # noqa: BLE001
        rows = []
    n = 0
    for row in rows:
        dt = _parse_stamp(row.get("occurred_at") or "")
        if now and dt and (now - dt).total_seconds() <= 86400:
            n += 1
        elif now is None:
            n += 1
    if n == 0:
        status = "PASS"
    elif n < EVENT_FAIL_FAIL:
        status = "WARN"
    else:
        status = "FAIL"
    return _tri(status, "event write failures 24h={0}".format(n))


def _pipeline_health(store: Store, now_raw: str) -> Dict[str, Any]:
    now = _parse_stamp(now_raw)
    try:
        rows = store.query("SELECT * FROM pipeline_run")
    except Exception:  # noqa: BLE001
        rows = []
    stuck = []
    failed_24h = 0
    for row in rows:
        status = (row.get("status") or "").lower()
        started = _parse_stamp(row.get("started_at") or "")
        if status == "running" and now and started:
            if (now - started).total_seconds() > PIPELINE_STUCK_SECONDS:
                stuck.append(row.get("id"))
        if status == "failed" and now and started and (now - started).total_seconds() <= 86400:
            failed_24h += 1
    if stuck:
        return _tri("WARN", "stuck pipeline_run={0}".format(",".join(str(x) for x in stuck[:5])))
    if failed_24h:
        return _tri("WARN", "pipeline failures 24h={0}".format(failed_24h))
    return _tri("PASS", "pipelines idle or finished")


def collect(store: Store = STORE, today: str = "", quotes_dir: Optional[Path] = None) -> Dict[str, Any]:
    day = today or repo.today()
    qdir = quotes_dir or QUOTES_DIR
    quote_asof = store.max_date("quote_daily") or ""
    if not quote_asof and qdir.exists():
        dates = []
        for path in list(qdir.glob("*.csv"))[:40]:
            asof = _file_asof(path)
            if asof:
                dates.append(asof)
        quote_asof = max(dates) if dates else ""
    q_age = _age_days(quote_asof, day)
    quotes = _status(q_age is not None and q_age <= STALE_DAYS, quote_asof or "missing", q_age)

    exec_asof = store.max_date("execution", "executed_on") or ""
    e_age = _age_days(exec_asof, day)
    execution = _status(True if not exec_asof else (e_age is not None and e_age <= STALE_DAYS),
                        exec_asof or "none", e_age)

    pos_asof = store.max_date("position_snapshot") or _file_asof(HOLDINGS_SNAPSHOT_CSV)
    p_age = _age_days(pos_asof, day)
    position = _status(p_age is not None and p_age <= STALE_DAYS, pos_asof or "missing", p_age)

    acct_asof = store.max_date("account_snapshot") or _file_asof(ACCOUNT_SNAPSHOT_CSV)
    a_age = _age_days(acct_asof, day)
    account = _status(a_age is not None and a_age <= STALE_DAYS, acct_asof or "missing", a_age)

    orphans = store.query("SELECT id FROM execution WHERE decision_id IS NULL OR decision_id = ''")
    pending = store.query("SELECT id FROM decision WHERE status = 'REVIEW_PENDING'")
    drafts = store.query(
        "SELECT id FROM recorder_draft WHERE status IN ('PARSED','VALIDATED','NEEDS_EDIT')"
    )
    try:
        candidates = store.query("SELECT id FROM pattern WHERE status = 'CANDIDATE'")
    except Exception:  # noqa: BLE001
        candidates = []
    try:
        from core.ops.audit import check as audit_check
        audit = audit_check(store)
        audit_ok = audit.get("status") != "FAIL"
    except Exception as exc:  # noqa: BLE001
        audit = {"status": "WARN", "error": str(exc)}
        audit_ok = True

    items = {
        "quotes": quotes,
        "execution_import": execution,
        "positions": position,
        "account": account,
        "decision_audit": _status(audit_ok, audit.get("status") or "", None),
        "product_events": _event_logging(store, repo.now()),
        "pipelines": _pipeline_health(store, repo.now()),
    }
    core_ok = all(v["ok"] for v in (quotes, position, account)) and audit_ok
    events_ok = items["product_events"]["status"] != "FAIL"
    return {
        "checked_at": repo.now(),
        "as_of": day,
        "ok": core_ok and events_ok,
        "items": items,
        "review_backlog": len(pending),
        "recorder_drafts": len(drafts),
        "memory_candidates": len(candidates),
        "orphan_execution_count": len(orphans),
        "flags": flags.snapshot(),
        "lines": [
            "Quotes             {0}".format(quotes["status"]),
            "Execution import   {0}".format(execution["status"]),
            "Decision audit     {0}".format(audit.get("status") or "PASS"),
            "Product Events     {0}".format(items["product_events"]["status"]),
            "Pipelines          {0}".format(items["pipelines"]["status"]),
            "Review backlog     {0}".format(len(pending)),
            "Recorder drafts    {0}".format(len(drafts)),
            "Memory candidates  {0}".format(len(candidates)),
        ],
    }
