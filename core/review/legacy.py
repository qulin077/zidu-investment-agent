"""P0.8：历史交易流水 → execution。

530 笔流水是导入的，不是记录的：价格数量时间是真的，「为什么买、是不是
计划内、当时什么情绪」基本是空的。所以这里只做一件事——把成交事实落进
execution 表，decision_id 留 NULL。

严禁在这里生成 Decision，也严禁填 thesis / expectation / plan / emotion /
invalidation。主观字段一律 subjective_context='unavailable'，它的含义是
「当时就没记」，不是「待补」，任何人和模型都不应该去补。
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.config import TRADES_CSV
from core.review import repo
from core.store import STORE, Store
from core.symbols import normalize_code


def _rows(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [{k: (v or "").strip() for k, v in row.items()} for row in csv.DictReader(handle)]


def _side(raw: str) -> Optional[str]:
    text = raw or ""
    if "买" in text:
        return "BUY"
    if "卖" in text:
        return "SELL"
    return None


def _num(raw: str) -> Optional[float]:
    try:
        return float(str(raw).replace(",", ""))
    except (TypeError, ValueError):
        return None


def legacy_trade_id(row: Dict[str, str], index: int) -> str:
    """稳定 id：同一行重复导入不会产生第二条 execution。"""
    return "LT-{0}-{1}-{2}-{3:04d}".format(
        (row.get("日期") or "")[:10].replace("-", ""),
        normalize_code(row.get("代码")) or "000000",
        (row.get("时间") or "").replace(":", "")[:6] or "000000",
        index,
    )


def import_trades(
    path: Path = TRADES_CSV, limit: int = 0, store: Store = STORE
) -> Dict[str, Any]:
    rows = _rows(path)
    existing = {
        r["trade_id"]
        for r in store.query("SELECT trade_id FROM execution WHERE trade_id != ''")
    }

    imported = 0
    skipped_existing = 0
    skipped_non_trade: List[Dict[str, str]] = []
    skipped_bad: List[str] = []

    for index, row in enumerate(rows, start=1):
        if limit and imported >= limit:
            break
        tid = legacy_trade_id(row, index)
        if tid in existing:
            skipped_existing += 1
            continue
        side = _side(row.get("方向") or "")
        if side is None:
            # 红股入账、配股、分红这类公司行为不是成交，不该被猜成买卖。
            skipped_non_trade.append(
                {"trade_id": tid, "方向": row.get("方向") or "", "名称": row.get("名称") or ""}
            )
            continue
        code = normalize_code(row.get("代码"))
        day = (row.get("日期") or "")[:10]
        price = _num(row.get("价格") or "")
        qty = _num(row.get("数量") or "")
        if not (code and day and price and qty):
            skipped_bad.append(tid)
            continue
        repo.add_execution(
            code=code,
            executed_on=day,
            side=side,
            price=price,
            qty=abs(qty),
            decision_id=None,
            name=row.get("名称") or "",
            executed_at=row.get("时间") or "",
            amount=_num(row.get("金额") or "") or price * abs(qty),
            planned="unknown",          # 历史没有可信的计划内标记
            trade_id=tid,
            fingerprint=tid,            # 与 0002 回填口径一致，走新 importer 也不会再插一条
            note="",                    # 决策理由多为「截图导入」占位，不搬进来
            source="legacy_import",
            created_by="system",
            subjective_context="unavailable",
            store=store,
        )
        imported += 1

    return {
        "ok": True,
        "source": str(path),
        "rows_in_csv": len(rows),
        "imported": imported,
        "skipped_existing": skipped_existing,
        "skipped_non_trade": skipped_non_trade,
        "skipped_unparseable": len(skipped_bad),
        "decision_id": None,
        "subjective_context": "unavailable",
        "note": "只落 execution。不生成 Decision，不推断 thesis / plan / emotion。",
    }


def stats(store: Store = STORE) -> Dict[str, Any]:
    total = store.scalar("SELECT COUNT(*) FROM execution") or 0
    orphan = store.scalar("SELECT COUNT(*) FROM execution WHERE decision_id IS NULL") or 0
    legacy = (
        store.scalar("SELECT COUNT(*) FROM execution WHERE source = 'legacy_import'") or 0
    )
    return {
        "executions": int(total),
        "orphan": int(orphan),
        "legacy_import": int(legacy),
        "attached": int(total) - int(orphan),
    }
