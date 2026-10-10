"""ExecutionImporter：归一后的成交 → execution 表。

只负责去重与落库。不匹配 Decision，不推进状态 —— 那是 matching / pipeline 的事。

去重分两层，不要混成一把「全局自然键」：

  1. fingerprint（主路径）
     同一文件再导一次，fingerprint 撞唯一索引 → duplicate。
     identical twins 在 assign_fingerprints() 里用 occurrence 区分，所以
     同秒同价同量的两笔真实成交会得到两个 fingerprint，都会入库。

  2. legacy 兼容（只对已有 legacy 行计数）
     历史流水以 LT- id 入库后，同一笔又被新 importer 打成 fp: 哈希。
     这时 fingerprint 对不上，要用自然键把「还没被认领的 legacy 名额」消耗掉。
     同一次新 import batch 内的 twins **不会**互相写入这个计数器。

有 broker_order_id 时完全走 fingerprint，不再看自然键。
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple

from core.review import repo
from core.review.intake.normalized import (
    NonTradeRow,
    NormalizedExecution,
    ParseResult,
    assign_fingerprints,
)
from core.store import STORE, Store


@dataclass
class ImportResult:
    inserted: List[str] = field(default_factory=list)
    duplicate: List[str] = field(default_factory=list)
    non_trade: List[NonTradeRow] = field(default_factory=list)
    unparseable: List[NonTradeRow] = field(default_factory=list)
    adapter: str = ""
    source_ref: str = ""
    rows_in: int = 0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "rows_in": self.rows_in,
            "inserted": len(self.inserted),
            "duplicate": len(self.duplicate),
            "non_trade": len(self.non_trade),
            "unparseable": len(self.unparseable),
            "execution_ids": self.inserted,
            "non_trade_detail": [
                {"reason": r.reason, "detail": r.detail} for r in self.non_trade
            ],
            "unparseable_detail": [
                {"reason": r.reason, "detail": r.detail} for r in self.unparseable
            ],
            "adapter": self.adapter,
            "source_ref": self.source_ref,
        }


def _existing_fingerprints(fps: List[str], store: Store) -> set:
    if not fps:
        return set()
    found = set()
    for i in range(0, len(fps), 400):  # SQLite 变量上限
        chunk = fps[i:i + 400]
        rows = store.query(
            "SELECT fingerprint FROM execution WHERE fingerprint IN ({0})".format(
                ",".join("?" for _ in chunk)
            ),
            chunk,
        )
        found.update(r["fingerprint"] for r in rows)
    return found


def _natural_key(item: NormalizedExecution) -> Tuple:
    return (
        item.account or "",
        item.code,
        item.executed_on,
        item.executed_at or "",
        item.side,
        round(float(item.price), 4),
        round(float(item.qty), 4),
    )


def _is_legacy_row(row: Dict[str, Any]) -> bool:
    source = row.get("source") or ""
    fingerprint = str(row.get("fingerprint") or "")
    trade_id = str(row.get("trade_id") or "")
    return (
        source == "legacy_import"
        or fingerprint.startswith("LT-")
        or trade_id.startswith("LT-")
    )


def _legacy_natural_key_slots(items: List[NormalizedExecution], store: Store) -> Counter:
    """已有 legacy 行按自然键计数。新 importer 行不进入这个袋子。"""
    days = sorted({i.executed_on for i in items})
    found: Counter = Counter()
    if not days:
        return found
    for i in range(0, len(days), 200):
        chunk = days[i:i + 200]
        rows = store.query(
            "SELECT account, code, executed_on, executed_at, side, price, qty,"
            " source, fingerprint, trade_id"
            " FROM execution WHERE executed_on IN ({0})".format(
                ",".join("?" for _ in chunk)
            ),
            chunk,
        )
        for row in rows:
            if not _is_legacy_row(row):
                continue
            found[(
                row.get("account") or "",
                row["code"],
                row["executed_on"],
                row.get("executed_at") or "",
                row["side"],
                round(float(row["price"] or 0), 4),
                round(float(row["qty"] or 0), 4),
            )] += 1
    return found


def import_executions(
    parsed: ParseResult,
    trade_date: str = "",
    store: Store = STORE,
) -> ImportResult:
    """落库。decision_id 一律留空，匹配在下一步单独做。"""
    items = assign_fingerprints(list(parsed.executions))
    if trade_date:
        items = [i for i in items if i.executed_on == trade_date]

    result = ImportResult(
        non_trade=list(parsed.non_trade),
        unparseable=list(parsed.unparseable),
        adapter=parsed.adapter,
        source_ref=parsed.source_ref,
        rows_in=parsed.rows_in,
    )

    known = _existing_fingerprints([i.fingerprint for i in items], store)
    legacy_slots = _legacy_natural_key_slots(items, store)
    for item in items:
        if item.fingerprint in known:
            result.duplicate.append(item.fingerprint)
            continue
        # 有券商订单号就只信 fingerprint；自然键只用于无 oid 的 legacy 兼容。
        if not item.broker_order_id:
            key = _natural_key(item)
            if legacy_slots[key] > 0:
                legacy_slots[key] -= 1
                result.duplicate.append(item.fingerprint)
                continue
        known.add(item.fingerprint)
        xid = repo.add_execution(
            code=item.code,
            executed_on=item.executed_on,
            side=item.side,
            price=item.price,
            qty=item.qty,
            decision_id=None,
            name=item.name,
            executed_at=item.executed_at,
            amount=item.amount,
            size_pct=item.size_pct,
            planned=item.planned,
            note=item.note,
            source=item.source,
            created_by="system",
            subjective_context="not_recorded",
            account=item.account,
            broker_order_id=item.broker_order_id,
            fingerprint=item.fingerprint,
            store=store,
        )
        result.inserted.append(xid)
    return result
