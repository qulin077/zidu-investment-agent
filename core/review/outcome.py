"""确定性 Outcome。

全部由 execution + quote_daily 算出，不接受手填、不调模型。
行情缺口如实记在 quote_coverage 里：算不出 MFE/MAE 就留空，不猜。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from core.review import repo
from core.review.defs import threshold
from core.store import STORE, Store


def _quotes(code: str, start: str, end: str, store: Store) -> List[Dict[str, Any]]:
    if not start or not end or end < start:
        return []
    return store.query(
        "SELECT date, high, low, close FROM quote_daily"
        " WHERE code = ? AND date BETWEEN ? AND ? ORDER BY date",
        (code, start, end),
    )


def _coverage(rows: List[Dict[str, Any]], start: str, end: str) -> str:
    if not rows:
        return "none"
    if rows[0]["date"] <= start and rows[-1]["date"] >= end:
        return "full"
    return "partial"


def compute(decision_id: str, store: Store = STORE) -> Dict[str, Any]:
    """算一次 outcome，不写库。"""
    decision = repo.require_decision(decision_id, store)
    rows = repo.executions(decision_id, store)
    if not rows:
        raise repo.ReviewError("{0} 没有 execution，无法计算 outcome".format(decision_id))

    buys = [r for r in rows if r["side"] == "BUY"]
    sells = [r for r in rows if r["side"] == "SELL"]
    qty_bought = sum(float(r["qty"]) for r in buys)
    qty_sold = sum(float(r["qty"]) for r in sells)
    amt_bought = sum(float(r["amount"] or 0) for r in buys)
    amt_sold = sum(float(r["amount"] or 0) for r in sells)

    avg_entry = amt_bought / qty_bought if qty_bought else None
    avg_exit = amt_sold / qty_sold if qty_sold else None

    # 只对已卖出的部分算已实现盈亏；未平仓部分不计入，避免用现价充当成交价。
    gross_pnl = None
    realized_pct = None
    if avg_entry and avg_exit and qty_sold:
        gross_pnl = (avg_exit - avg_entry) * qty_sold
        realized_pct = (avg_exit / avg_entry - 1) * 100

    first_entry_on = rows[0]["executed_on"]
    closed_on = decision.get("closed_on") or rows[-1]["executed_on"]

    quotes = _quotes(decision["code"], first_entry_on, closed_on, store)
    coverage = _coverage(quotes, first_entry_on, closed_on)
    mfe_pct = mae_pct = None
    peak_on = trough_on = ""
    if quotes and avg_entry:
        highs = [(float(q["high"]), q["date"]) for q in quotes if q["high"] is not None]
        lows = [(float(q["low"]), q["date"]) for q in quotes if q["low"] is not None]
        if highs:
            top, peak_on = max(highs)
            mfe_pct = (top / avg_entry - 1) * 100
        if lows:
            bottom, trough_on = min(lows)
            mae_pct = (bottom / avg_entry - 1) * 100

    holding_days = len(quotes) if quotes else None

    return {
        "decision_id": decision_id,
        "first_entry_on": first_entry_on,
        "closed_on": closed_on,
        "holding_days": holding_days,
        "qty_bought": qty_bought,
        "qty_sold": qty_sold,
        "avg_entry": avg_entry,
        "avg_exit": avg_exit,
        "gross_pnl": gross_pnl,
        "realized_pct": realized_pct,
        "mfe_pct": mfe_pct,
        "mae_pct": mae_pct,
        "peak_on": peak_on,
        "trough_on": trough_on,
        "quote_coverage": coverage,
        "computed_at": repo.now(),
        "computed_from": "execution+quote_daily",
        "source": "system",
    }


def persist(decision_id: str, store: Store = STORE) -> Dict[str, Any]:
    """算完写库。outcome 整行可重算覆盖 —— 它没有用户输入，不需要 revision。"""
    row = compute(decision_id, store)
    cols = list(row.keys())
    with store.connect() as conn:
        conn.execute("DELETE FROM outcome WHERE decision_id = ?", (decision_id,))
        conn.execute(
            "INSERT INTO outcome ({0}) VALUES ({1})".format(
                ", ".join(cols), ", ".join("?" for _ in cols)
            ),
            tuple(row[c] for c in cols),
        )
    return row


def is_flat(decision_id: str, store: Store = STORE) -> bool:
    return abs(repo.net_qty(decision_id, store)) <= threshold("flat_qty_epsilon", 1e-6)


def close_and_compute(
    decision_id: str, changed_by: str = "user", store: Store = STORE
) -> Dict[str, Any]:
    """ACTIVE → CLOSED → 算 outcome → REVIEW_PENDING。

    净持仓不为零时拒绝，避免出现「还拿着却已复盘」的记录。
    """
    from core.review import lifecycle

    decision = repo.require_decision(decision_id, store)
    if decision["status"] == lifecycle.ACTIVE:
        if not is_flat(decision_id, store):
            raise repo.ReviewError(
                "{0} 还有净持仓 {1}，先补卖出 execution 再 close".format(
                    decision_id, repo.net_qty(decision_id, store)
                )
            )
        repo.transition(decision_id, lifecycle.CLOSED, "净持仓归零", changed_by, "user", store)

    decision = repo.require_decision(decision_id, store)
    if decision["status"] != lifecycle.CLOSED:
        raise repo.ReviewError(
            "{0} 当前是 {1}，只有 ACTIVE / CLOSED 能进入 outcome 计算".format(
                decision_id, decision["status"]
            )
        )
    result = persist(decision_id, store)
    repo.transition(
        decision_id, lifecycle.REVIEW_PENDING, "outcome 已算出", "system", "system", store
    )
    return result
