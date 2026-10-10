"""Stable company dossier assembled from grounded research claims.

The dossier is the long-lived product object.  A chat answer is only a view of
it.  Missing evidence stays explicit instead of being completed from model
memory.
"""
from __future__ import annotations

from datetime import date
import re
from typing import Iterable
from urllib.parse import urlparse


UNKNOWN = "UNKNOWN（尚无已核对证据）"


def build(
    *, name: str, ticker: str, claims: list, sources: list, delta: dict,
    quote: dict | None = None, previous: dict | None = None, source_plan: list | None = None,
    financial_statements: dict | None = None,
) -> dict:
    previous = previous or {}
    financial_statements = financial_statements or previous.get("financial_statements") or {}
    source_order = {row.get("local_id") or "": index for index, row in enumerate(sources, start=1)}
    source_by_id = {row.get("local_id") or "": row for row in sources}

    def pick(
        *tokens: str, limit: int = 4,
        source_skills: tuple[str, ...] = (), claim_types: tuple[str, ...] = (),
    ) -> list:
        rows = []
        for claim in claims:
            value = claim.get("text") or claim.get("evidence_text") or ""
            source = source_by_id.get(claim.get("source_id") or "", {})
            semantic_match = (
                (tokens and any(token in value for token in tokens))
                or (source_skills and source.get("source_skill") in source_skills)
                or (claim_types and (claim.get("claim_type") or "").upper() in claim_types)
            )
            if value and semantic_match:
                rows.append(_item(claim, source_order))
        return _unique(rows)[:limit]

    business = pick("主要业务", "产品", "生产和销售", "客户", "服务")
    segments = pick("分行业", "分产品", "分地区", "板块", "占营业收入", "收入来源")
    financials = pick("营业收入", "净利润", "毛利率", "现金流", "资本开支", "ROE", "ROIC", limit=6)
    growth = pick("增长", "增速", "订单", "产能", "利用率", "销量", "价格", "需求", "客户", limit=5)
    profit = pick("毛利", "成本", "费用", "利润", "价格", "原材料", "汇率", limit=5)
    moat = pick("核心竞争力", "壁垒", "专利", "技术", "研发", "市场份额", "定价", "认证", "规模", limit=5)
    industry = pick("行业", "市场份额", "市占率", "排名", "竞争", "产业链", limit=5)
    customer_supplier = pick("客户", "供应商", "集中度", "直销", "海外", limit=5)
    capital_allocation = pick("资本开支", "扩产", "投资", "收购", "负债", "营运资本", "现金流", limit=5)
    guidance = pick("指引", "经营目标", "公司预计", "管理层预计", "展望", limit=4)
    consensus = pick("一致预期", "市场预期", "机构预期", limit=4)
    sell_side = _sell_side_rows(claims, sources, source_order, limit=12)
    narrative = pick(
        "市场叙事", "主题", "概念", "估值", "景气", "争议", limit=6,
        source_skills=("market-narrative",),
    )
    risks = pick("风险", "下滑", "下降", "承压", "波动", "减值", "依赖", "不利", limit=6)
    catalysts = pick(
        "催化", "投产", "量产", "订单", "认证", "涨价", "发布", "出货", "扩产",
        "交付", "获批", "中标", "业绩预告", limit=8,
    )

    new_claim_ids = {row.get("id") for row in delta.get("added_claims") or []}
    new_facts = [
        _item(row, source_order) for row in claims
        if (row.get("local_id") or "") in new_claim_ids
    ][:6]
    if delta.get("first_research"):
        change_status = "BASELINE"
        change_summary = "首次建立公司研究基线。"
    elif new_facts or delta.get("added_source_count"):
        change_status = "UPDATED"
        change_summary = "发现新的可引用来源或事实；是否改变核心判断仍需按下列条件验证。"
    else:
        change_status = "NO_CHANGE"
        change_summary = "本轮没有发现来自新增或更新来源、足以改变档案的新事实。"

    market = _market_view(quote or {}, consensus, guidance, sell_side, narrative)
    source_rows = [
        {
            "number": index,
            "id": row.get("local_id") or "",
            "title": _source_title(row),
            "url": row.get("url") or "",
            "published_at": row.get("published_at") or "",
            "source_type": row.get("source_type") or "",
            "source_skill": row.get("source_skill") or "",
            "source_label": row.get("source_label") or "",
            "evidence_role": row.get("evidence_role") or "",
            "source_grade": row.get("source_grade") or "",
            "rating": row.get("rating") or "",
        }
        for index, row in enumerate(sources, start=1)
    ]
    return {
        "schema_version": "company-dossier-v1",
        "company": {"name": name or "公司", "ticker": ticker or ""},
        "one_line_view": _one_line(name, business, growth, profit),
        "company_basics": {
            "products_and_customers": business,
            "segments": segments,
            "revenue_and_profit_sources": financials,
        },
        "moat": {
            "evidence": moat,
            "assessment": "已有直接证据，仍需验证其持续性。" if moat else UNKNOWN,
        },
        "financial_quality": {
            "evidence": financials,
            "assessment": _financial_assessment(financials, financial_statements),
            "risk_checks": financial_statements.get("risk_checks") or [],
        },
        "financial_statements": financial_statements,
        "industry_and_lifecycle_lens": financial_statements.get("analysis_lens") or {},
        "industry_position": {
            "evidence": industry,
            "assessment": "已有行业位置线索，仍需同行和份额口径交叉验证。" if industry else UNKNOWN,
        },
        "customer_supplier_exposure": customer_supplier,
        "capital_allocation": capital_allocation,
        "core_thesis": {
            "growth_drivers": growth,
            "profit_drivers": profit,
            "conditions": _conditions(growth, profit),
        },
        "expectations": {
            "management_guidance": guidance,
            "consensus": consensus,
            "sell_side": sell_side,
            "market_narrative": narrative,
            "revision_timeline": _expectation_timeline(
                guidance, consensus, sell_side, narrative, sources,
            ),
        },
        "price_and_expectations": market,
        "changes": {
            "status": change_status,
            "summary": change_summary,
            "new_facts": new_facts,
            "reclassified_old_facts": delta.get("reclassified_claim_count") or 0,
            "expectation_change": "UNKNOWN（缺少可比的前后两期预期数据）",
            "thesis_impact": "待验证" if change_status == "UPDATED" else ("未变化" if change_status == "NO_CHANGE" else "建立基线"),
        },
        "catalysts": catalysts,
        "risks_and_invalidation": {
            "risks": risks,
            "invalidation": _invalidation(growth, profit, risks),
        },
        "monitoring": _monitoring(growth, profit, guidance, consensus, financials),
        "source_coverage": _source_coverage(source_plan or [], sources),
        "sources": source_rows,
        "carried_from_previous": bool(previous),
    }


def apply_model_view(dossier: dict, data: dict, claims: list, delta: dict) -> dict:
    """Apply semantic organization while allowing references to known claims only."""
    result = dict(dossier)
    claim_map = {row.get("local_id"): row for row in claims if row.get("local_id")}
    source_order = {row.get("id"): row.get("number") for row in dossier.get("sources") or []}

    source_meta = {row.get("id"): row for row in dossier.get("sources") or []}

    def selected(ids, limit=6, tokens=(), source_skills=(), claim_types=()):
        rows = []
        for claim_id in ids or []:
            claim = claim_map.get(claim_id)
            value = (claim or {}).get("text") or (claim or {}).get("evidence_text") or ""
            source = source_meta.get((claim or {}).get("source_id") or "", {})
            semantic_match = (
                not tokens
                or any(token in value for token in tokens)
                or (source_skills and source.get("source_skill") in source_skills)
                or (claim_types and (claim.get("claim_type") or "").upper() in claim_types)
            )
            if claim and semantic_match:
                rows.append(_item(claim, source_order))
        return _unique(rows)[:limit]

    basics = data.get("company_basics") or {}
    result["company_basics"] = {
        "products_and_customers": selected(basics.get("products_and_customers")) or result["company_basics"]["products_and_customers"],
        "segments": selected(basics.get("segments"), tokens=("板块", "分部", "分行业", "分产品", "占比", "收入来源")) or result["company_basics"]["segments"],
        "revenue_and_profit_sources": selected(basics.get("revenue_and_profit_sources"), tokens=("收入", "利润", "毛利", "现金流")) or result["company_basics"]["revenue_and_profit_sources"],
    }
    moat = data.get("moat") or {}
    moat_rows = selected(moat.get("evidence"), tokens=(
        "核心竞争力", "自供", "稀缺", "专利", "技术", "研发", "认证", "定价", "份额", "规模出货", "转换成本",
    ))
    result["moat"] = {
        "evidence": moat_rows,
        "assessment": _short(moat.get("assessment")) if moat_rows else UNKNOWN,
    }
    thesis = data.get("core_thesis") or {}
    result["core_thesis"] = {
        "growth_drivers": selected(thesis.get("growth_drivers"), tokens=("增长", "订单", "出货", "销量", "价格", "需求", "产能", "利用率", "客户")) or result["core_thesis"]["growth_drivers"],
        "profit_drivers": selected(thesis.get("profit_drivers"), tokens=("利润", "毛利", "成本", "费用", "自供", "产品结构", "原材料", "汇率")) or result["core_thesis"]["profit_drivers"],
        "conditions": _strings(thesis.get("conditions"), 4) or result["core_thesis"]["conditions"],
    }
    expectations = data.get("expectations") or {}
    model_sell_side = selected(
        expectations.get("sell_side"), limit=12,
        tokens=("研报", "分析师", "证券预计", "券商预计", "盈利预测", "预测", "目标价", "评级", "上调", "下调", "PE", "EPS"),
        claim_types=("ESTIMATE",),
    )
    result["expectations"] = {
        "management_guidance": selected(expectations.get("management_guidance"), tokens=("指引", "经营目标", "公司预计", "管理层预计", "展望")) or result["expectations"]["management_guidance"],
        "consensus": selected(expectations.get("consensus"), tokens=("一致预期", "市场预期", "机构预期")) or result["expectations"]["consensus"],
        # The model organises the evidence but must not erase already verified
        # revisions simply because it chose a shorter presentation list.
        "sell_side": _unique(
            (result["expectations"].get("sell_side") or []) + model_sell_side
        )[:12],
        "market_narrative": selected(
            expectations.get("market_narrative"),
            tokens=("市场叙事", "主题", "概念", "估值", "景气", "争议"),
            source_skills=("market-narrative",),
        ) or result["expectations"]["market_narrative"],
        "revision_timeline": result["expectations"].get("revision_timeline") or [],
    }
    risks = data.get("risks_and_invalidation") or {}
    result["risks_and_invalidation"] = {
        "risks": selected(risks.get("risks"), tokens=("风险", "下滑", "下降", "承压", "波动", "减值", "依赖", "不利")) or result["risks_and_invalidation"]["risks"],
        "invalidation": _strings(risks.get("invalidation"), 5) or result["risks_and_invalidation"]["invalidation"],
    }
    result["expectations"]["revision_timeline"] = _expectation_timeline(
        result["expectations"].get("management_guidance") or [],
        result["expectations"].get("consensus") or [],
        result["expectations"].get("sell_side") or [],
        result["expectations"].get("market_narrative") or [],
        dossier.get("sources") or [],
    )
    result["catalysts"] = selected(data.get("catalysts"), limit=8, tokens=(
        "催化", "投产", "量产", "订单", "认证", "涨价", "发布", "出货", "扩产",
        "交付", "获批", "中标", "业绩预告",
    )) or result.get("catalysts") or []
    result["monitoring"] = _strings(data.get("monitoring"), 6) or result.get("monitoring") or []
    one_line = _short(data.get("one_line_view"), 260)
    if one_line:
        result["one_line_view"] = one_line

    market = data.get("price_and_expectations") or {}
    evidence_ids = market.get("evidence") or []
    has_expectation_evidence = bool(selected(evidence_ids)) and bool(
        result["expectations"]["management_guidance"]
        or result["expectations"]["consensus"]
        or result["expectations"]["sell_side"]
    )
    if has_expectation_evidence:
        result["price_and_expectations"]["price_implied_expectation"] = _short(
            market.get("price_implied_expectation"), 300,
        ) or result["price_and_expectations"]["price_implied_expectation"]
        result["price_and_expectations"]["expectation_gap"] = _short(
            market.get("expectation_gap"), 300,
        ) or result["price_and_expectations"]["expectation_gap"]
        direction = (market.get("gap_direction") or "").upper()
        if direction in ("POSITIVE", "NEGATIVE", "NEUTRAL", "UNKNOWN"):
            result["price_and_expectations"]["gap_direction"] = direction

    changes = data.get("changes") or {}
    if result["changes"]["status"] == "UPDATED":
        result["changes"]["expectation_change"] = _short(changes.get("expectation_change"), 240) or result["changes"]["expectation_change"]
        result["changes"]["thesis_impact"] = _short(changes.get("thesis_impact"), 240) or result["changes"]["thesis_impact"]
    return result


def _item(claim: dict, source_order: dict) -> dict:
    source_id = claim.get("source_id") or ""
    return {
        "text": claim.get("text") or claim.get("evidence_text") or "",
        "source_id": source_id,
        "source_number": source_order.get(source_id),
        "claim_id": claim.get("local_id") or "",
        "claim_type": claim.get("claim_type") or "",
        "estimator": claim.get("estimator") or "",
        "period": claim.get("period") or "",
        "comparison_basis": claim.get("comparison_basis") or "",
    }


def _sell_side_rows(claims: list, sources: list, source_order: dict, limit: int = 12) -> list:
    source_by_id = {row.get("local_id") or "": row for row in sources}
    tokens = (
        "研报", "分析师", "证券预计", "券商预计", "盈利预测", "预测", "目标价",
        "评级", "上调", "下调", "PE", "EPS",
    )
    candidates = []
    for claim in claims:
        value = claim.get("text") or claim.get("evidence_text") or ""
        if not value:
            continue
        if (claim.get("claim_type") or "").upper() != "ESTIMATE" and not any(
            token in value for token in tokens
        ):
            continue
        source = source_by_id.get(claim.get("source_id") or "", {})
        estimator = (claim.get("estimator") or "").strip()
        anonymous = not estimator or any(token in estimator for token in (
            "未具名", "机构综合", "机构（", "市场", "投资者",
        ))
        grade = (source.get("source_grade") or claim.get("source_grade") or "").upper()
        source_type = (source.get("source_type") or claim.get("source_type") or "").upper()
        if grade == "OPENED_REPORT" or source_type in ("SELL_SIDE", "BROKER"):
            source_rank = 0
        elif grade == "VENDOR_EXCERPT" and not anonymous:
            source_rank = 1
        elif grade == "VENDOR_EXCERPT":
            source_rank = 3
        else:
            source_rank = 2
        date_digits = re.sub(r"\D", "", source.get("published_at") or claim.get("source_published_at") or "")[:8]
        date_rank = -int(date_digits) if len(date_digits) == 8 else 0
        explicit_revision = (
            "目标价" in value
            and any(token in value for token in ("从", "由"))
            and any(token in value for token in ("上调", "下调", "调整", "提升", "推升"))
        )
        candidates.append((
            (source_rank, 1 if anonymous else 0, 0 if explicit_revision else 1, date_rank, len(value)),
            estimator or claim.get("source_id") or value[:80],
            explicit_revision,
            _item(claim, source_order),
        ))
    candidates.sort(key=lambda row: row[0])
    selected = []
    seen_text = set()

    def add(row) -> None:
        item = row[3]
        text = item.get("text") or ""
        if text and text not in seen_text:
            seen_text.add(text)
            selected.append(item)

    for row in candidates:
        if row[2]:
            add(row)
        if len(selected) >= min(4, limit):
            break
    seen_origins = set()
    for row in candidates:
        if row[1] in seen_origins:
            continue
        seen_origins.add(row[1])
        add(row)
        if len(selected) >= limit:
            return selected[:limit]
    for row in candidates:
        add(row)
        if len(selected) >= limit:
            break
    return selected[:limit]


def _expectation_timeline(
    guidance: list, consensus: list, sell_side: list, narrative: list, sources: list,
) -> list:
    """Keep dated expectation revisions instead of overwriting one number."""
    source_by_id = {
        (row.get("local_id") or row.get("id") or ""): row
        for row in sources
    }
    rows = []
    seen_items = set()
    for kind, items in (
        ("MANAGEMENT_GUIDANCE", guidance),
        ("CONSENSUS_DATA", consensus),
        ("SELL_SIDE_ESTIMATE", sell_side),
        ("MARKET_NARRATIVE", narrative),
    ):
        for item in items or []:
            if not isinstance(item, dict):
                continue
            source = source_by_id.get(item.get("source_id") or "", {})
            statement = item.get("text") or ""
            if not statement:
                continue
            identity = (
                item.get("claim_id") or statement,
                item.get("source_id") or "",
            )
            if identity in seen_items:
                continue
            seen_items.add(identity)
            source_type = source.get("source_type") or ""
            grade = source.get("source_grade") or (
                "RESEARCH_NOTE" if source_type == "RESEARCH_NOTE"
                else "OPENED_REPORT" if source_type in ("SELL_SIDE", "BROKER")
                else "SECONDARY_SOURCE"
            )
            rows.append({
                "date": source.get("published_at") or "",
                "institution": item.get("estimator") or _institution(statement, source),
                "kind": kind,
                "statement": statement,
                "period": item.get("period") or "",
                "comparison_basis": item.get("comparison_basis") or "",
                "rating": source.get("rating") or "",
                "source_id": item.get("source_id") or "",
                "source_number": item.get("source_number") or source.get("number"),
                "source_grade": grade,
                "latest_for_institution": True,
            })
    rows.sort(key=lambda row: (row.get("date") or "", row.get("source_number") or 0), reverse=True)
    latest_seen = set()
    for row in rows:
        institution = row.get("institution") or ""
        if institution and institution != "来源机构待确认":
            row["latest_for_institution"] = institution not in latest_seen
            latest_seen.add(institution)
    return rows[:16]


def _institution(statement: str, source: dict) -> str:
    names = (
        "花旗", "高盛", "瑞银", "摩根士丹利", "摩根大通", "美银", "汇丰", "野村",
        "中信证券", "中金公司", "华泰证券", "国泰海通", "开源证券", "招商证券",
        "申万宏源", "广发证券", "天风证券", "华创证券", "兴业证券", "国盛证券",
        "Citi", "Goldman Sachs", "UBS", "Morgan Stanley", "JPMorgan",
    )
    blob = " ".join((statement or "", source.get("title") or "", source.get("publisher") or ""))
    for name in names:
        if name.lower() in blob.lower():
            return name
    publisher = (source.get("publisher") or "").strip()
    if publisher and publisher != "同花顺 iFinD":
        return publisher
    return "来源机构待确认"


def _source_title(row: dict) -> str:
    title = (row.get("title") or row.get("publisher") or "").strip()
    if title and title.count("�") < 2:
        return title
    host = (urlparse(row.get("url") or "").hostname or "").removeprefix("www.")
    return "{0}（标题编码异常）".format(host or "网页来源")


def _unique(rows: Iterable[dict]) -> list:
    seen = set()
    result = []
    for row in rows:
        key = row.get("text") or ""
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(row)
    return result


def _source_coverage(source_plan: list, sources: list) -> list:
    counts = {}
    for row in sources:
        key = row.get("source_skill") or ""
        if key:
            counts[key] = counts.get(key, 0) + 1
    result = []
    for row in source_plan:
        name = row.get("name") or ""
        count = counts.get(name, int(row.get("source_count") or 0))
        status = row.get("status") or ("completed" if count else "pending")
        result.append({
            "name": name,
            "label": row.get("label") or name,
            "evidence_role": row.get("evidence_role") or "",
            "source_count": count,
            "status": status,
        })
    return result


def _short(value, limit: int = 220) -> str:
    text = str(value or "").strip()
    text = re.sub(r"\[C\d+\]", "", text)
    text = re.sub(r"\bC\d+\s*[:：]\s*", "", text)
    text = re.sub(r"\s{2,}", " ", text).strip()
    return text[:limit] if text else ""


def _strings(values, limit: int) -> list:
    result = []
    for value in values or []:
        text = _short(value, 240)
        if text and text not in result:
            result.append(text)
    return result[:limit]


def _one_line(name: str, business: list, growth: list, profit: list) -> str:
    if business:
        suffix = "；关键变化需继续跟踪增长和利润驱动。" if growth or profit else "；增长与利润驱动仍待补证。"
        return "{0}的已核对基本盘是：{1}{2}".format(name or "该公司", business[0]["text"], suffix)
    return "{0}的业务基本盘尚未从可引用正文中核对完整。".format(name or "该公司")


def _financial_assessment(financials: list, statements: dict | None = None) -> str:
    statements = statements or {}
    if statements.get("coverage_status") == "COMPLETE":
        return "最近三年官方年报核心财务口径已形成基线；下面继续检查利润现金含量、杠杆和资本开支。"
    if statements.get("records"):
        return statements.get("coverage_note") or "已有部分年度财务数据，缺失口径保持 UNKNOWN。"
    if not financials:
        return UNKNOWN
    has_cash = any("现金流" in row["text"] for row in financials)
    return "已有部分财务证据，但尚不能完整评价盈利质量。" if not has_cash else "已有利润与现金流证据，仍需统一报告期和口径后比较。"


def _conditions(growth: list, profit: list) -> list:
    conditions = []
    if growth:
        conditions.append("后续披露继续验证当前增长驱动，而不是只出现一次性增长。")
    if profit:
        conditions.append("收入增长能转化为毛利、经营利润或现金流改善。")
    if not conditions:
        conditions.append("先补齐量、价、成本、订单或产能的直接证据，再判断逻辑是否成立。")
    return conditions


def _invalidation(growth: list, profit: list, risks: list) -> list:
    rows = []
    if growth:
        rows.append("关键增长变量在后续财报或经营披露中停止改善。")
    if profit:
        rows.append("收入改善但毛利、经营利润或现金流持续背离。")
    if risks:
        rows.append("已披露风险由可能性变成持续经营事实。")
    return rows or ["当前证据不足以定义公司专属失效条件；下一轮必须补齐。"]


def _monitoring(growth: list, profit: list, guidance: list, consensus: list, financials: list) -> list:
    rows = []
    if growth:
        rows.append("核心增长变量：订单/销量/价格/产能利用率的下一期变化")
    if profit:
        rows.append("利润兑现：毛利率、费用率、经营利润率和经营现金流")
    if guidance:
        rows.append("公司指引：是否兑现、上调或下调")
    else:
        rows.append("补齐公司指引或管理层展望")
    if consensus:
        rows.append("一致预期：盈利预测修正方向及幅度")
    else:
        rows.append("补齐可验证的一致预期，避免把市场叙事当共识")
    if not financials:
        rows.append("补齐同口径历史财务与现金流")
    return rows[:6]


def _market_view(quote: dict, consensus: list, guidance: list, sell_side: list, narrative: list) -> dict:
    row = quote.get("row") or {}
    price = row.get("close") if quote.get("ok") else None
    quote_date = row.get("date") or ""
    try:
        stale_days = (date.today() - date.fromisoformat(quote_date)).days if quote_date else None
    except ValueError:
        stale_days = None
    expectation_inputs = consensus + guidance + sell_side
    if not expectation_inputs:
        gap = "UNKNOWN（缺少公司指引/一致预期/卖方预测，不能从叙事硬推预期差）"
    else:
        gap = "待验证（已有预期输入，但仍缺少反推股价隐含假设所需的盈利与估值口径）"
    return {
        "last_price": price,
        "price_date": quote_date or "UNKNOWN",
        "price_is_stale": stale_days is None or stale_days > 5,
        "market_data_source": quote.get("source") or "UNKNOWN",
        "technical": quote.get("technical") or {"ok": False, "message": "历史日线不足"},
        "valuation_context": narrative or [],
        "price_implied_expectation": "UNKNOWN（尚未完成反向估值/隐含预期分析）",
        "fundamental_expectation": expectation_inputs[:6],
        "expectation_gap": gap,
        "gap_direction": "UNKNOWN",
    }
