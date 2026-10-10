"""Review Today 读模型。

Web / API / CLI 共用这一份投影。这里不写库、不发明匹配规则。
"""
from __future__ import annotations

from typing import Any, Dict, List

from core.review import matching, queue, repo
from core.store import STORE, Store


def _open_decisions(code: str, account: str, store: Store) -> List[Dict[str, Any]]:
    rows = store.query(
        "SELECT id, opened_on, code, name, status, origin, thesis, account"
        " FROM decision WHERE code = ? AND status IN ({0})"
        " ORDER BY opened_on DESC, id DESC".format(
            ",".join("?" for _ in matching.OPEN_STATUSES)
        ),
        [code, *matching.OPEN_STATUSES],
    )
    want = account or ""
    return [r for r in rows if (r.get("account") or "") == want]


def _execution_view(row: Dict[str, Any], store: Store) -> Dict[str, Any]:
    claimable = (row.get("match_status") or "") in matching.CLAIMABLE
    payload: Dict[str, Any] = {
        "id": row["id"],
        "symbol": row["code"],
        "name": row.get("name") or "",
        "side": row["side"],
        "price": row["price"],
        "qty": row["qty"],
        "time": row.get("executed_at") or "",
        "executed_on": row["executed_on"],
        "account": row.get("account") or "",
        "match_status": row.get("match_status") or "",
        "match_reason": row.get("match_reason") or "",
        "decision_id": row.get("decision_id"),
        "fingerprint": row.get("fingerprint") or "",
        "subjective_context": row.get("subjective_context") or "",
        "broker_order_id": row.get("broker_order_id") or "",
        "claimable": claimable,
        "candidates": [],
        "open_decisions": [],
    }
    if claimable:
        payload["candidates"] = [
            {
                "decision_id": c["decision_id"],
                "rank": c.get("rank"),
                "score": c.get("score"),
                "reason": c.get("reason") or "",
            }
            for c in repo.candidates_of(row["id"], store)
        ]
        payload["open_decisions"] = _open_decisions(row["code"], row.get("account") or "", store)
    return payload


def snapshot(day: str, store: Store = STORE) -> Dict[str, Any]:
    """今日成交 + 待认领 + 待复盘队列。"""
    executions = [_execution_view(row, store) for row in repo.executions_on(day, store)]
    return {
        "date": day,
        "executions": executions,
        "claimable": [row for row in executions if row["claimable"]],
        "queue": queue.as_dicts(day, store),
    }


def workbench(day: str, store: Store = STORE) -> Dict[str, Any]:
    """/today 盘前入口：健康、未完成、Recorder、提醒、复盘积压、极简 Context。"""
    from core.health.system import collect as health_collect
    from core.context.providers import market, sentiment
    from core.review import flags as _flags
    from core.product import metrics as product_metrics

    base = snapshot(day, store)
    open_rows = store.query(
        "SELECT id, opened_on, code, name, status, origin, thesis FROM decision"
        " WHERE status IN ('DRAFT','PLANNED','ACTIVE') ORDER BY opened_on DESC, id DESC LIMIT 20"
    )
    try:
        reminders = store.query(
            "SELECT r.*, d.code FROM memory_reminder r"
            " LEFT JOIN decision d ON d.id = r.decision_id"
            " ORDER BY r.created_at DESC LIMIT 20"
        )
    except Exception:  # noqa: BLE001
        reminders = []
    mini = {}
    try:
        sent = sentiment.collect(repo.now(), store, None)
        mkt = market.collect(repo.now(), store, None)
        mini = {
            "market_stage": ((sent.get("payload") or {}).get("mkt_stage") or {}).get("value"),
            "indices": (mkt.get("payload") or {}).get("indices") or {},
        }
    except Exception:  # noqa: BLE001
        mini = {}
    return {
        **base,
        "health": health_collect(store, today=day),
        "open_decisions": open_rows,
        "reminders": reminders,
        "metrics": product_metrics.collect(store, include_demo=False),
        "context_now": mini,
        "flags": _flags.snapshot(),
        "note": "Today 不是行情终端。Context 是事实，不是建议。",
    }
