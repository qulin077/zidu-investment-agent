"""Lightweight skills that do not require the Research Workspace."""
from __future__ import annotations

from core.agent.skill_registry import allows
from core.ingest.base import as_float


def run_candidates(message: str, event: str, network: str = "replay", search=None) -> dict:
    theme = event or "当前主题"
    leads = []
    if network == "live" and allows("candidate-discovery", "search"):
        leads = _search_leads("{0} 供应商 客户".format(theme), search, provider="ddgs")
    lines = [
        "Candidate Exposure Matrix",
        "沿用事件：{0}".format(theme),
        "这是暴露发现。没有产品、客户或收入原文的公司，不进入推荐。",
        "Company | Exposure | Stage | Revenue Evidence",
        "待核对 | THEMATIC | UNKNOWN | UNKNOWN",
        "没有足够原文时，不把市场映射写成 DIRECT，也不给排序。",
    ]
    if leads:
        lines.append("检索线索（不是证据）")
        lines.extend("- {0}".format(row) for row in leads[:4])
    return _result("candidate-discovery", "\n".join(lines), [{"mention": theme, "type": "technology_platform"}])


def run_market(store, network: str = "replay") -> dict:
    sectors = []
    movers = []
    indices = []
    breadth = {}
    professional = {}
    provider_gap = ""
    if network == "live":
        try:
            from core.market_data.ifind import IfindDataService
            service = IfindDataService.from_environment()
            if service:
                professional = service.market_scan()
        except Exception as exc:
            provider_gap = type(exc).__name__
    try:
        from app.api.services import movers as mover_fn
        from app.api.services import sector_performance
        from core.market_pulse import breadth as breadth_fn
        from core.market_pulse import live_indices
        sectors = (sector_performance(store).get("sectors") or [])[:5]
        packed = mover_fn(limit=5, store=store)
        movers = (packed.get("gainers") or [])[:3]
        indices = live_indices()
        breadth = breadth_fn(store)
    except Exception:
        sectors = []
    lines = ["Market Regime"]
    if professional:
        lines.append("实时数据层：同花顺 iFinD；本地行情用于研究池和历史技术指标。")
    elif network == "live" and provider_gap:
        lines.append("iFinD 实时盘面暂不可用（{0}），已降级到本地行情。".format(provider_gap))
    if not sectors and not movers:
        lines.append("内部行情还不足以判断风格。板块强弱是 UNKNOWN。")
    else:
        lines.append("强弱只来自已入库的板块和异动，没有先去搜新闻。")
    lines.append("Major Indices")
    if professional.get("indices"):
        for row in professional["indices"]:
            close = as_float(row.get("最新价") or row.get("最新成交价"))
            pct = as_float(row.get("涨跌幅"))
            lines.append("- {0} {1}，{2}%（{3}）".format(
                row.get("证券简称") or row.get("指数简称") or row.get("证券代码") or "指数",
                round(close, 2) if close is not None else "UNKNOWN",
                round(pct, 2) if pct is not None else "UNKNOWN",
                row.get("time") or row.get("时间") or "时间 UNKNOWN",
            ))
    elif indices:
        for row in indices:
            lines.append("- {0} {1}，{2}%".format(
                row.get("name") or row.get("code") or "指数",
                row.get("close"), row.get("pct_chg"),
            ))
    else:
        lines.append("主要指数实时快照 UNKNOWN。")
    if professional.get("indices"):
        # 上证与深证口径覆盖沪深两市；创业板已包含在深市中，不重复相加。
        market_rows = [
            row for row in professional["indices"]
            if (row.get("证券简称") or "") in {"上证指数", "深证成指"}
        ]
        up = sum(int(as_float(row.get("上涨家数")) or 0) for row in market_rows)
        down = sum(int(as_float(row.get("下跌家数")) or 0) for row in market_rows)
        limit_up = sum(int(as_float(row.get("涨停家数")) or 0) for row in market_rows)
        limit_down = sum(int(as_float(row.get("跌停家数")) or 0) for row in market_rows)
        amount = sum(as_float(row.get("成交额")) or 0 for row in market_rows)
        if up or down:
            lines.append("Full-market Breadth")
            lines.append("- 沪深口径：上涨 {0}、下跌 {1}、涨停 {2}、跌停 {3}。".format(
                up, down, limit_up, limit_down,
            ))
            lines.append("- 沪深成交额约 {0:.2f} 万亿元。".format(amount / 1_000_000_000_000))
    lines.append("Watchlist Strength Map")
    if sectors:
        for row in sectors:
            lines.append("- {0} 平均 {1}%".format(row.get("sector") or "未分类", row.get("avg_pct")))
    else:
        lines.append("板块排名 UNKNOWN。")
    if professional.get("sectors"):
        live_sectors = professional["sectors"]
        lines.append("iFinD 申万一级行业横截面")
        lines.append("- 相对较强：{0}".format("；".join(
            "{0} {1}%".format(row["name"], round(row["pct_chg"], 2))
            for row in live_sectors[:5]
        )))
        lines.append("- 相对较弱：{0}".format("；".join(
            "{0} {1}%".format(row["name"], round(row["pct_chg"], 2))
            for row in live_sectors[-5:]
        )))
    lines.append("Strong / Weak Sectors")
    if len(sectors) >= 2:
        lines.append("相对较强：{0}".format(sectors[0].get("sector") or ""))
        lines.append("相对较弱：{0}".format(sectors[-1].get("sector") or ""))
    else:
        lines.append("样本不够，不写强弱。")
    lines.append("Breadth")
    if breadth.get("n"):
        lines.append("自选研究池 {0} 只：上涨 {1}、下跌 {2}、平盘 {3}。这不是全市场涨跌家数。".format(
            breadth.get("n"), breadth.get("up"), breadth.get("down"), breadth.get("flat"),
        ))
    else:
        lines.append("自选研究池涨跌家数 UNKNOWN。")
    if movers:
        lines.append("异动里靠前的标的只说明当天波动，不说明主线持续。")
    lines.append("Rotation")
    lines.append("一天的上涨不等于板块轮动已经切换。")
    lines.append("What Changed")
    lines.append("没有把单日涨幅写成趋势。")
    lines.append("Unknown")
    lines.append("成交是否持续、主线能否跨日，内部数据不足时保持 UNKNOWN。")
    return _result("market-scan", "\n".join(lines), [])


def run_portfolio(store, summary: dict | None = None) -> dict:
    summary = summary or {}
    rows = []
    try:
        from app.api.services import positions
        rows = positions(store).get("rows") or []
    except Exception:
        rows = []
    lines = ["Material Changes"]
    if not rows:
        lines.append("现在没有持仓快照。关注项先空着，不会把新闻整份倒出来。")
    else:
        shown = 0
        for row in rows[:8]:
            name = row.get("name") or row.get("code") or ""
            move = row.get("pct_chg")
            if move in (None, "", 0, 0.0):
                continue
            shown += 1
            lines.append("{0}：价格变动 {1}。新证据还没有对照到 Thesis。风险和未决问题保持原样。".format(name, move))
        if not shown:
            lines.append("持仓价格没有需要单独盯的变动。研究记忆里也没有新的实质性证据。")
    thesis = summary.get("thesis_label") or ""
    if thesis:
        lines.append("研究对照：{0}".format(thesis))
    entity = summary.get("active_entity") or summary.get("entity_name") or ""
    entities = [{"mention": entity, "type": "company"}] if entity else []
    return _result("portfolio-monitor", "\n".join(lines), entities)


def _search_leads(query: str, search, provider: str) -> list:
    try:
        if search is not None:
            result = search(query, max_results=5, region="cn-zh")
        else:
            from core.research.tools import providers
            result = providers.search(query, provider, max_results=5, region="cn-zh")
    except Exception:
        return []
    if not result or not result.get("ok"):
        return []
    titles = []
    for hit in result.get("hits") or []:
        title = hit.get("title") or ""
        if title:
            titles.append(title)
    return titles


def _result(skill: str, answer: str, entities: list) -> dict:
    return {
        "skill": skill,
        "status": "ok",
        "answer": answer,
        "artifact": None,
        "entity_refs": entities,
        "project_refs": [],
        "decision_refs": [],
        "claim_refs": [],
        "source_refs": [],
        "open_questions": [],
        "activity": [skill],
    }
