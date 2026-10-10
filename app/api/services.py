"""看板查询层。只读 core.store，不做任何交易判定。"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from core import config
from core.calendar import age_days, to_iso, today
from core.contracts import inspect_all
from core.store import STORE, Store
from core.symbols import normalize_code, universe_codes, universe_index

# 框架文档的检索范围。只暴露研究框架，不含交割单等隐私明细。
FRAMEWORK_DIRS = (
    "08-工具与模板",
    "10-我的交易",
    "11-节奏看板",
    "01-宏观基本面",
    "06-行业景气度",
)


def dataset_health(store: Store = STORE) -> Dict[str, Any]:
    statuses = inspect_all(store=store, universe_size=len(universe_codes()))
    return {
        "ok": all(s.ok for s in statuses),
        "checked_at": today().isoformat(),
        "datasets": [s.as_dict() for s in statuses],
    }


def latest_quote_day(store: Store = STORE) -> str:
    return store.max_date("quote_daily") or ""


def instruments(store: Store = STORE) -> List[Dict[str, Any]]:
    day = latest_quote_day(store)
    rows = store.query(
        """
        SELECT i.code, i.name, i.sector, i.role, i.board, i.priority,
               q.close, q.pct_chg, q.date AS quote_date
        FROM instrument i
        LEFT JOIN quote_daily q ON q.code = i.code AND q.date = ?
        ORDER BY i.priority, i.code
        """,
        (day,),
    )
    for row in rows:
        row["stale"] = row.get("quote_date") is None
    return rows


def quote_series(code: str, days: int = 120, store: Store = STORE) -> Dict[str, Any]:
    norm = normalize_code(code)
    rows = store.query(
        """
        SELECT date, open, high, low, close, volume, pct_chg
        FROM quote_daily WHERE code = ?
        ORDER BY date DESC LIMIT ?
        """,
        (norm, max(1, days)),
    )
    rows.reverse()
    inst = universe_index().get(norm)
    from core.market_data.technical import technical_snapshot
    return {
        "code": norm,
        "name": inst.name if inst else "",
        "sector": inst.sector if inst else "",
        "rows": rows,
        "asof": rows[-1]["date"] if rows else "",
        "technical": technical_snapshot(rows),
    }


def movers(limit: int = 10, store: Store = STORE) -> Dict[str, Any]:
    """池内当日涨跌排行。"""
    day = latest_quote_day(store)
    if not day:
        return {"asof": "", "gainers": [], "losers": []}
    rows = store.query(
        """
        SELECT q.code, i.name, i.sector, q.close, q.pct_chg
        FROM quote_daily q JOIN instrument i ON i.code = q.code
        WHERE q.date = ? AND q.pct_chg IS NOT NULL
        ORDER BY q.pct_chg DESC
        """,
        (day,),
    )
    return {
        "asof": day,
        "gainers": rows[: max(1, limit)],
        "losers": list(reversed(rows[-max(1, limit) :])),
    }


def sector_performance(store: Store = STORE) -> Dict[str, Any]:
    """板块波动：按 universe 的 sector 聚合当日平均涨跌幅。"""
    day = latest_quote_day(store)
    if not day:
        return {"asof": "", "sectors": []}
    rows = store.query(
        """
        SELECT i.sector,
               COUNT(*) AS count,
               AVG(q.pct_chg) AS avg_pct,
               MAX(q.pct_chg) AS max_pct,
               MIN(q.pct_chg) AS min_pct
        FROM quote_daily q JOIN instrument i ON i.code = q.code
        WHERE q.date = ? AND q.pct_chg IS NOT NULL AND i.sector <> ''
        GROUP BY i.sector
        ORDER BY avg_pct DESC
        """,
        (day,),
    )
    for row in rows:
        for key in ("avg_pct", "max_pct", "min_pct"):
            if row.get(key) is not None:
                row[key] = round(row[key], 2)
    return {"asof": day, "sectors": rows}


def positions(store: Store = STORE) -> Dict[str, Any]:
    """最新持仓快照，并附上当前行情价与快照过期天数。"""
    snapshot_day = store.max_date("position_snapshot") or ""
    if not snapshot_day:
        return {"asof": "", "stale_days": None, "rows": []}
    quote_day = latest_quote_day(store)
    rows = store.query(
        """
        SELECT p.code, p.name, p.qty, p.cost, p.price AS snapshot_price,
               p.mkt_value, p.pnl_pct, p.sector, p.weight_pct,
               q.close AS current_price, q.date AS quote_date
        FROM position_snapshot p
        LEFT JOIN quote_daily q ON q.code = p.code AND q.date = ?
        WHERE p.date = ? AND p.qty > 0
        ORDER BY p.mkt_value DESC
        """,
        (quote_day, snapshot_day),
    )
    for row in rows:
        price = row.get("current_price")
        cost = row.get("cost")
        row["current_pnl_pct"] = (
            round((price - cost) / cost * 100, 2) if price and cost else None
        )
        row["current_value"] = (
            round(price * row["qty"], 2) if price and row.get("qty") else None
        )
    return {
        "asof": snapshot_day,
        "quote_date": quote_day,
        "stale_days": age_days(snapshot_day),
        "rows": rows,
    }


def account_curve(store: Store = STORE, limit: int = 180) -> Dict[str, Any]:
    rows = store.query(
        "SELECT * FROM account_snapshot ORDER BY date DESC LIMIT ?", (limit,)
    )
    rows.reverse()
    return {"asof": rows[-1]["date"] if rows else "", "rows": rows}


def news(
    source: Optional[str] = None,
    limit: int = 50,
    store: Store = STORE,
) -> Dict[str, Any]:
    sql = "SELECT id, source, published_at, title, url, summary, tags FROM news_item"
    params: List[Any] = []
    if source:
        sql += " WHERE source = ?"
        params.append(source)
    sql += " ORDER BY published_at DESC LIMIT ?"
    params.append(max(1, min(limit, 300)))
    rows = store.query(sql, params)
    sources = store.query(
        "SELECT source, COUNT(*) AS count FROM news_item GROUP BY source ORDER BY count DESC"
    )
    return {
        "asof": to_iso(rows[0]["published_at"]) if rows else "",
        "sources": sources,
        "rows": rows,
    }


def news_board(limit: int = 48, store: Store = STORE) -> Dict[str, Any]:
    """看板新闻：按来源抽样再按时间排，避免整页都是金十快讯。"""
    sources = store.query(
        "SELECT source, COUNT(*) AS count FROM news_item GROUP BY source ORDER BY count DESC"
    )
    seen = set()
    rows: List[Dict[str, Any]] = []
    for src in sources[:10]:
        name = src.get("source") or ""
        quota = 6 if name == "金十快讯" else 10
        chunk = store.query(
            """
            SELECT id, source, published_at, title, url, summary, tags
            FROM news_item WHERE source = ?
            ORDER BY published_at DESC LIMIT ?
            """,
            (name, quota),
        )
        for row in chunk:
            rid = row.get("id")
            if rid in seen:
                continue
            seen.add(rid)
            rows.append(row)
    rows.sort(key=lambda r: r.get("published_at") or "", reverse=True)
    clipped = rows[: max(1, min(limit, 80))]
    return {
        "asof": to_iso(clipped[0]["published_at"]) if clipped else "",
        "sources": sources,
        "rows": clipped,
    }


def trade_summary(store: Store = STORE) -> Dict[str, Any]:
    """成交流水概览与字段填充率。填充率是采集质量的核心指标。"""
    total = store.count("trade")
    if total == 0:
        return {"total": 0, "asof": "", "fill_rates": {}}
    fields = {
        "赚钱类型": "earning_type",
        "策略标签": "strategy",
        "情绪分": "emotion",
        "计划内": "planned",
        "决策理由": "reason",
    }
    rates = {}
    for label, column in fields.items():
        filled = int(
            store.scalar(
                "SELECT COUNT(*) FROM trade WHERE {0} <> '' AND {0} <> '待复盘'".format(column)
            )
            or 0
        )
        rates[label] = round(filled / total * 100, 1)
    return {
        "total": total,
        "asof": store.max_date("trade") or "",
        "fill_rates": rates,
    }


def _doc_title(path: Path) -> str:
    try:
        with path.open("r", encoding="utf-8") as handle:
            for _ in range(10):
                line = handle.readline()
                if not line:
                    break
                if line.startswith("# "):
                    return line[2:].strip()
    except OSError:
        pass
    return path.stem


def frameworks() -> List[Dict[str, Any]]:
    """研究框架文档索引。"""
    out: List[Dict[str, Any]] = []
    for folder in FRAMEWORK_DIRS:
        base = config.ROOT / folder
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.md")):
            if any(part.startswith((".", "_")) for part in path.parts):
                continue
            rel = path.relative_to(config.ROOT)
            try:
                size = path.stat().st_size
            except OSError:
                continue
            out.append(
                {
                    "path": str(rel),
                    "section": folder,
                    "title": _doc_title(path),
                    "size": size,
                }
            )
    return out


def read_framework(rel_path: str) -> Dict[str, Any]:
    """按相对路径读取文档内容。拒绝跳出仓库与访问未授权目录。"""
    target = (config.ROOT / rel_path).resolve()
    if not str(target).startswith(str(config.ROOT.resolve())):
        raise PermissionError("路径越界")
    if target.suffix.lower() != ".md" or not target.is_file():
        raise FileNotFoundError(rel_path)
    rel = target.relative_to(config.ROOT.resolve())
    if rel.parts[0] not in FRAMEWORK_DIRS:
        raise PermissionError("该目录未开放")
    return {
        "path": str(rel),
        "title": _doc_title(target),
        "content": target.read_text(encoding="utf-8"),
    }


def board(store: Store = STORE) -> Dict[str, Any]:
    """看板首屏：环境脉冲 + 异动 + 板块 + 持仓 + 新闻。"""
    from core.market_pulse import pulse

    from core.research.daily_updates import list_candidates, pending_count

    return {
        "health": dataset_health(store),
        "pulse": pulse(store=store),
        "movers": movers(limit=12, store=store),
        "sectors": sector_performance(store),
        "positions": positions(store),
        "account": account_curve(store, limit=30),
        "trades": trade_summary(store),
        "news": news_board(limit=48, store=store),
        "research_updates": {
            "pending_count": pending_count(store),
            "rows": list_candidates(store, status="PENDING", limit=8),
        },
    }


def _prediction_rows() -> List[Dict[str, str]]:
    path = config.TRADING_DIR / "预测台账.csv"
    if not path.exists():
        return []
    import csv

    with path.open("r", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def replay(date: Optional[str] = None, store: Store = STORE) -> Dict[str, Any]:
    """复盘房间：当天交割 + 感知账（预测）+ 执行账（计划内）。"""
    asof = date or store.max_date("trade") or ""
    trades = []
    if asof:
        trades = store.query(
            """
            SELECT id, date, time, code, name, side, price, qty, amount,
                   strategy, earning_type, reason, emotion, planned
            FROM trade WHERE date = ? ORDER BY time, id
            """,
            (asof,),
        )
    dates = [
        row["date"]
        for row in store.query(
            "SELECT DISTINCT date FROM trade ORDER BY date DESC LIMIT 12"
        )
    ]
    preds = _prediction_rows()
    pending = [row for row in preds if (row.get("结果") or "待验") in ("待验", "")]
    scored = [row for row in preds if (row.get("结果") or "") not in ("待验", "")]
    summary = trade_summary(store)
    buys = [t for t in trades if "买" in (t.get("side") or "")]
    missing_e = [
        t
        for t in buys
        if not (t.get("earning_type") or "").strip()
        or t.get("earning_type") == "待复盘"
    ]
    unplanned = [t for t in trades if str(t.get("planned") or "").startswith("否")]
    return {
        "asof": asof,
        "dates": dates,
        "trades": trades,
        "n_trades": len(trades),
        "n_buys": len(buys),
        "missing_earning_type": len(missing_e),
        "unplanned": len(unplanned),
        "predictions": {
            "pending": pending,
            "scored": scored,
            "pending_count": len(pending),
            "scored_count": len(scored),
        },
        "fill_rates": summary.get("fill_rates") or {},
        "trade_total": summary.get("total") or 0,
        "purpose": {
            "perception": "昨日预期 vs 今日事实。检验对市场的感知。",
            "execution": "计划 vs 实操。检验执行。两套账不能用盈亏互相开脱。",
        },
    }


def personas() -> Dict[str, Any]:
    path = config.CONFIG_DIR / "personas.yaml"
    import yaml

    data = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
    return {"modes": data.get("modes") or {}}


def research(query: str, write: bool = True) -> Dict[str, Any]:
    """LEGACY_QUICK_BRIEF。新的研究会话不要走这里。"""
    from core.research.harness import run

    return run(query, write=write)


def dialogue(
    query: str,
    persist: bool = True,
    image_base64: Optional[str] = None,
    mime: Optional[str] = None,
) -> Dict[str, Any]:
    from core.dialogue import turn

    vision = None
    if image_base64:
        from core.vision import extract_trades

        vision = extract_trades(image_base64, mime)
    return turn(query, persist=persist, vision=vision)


def dialogue_session() -> Dict[str, Any]:
    from core.dialogue import load_session

    return load_session()


def dialogue_reset() -> Dict[str, Any]:
    from core.dialogue import reset_session

    return reset_session()


def tools_catalog() -> Dict[str, Any]:
    from core.tools import catalog

    return catalog()


def tools_call(name: str, args: Optional[Dict[str, Any]] = None, compact: bool = True) -> Dict[str, Any]:
    from core.tools import call

    return call(name, args or {}, compact=compact)
