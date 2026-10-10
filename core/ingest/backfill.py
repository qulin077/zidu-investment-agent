"""把现有的 625 个 csv/json 回灌进 SQLite。

这一步不碰任何既有脚本，只是把它们已经产出的东西读进统一的表。
日更管道照常运行，新工作台读库。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from core import config
from core.calendar import to_iso
from core.ingest.base import IngestResult, as_float, as_text, read_csv, stable_id
from core.store import STORE, Store
from core.symbols import is_valid_code, load_universe, normalize_code


def ingest_instruments(store: Store = STORE) -> IngestResult:
    """股票池主数据。"""
    universe = load_universe()
    rows = [
        {
            "code": inst.code,
            "name": inst.name,
            "sector": inst.sector,
            "role": inst.role,
            "board": inst.board,
            "priority": inst.priority,
        }
        for inst in universe
    ]
    written = store.upsert("instrument", rows)
    return IngestResult(
        dataset="instrument",
        rows=written,
        ok=written > 0,
        message="" if written else "config/universe.yaml 为空或缺失",
    )


def ingest_quotes(store: Store = STORE, quotes_dir: Path = config.QUOTES_DIR) -> IngestResult:
    """回灌 data/raw/quotes/*.csv。"""
    result = IngestResult(dataset="quote_daily")
    if not quotes_dir.exists():
        result.ok = False
        result.message = "目录不存在: {0}".format(quotes_dir)
        return result

    payload: List[Dict[str, Any]] = []
    latest = ""
    for path in sorted(quotes_dir.glob("*.csv")):
        code = normalize_code(path.stem)
        if not is_valid_code(code):
            result.skipped.append(path.name)
            continue
        frame = read_csv(path)
        if frame is None or frame.empty or "日期" not in frame.columns:
            result.skipped.append(path.name)
            continue
        for record in frame.to_dict("records"):
            day = to_iso(record.get("日期"))
            if not day:
                continue
            payload.append(
                {
                    "code": code,
                    "date": day,
                    "open": as_float(record.get("开盘")),
                    "high": as_float(record.get("最高")),
                    "low": as_float(record.get("最低")),
                    "close": as_float(record.get("收盘")),
                    "volume": as_float(record.get("成交量")),
                    "pct_chg": as_float(record.get("涨跌幅")),
                }
            )
            if day > latest:
                latest = day

    result.rows = store.upsert("quote_daily", payload)
    result.asof = latest
    result.ok = result.rows > 0
    if not result.ok:
        result.message = "未读到任何行情记录"
    return result


def _news_rows_from_jin10(directory: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for path in sorted(directory.glob("flash_*.csv")):
        frame = read_csv(path)
        if frame is None or frame.empty:
            continue
        for record in frame.to_dict("records"):
            title = as_text(record.get("title")) or as_text(record.get("content"))
            if not title:
                continue
            published = as_text(record.get("time")) or to_iso(record.get("date"))
            if not published:
                continue
            raw_id = as_text(record.get("id"))
            rows.append(
                {
                    "id": "jin10:{0}".format(raw_id or stable_id(published, title)),
                    "source": "金十快讯",
                    "published_at": published,
                    "title": title,
                    "url": as_text(record.get("source_link")) or as_text(record.get("uri")),
                    "summary": as_text(record.get("content"))[:500],
                    "tags": as_text(record.get("importance")),
                }
            )
    return rows


def _news_rows_from_narrative(directory: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for path in sorted(directory.glob("articles_*.csv")):
        frame = read_csv(path)
        if frame is None or frame.empty:
            continue
        for record in frame.to_dict("records"):
            title = as_text(record.get("title"))
            published = to_iso(record.get("date"))
            if not title or not published:
                continue
            raw_id = as_text(record.get("id"))
            rows.append(
                {
                    "id": "narrative:{0}".format(raw_id or stable_id(published, title)),
                    "source": as_text(record.get("source_name")) or "叙事",
                    "published_at": published,
                    "title": title,
                    "url": as_text(record.get("uri")),
                    "summary": as_text(record.get("summary"))[:500],
                    "tags": " ".join(
                        part
                        for part in [as_text(record.get("label")), as_text(record.get("query"))]
                        if part
                    ),
                }
            )
    return rows


def _news_rows_from_policy(directory: Path) -> List[Dict[str, Any]]:
    frame = read_csv(directory / "policy_news.csv")
    if frame is None or frame.empty:
        return []
    rows: List[Dict[str, Any]] = []
    for record in frame.to_dict("records"):
        title = as_text(record.get("title"))
        published = to_iso(record.get("date"))
        if not title or not published:
            continue
        url = as_text(record.get("uri"))
        rows.append(
            {
                "id": "policy:{0}".format(stable_id(published, title, url)),
                "source": as_text(record.get("source")) or "政策要闻",
                "published_at": published,
                "title": title,
                "url": url,
                "summary": "",
                "tags": as_text(record.get("query")),
            }
        )
    return rows


def ingest_news(store: Store = STORE) -> IngestResult:
    """金十快讯 + 叙事文章 + 政策要闻，统一进 news_item。"""
    rows: List[Dict[str, Any]] = []
    rows.extend(_news_rows_from_jin10(config.JIN10_DIR))
    rows.extend(_news_rows_from_narrative(config.NARRATIVE_DIR))
    rows.extend(_news_rows_from_policy(config.POLICY_DIR))

    # 同一 id 保留最后一条，避免 executemany 在单批次内撞主键
    deduped: Dict[str, Dict[str, Any]] = {row["id"]: row for row in rows}
    payload = list(deduped.values())
    latest = max((row["published_at"][:10] for row in payload), default="")

    written = store.upsert("news_item", payload)
    return IngestResult(
        dataset="news_item",
        rows=written,
        asof=latest,
        ok=written > 0,
        message="" if written else "三个新闻源都没有可用记录",
    )


def ingest_positions(store: Store = STORE) -> IngestResult:
    """持仓快照。以 持仓_快照.csv 为历史真相源。"""
    frame = read_csv(config.HOLDINGS_SNAPSHOT_CSV)
    if frame is None or frame.empty:
        return IngestResult(
            dataset="position_snapshot", ok=False, message="持仓_快照.csv 缺失或为空"
        )
    payload = []
    for record in frame.to_dict("records"):
        day = to_iso(record.get("日期"))
        code = normalize_code(record.get("代码"))
        if not day or not code:
            continue
        payload.append(
            {
                "date": day,
                "code": code,
                "name": as_text(record.get("名称")),
                "qty": as_float(record.get("持仓数量")),
                "cost": as_float(record.get("成本价")),
                "price": as_float(record.get("现价")),
                "mkt_value": as_float(record.get("市值")),
                "pnl_pct": as_float(record.get("浮盈亏%")),
                "sector": as_text(record.get("板块")),
                "weight_pct": as_float(record.get("仓位占比%")),
                "note": as_text(record.get("备注")),
            }
        )
    written = store.upsert("position_snapshot", payload)
    return IngestResult(
        dataset="position_snapshot",
        rows=written,
        asof=max((row["date"] for row in payload), default=""),
        ok=written > 0,
    )


def ingest_account(store: Store = STORE) -> IngestResult:
    frame = read_csv(config.ACCOUNT_SNAPSHOT_CSV)
    if frame is None or frame.empty:
        return IngestResult(
            dataset="account_snapshot", ok=False, message="账户快照.csv 缺失或为空"
        )
    payload = []
    for record in frame.to_dict("records"):
        day = to_iso(record.get("日期"))
        if not day:
            continue
        payload.append(
            {
                "date": day,
                "equity": as_float(record.get("总资产")),
                "mkt_value": as_float(record.get("总市值")),
                "cash": as_float(record.get("可用资金")),
                "pnl_total": as_float(record.get("总盈亏")),
                "pnl_day": as_float(record.get("当日盈亏")),
                "pnl_day_pct": as_float(record.get("当日盈亏%")),
                "position_pct": as_float(record.get("仓位%")),
                "source": as_text(record.get("来源")),
            }
        )
    written = store.upsert("account_snapshot", payload)
    return IngestResult(
        dataset="account_snapshot",
        rows=written,
        asof=max((row["date"] for row in payload), default=""),
        ok=written > 0,
    )


def ingest_trades(store: Store = STORE) -> IngestResult:
    frame = read_csv(config.TRADES_CSV)
    if frame is None or frame.empty:
        return IngestResult(dataset="trade", ok=False, message="交易流水.csv 缺失或为空")
    payload = []
    for record in frame.to_dict("records"):
        day = to_iso(record.get("日期"))
        code = normalize_code(record.get("代码"))
        if not day or not code:
            continue
        time_text = as_text(record.get("时间"))
        side = as_text(record.get("方向"))
        price = as_float(record.get("价格"))
        qty = as_float(record.get("数量"))
        payload.append(
            {
                "id": stable_id(day, time_text, code, side, price, qty),
                "date": day,
                "time": time_text,
                "code": code,
                "name": as_text(record.get("名称")),
                "side": side,
                "price": price,
                "qty": qty,
                "amount": as_float(record.get("金额")),
                "strategy": as_text(record.get("策略标签")),
                "earning_type": as_text(record.get("赚钱类型")),
                "reason": as_text(record.get("决策理由")),
                "emotion": as_text(record.get("情绪分1-5")),
                "planned": as_text(record.get("计划内?")),
            }
        )
    deduped = {row["id"]: row for row in payload}
    written = store.upsert("trade", list(deduped.values()))
    return IngestResult(
        dataset="trade",
        rows=written,
        asof=max((row["date"] for row in payload), default=""),
        ok=written > 0,
        message="" if len(deduped) == len(payload) else "合并了 {0} 条完全重复的成交".format(
            len(payload) - len(deduped)
        ),
    )


BACKFILL_STEPS = (
    ("标的主数据", ingest_instruments),
    ("行情", ingest_quotes),
    ("新闻", ingest_news),
    ("持仓快照", ingest_positions),
    ("账户快照", ingest_account),
    ("成交流水", ingest_trades),
)
