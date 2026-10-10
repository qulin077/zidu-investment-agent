"""Market-data preflight and refresh tools used by the outer Agent runtime."""
from __future__ import annotations

from datetime import date, datetime, time
from typing import Any

from core.calendar import is_trading_day, parse_date, previous_trading_day, refresh_trading_calendar
from core.store import Store
from core.symbols import universe_codes


def expected_market_day(ref: Any = None) -> str:
    """Latest session a request for "today's market" is allowed to use.

    Before the A-share open we expect the previous session.  Once continuous
    trading starts, today's partial daily bar is preferable to an old close.
    """
    if isinstance(ref, datetime):
        now = ref
    elif isinstance(ref, date):
        now = datetime.combine(ref, time(16, 0))
    else:
        now = datetime.now().astimezone()
    day = now.date()
    if is_trading_day(day) and now.time() >= time(9, 30):
        return day.isoformat()
    prior = previous_trading_day(day)
    return prior.isoformat() if prior else day.isoformat()


def market_data_status(store: Store, ref: Any = None) -> dict:
    asof = store.max_date("quote_daily") or ""
    expected = expected_market_day(ref)
    universe = len(universe_codes())
    covered = 0
    if asof:
        covered = int(store.scalar(
            "SELECT COUNT(DISTINCT code) FROM quote_daily WHERE date = ?", (asof,),
        ) or 0)
    coverage = covered / universe if universe else 0.0
    asof_day = parse_date(asof)
    expected_day = parse_date(expected)
    current = bool(asof_day and expected_day and asof_day >= expected_day)
    complete = bool(universe and coverage >= 0.9)
    issues = []
    if not asof:
        issues.append("行情库为空")
    elif not current:
        issues.append("行情截止 {0}，当前至少需要 {1}".format(asof, expected))
    if not complete:
        issues.append("最新交易日覆盖 {0}/{1}（{2:.0%}）".format(covered, universe, coverage))
    return {
        "ok": current and complete,
        "asof": asof,
        "expected_asof": expected,
        "covered": covered,
        "universe": universe,
        "coverage": round(coverage, 4),
        "issues": issues,
    }


def refresh_market_data(store: Store, limit: int = 5) -> dict:
    """Refresh the bounded universe from a batched live snapshot provider."""
    from core.ingest.live import refresh_latest_quotes
    from core.ingest.runner import _now

    calendar_result = refresh_trading_calendar()
    expected = expected_market_day()
    result = refresh_latest_quotes(
        universe_codes(), store=store, minimum_date=expected,
    )
    store.record_run(
        dataset=result.dataset,
        ran_at=_now(),
        asof=result.asof,
        rows=result.rows,
        ok=result.ok,
        message=result.message,
    )
    status = market_data_status(store)
    return {
        "ok": bool(result.ok and status["ok"]),
        "ingest": result.as_dict(),
        "status": status,
        "calendar": calendar_result,
    }
