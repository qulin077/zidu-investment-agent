"""Grounded three-year financial statement analysis for company dossiers.

The extractor is deliberately conservative.  It reads only opened company
filings, keeps the source for every number, and leaves cells empty when a
filing layout cannot be parsed safely.  Calculations live here rather than in
the language model so the same inputs always produce the same ratios.
"""
from __future__ import annotations

from datetime import date
import re

from core.research import finance


_NUMBER = r"[-−—]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"

# Rows from the "主要会计数据和财务指标" table.  An annual report normally
# carries the current year, previous year, YoY, and year-2 in one row.
_SUMMARY_ROWS = {
    "revenue": r"营业\s*收入(?:（元）|\(元\))?",
    "net_profit_parent": r"归属于上市公司股东的\s*净利润(?:（元）|\(元\))?",
    "adjusted_net_profit": r"归属于上市公司股东的\s*扣除非经常性\s*损益的\s*净利\s*润(?:（元）|\(元\))?",
    "operating_cash_flow": r"经营活动产生的现金流\s*量净额(?:（元）|\(元\))?",
}

# Rows from the primary statements.  These usually carry current and prior
# year values.  Long labels are ordered before shorter overlapping labels.
_STATEMENT_ROWS = {
    "revenue": (r"营业收入",),
    "operating_cost": (r"营业成本",),
    "operating_profit": (r"营业利润",),
    "total_assets": (r"资产总计",),
    "total_liabilities": (r"负债合计",),
    "total_equity": (r"所有者权益合计", r"股东权益合计"),
    "current_assets": (r"流动资产合计",),
    "current_liabilities": (r"流动负债合计",),
    "cash": (r"货币资金",),
    "accounts_receivable": (r"应收账款",),
    "inventory": (r"存货",),
    "contract_liabilities": (r"合同负债",),
    "goodwill": (r"商誉",),
    "short_term_debt": (r"短期借款",),
    "long_term_debt": (r"长期借款",),
    "bonds_payable": (r"应付债券",),
    "debt_due_one_year": (r"一年内到期的非流动负债",),
    "capex": (r"购建固定资产、无形资产和其他长期资产支付的现金",),
}

_METRIC_LABELS = {
    "revenue": "营业收入",
    "revenue_yoy": "营收同比",
    "gross_margin": "毛利率",
    "operating_margin": "经营利润率",
    "net_profit_parent": "归母净利润",
    "adjusted_net_profit": "扣非归母净利润",
    "operating_cash_flow": "经营现金流净额",
    "cash_conversion": "现金利润比",
    "capex": "资本开支",
    "free_cash_flow": "自由现金流",
    "debt_to_assets": "资产负债率",
    "interest_bearing_debt": "有息负债",
    "current_ratio": "流动比率",
    "receivable_days_proxy": "应收/收入",
    "inventory_to_revenue": "存货/收入",
}


def completed_fiscal_years(as_of: str = "", count: int = 3) -> list[int]:
    """Return the most recent annual-report years expected to be available.

    PRC annual reports are normally due by the end of April.  Before May we do
    not require the immediately preceding year because it may not be filed yet.
    """
    current = _parse_date(as_of) or date.today()
    latest = current.year - (1 if current.month >= 5 else 2)
    return [latest - offset for offset in range(max(1, count))]


def build(
    *, corpus: list, sources: list, claims: list | None = None,
    previous: dict | None = None, as_of: str = "",
) -> dict:
    """Create the filing baseline used by the company dossier."""
    required = completed_fiscal_years(as_of)
    source_map = {row.get("local_id") or "": row for row in sources}
    reports = []
    periodic_reports = []
    for row in corpus or []:
        source_id = row.get("source_id") or ""
        source = dict(source_map.get(source_id) or {})
        # The opened corpus is the newest classification.  A legacy source row
        # may have been saved before the URL was recognised as an official
        # filing, so do not let stale metadata hide an otherwise valid report.
        if not source.get("source_type") and row.get("source_type"):
            source["source_type"] = row.get("source_type")
        body = row.get("text") or ""
        report_year = _report_year(source, body) if _is_annual_report(source, body) else None
        period = _report_period(source, body)
        if not report_year and not period:
            continue
        packed = {
            "year": report_year or int(period[:4]),
            "source_id": source_id,
            "source_number": _source_number(sources, source_id),
            "title": source.get("title") or ("年度报告" if report_year else "定期报告"),
            "url": source.get("url") or "",
            "text": body,
        }
        if report_year:
            reports.append(packed)
        else:
            packed["period"] = period
            periodic_reports.append(packed)

    # Latest filings win because they contain the latest comparative/restated
    # figures.  Older reports fill only still-empty cells.
    records: dict[int, dict] = {}
    for report in sorted(reports, key=lambda item: item["year"], reverse=True):
        _merge_report(records, report)

    prior = previous or {}
    for old in prior.get("records") or []:
        year = int(old.get("year") or 0)
        if not year:
            continue
        target = records.setdefault(year, {"year": year, "provenance": {}})
        for key, value in old.items():
            if key == "provenance":
                target.setdefault("provenance", {}).update({
                    metric: provenance for metric, provenance in (value or {}).items()
                    if metric not in target.get("provenance", {})
                })
            elif key not in target or target.get(key) is None:
                target[key] = value

    segment_rows = _merge_segments(
        _segments_from_reports(reports),
        _segments_from_claims(claims or [], source_map, sources),
        prior.get("segments") or [],
    )
    segment_rows = [row for row in segment_rows if row.get("year") in required]

    _calculate(records)
    ordered = [records[year] for year in sorted(records, reverse=True)]
    data_years = sorted({row["year"] for row in ordered if row.get("revenue") is not None}, reverse=True)
    official_sources = _merge_report_sources(_report_sources(reports), prior.get("official_sources") or [])
    found = sorted({int(row["year"]) for row in official_sources if row.get("year")}, reverse=True)
    risks = _risk_checks(ordered, reports)
    lens = _analysis_lens(claims or [], ordered)
    periodic_by_label = {
        row.get("period"): row
        for row in [_periodic_record(report) for report in periodic_reports]
        if row.get("period")
    }
    for old in prior.get("periodic_records") or []:
        if old.get("period") and old.get("period") not in periodic_by_label:
            periodic_by_label[old["period"]] = old
    periodic_records = sorted(
        periodic_by_label.values(),
        key=lambda item: _period_order(item.get("period") or ""), reverse=True,
    )
    return {
        "required_years": required,
        "found_years": found,
        "data_years": data_years,
        "coverage_status": "COMPLETE" if all(year in found and year in data_years for year in required) else "INCOMPLETE",
        "coverage_note": _coverage_note(required, found, data_years),
        "records": ordered,
        "periodic_records": periodic_records,
        "segments": segment_rows,
        "risk_checks": risks,
        "analysis_lens": lens,
        "official_sources": official_sources,
        "metric_labels": dict(_METRIC_LABELS),
        "unit": "亿元；比率为百分比",
    }


def _merge_report(records: dict[int, dict], report: dict) -> None:
    body = report["text"]
    report_year = report["year"]
    for metric, label in _SUMMARY_ROWS.items():
        values, evidence = _summary_values(body, label)
        if not values:
            continue
        years = (report_year, report_year - 1, report_year - 2)
        # values[2] is normally the change percentage, not an absolute value.
        absolutes = (values[0], values[1], values[3] if len(values) >= 4 else None)
        for year, value in zip(years, absolutes):
            if value is not None:
                _put(records, year, metric, value, report, evidence)

    for metric, labels in _STATEMENT_ROWS.items():
        values = []
        evidence = ""
        for label in labels:
            values, evidence = _statement_values(body, label)
            if values:
                break
        for offset, value in enumerate(values[:2]):
            _put(records, report_year - offset, metric, value, report, evidence)


def _summary_values(text: str, label: str) -> tuple[list[float], str]:
    pattern = re.compile(
        label + r"\s+(" + _NUMBER + r")\s+(" + _NUMBER + r")\s+(" + _NUMBER + r")\s*%\s+(" + _NUMBER + r")",
        re.MULTILINE,
    )
    match = pattern.search(text or "")
    if not match:
        return [], ""
    return [_number(value) for value in match.groups()], match.group(0)


def _statement_values(text: str, label: str) -> tuple[list[float], str]:
    # Financial statements often insert a note number between the label and
    # amounts (e.g. "货币资金 七、1 470,000,000 380,000,000").  Parse the
    # whole row and discard small note/page references before taking values.
    for match in re.finditer(label, text or ""):
        line_end = min(
            [pos for pos in ((text or "").find("\n", match.end()), (text or "").find("\r", match.end())) if pos >= 0]
            or [min(len(text or ""), match.end() + 180)]
        )
        evidence = (text or "")[match.start():line_end].strip()
        values = [_number(value) for value in re.findall(_NUMBER, evidence[len(match.group(0)):])]
        values = [value for value in values if value is not None and abs(value) >= 100000]
        if values:
            return values[:2], evidence
    return [], ""


def _put(records: dict, year: int, metric: str, value: float, report: dict, evidence: str) -> None:
    row = records.setdefault(year, {"year": year, "provenance": {}})
    if row.get(metric) is not None:
        return
    row[metric] = value
    row["provenance"][metric] = {
        "source_id": report.get("source_id") or "",
        "source_number": report.get("source_number"),
        "evidence": evidence,
    }


def _calculate(records: dict[int, dict]) -> None:
    for year, row in records.items():
        previous = records.get(year - 1) or {}
        revenue = row.get("revenue")
        operating_cost = row.get("operating_cost")
        gross_profit = None
        if revenue is not None and operating_cost is not None:
            gross_profit = revenue - operating_cost
            row["gross_profit"] = gross_profit
        interest_debt_parts = [
            row.get("short_term_debt"), row.get("long_term_debt"),
            row.get("bonds_payable"), row.get("debt_due_one_year"),
        ]
        if any(value is not None for value in interest_debt_parts):
            row["interest_bearing_debt"] = sum(value or 0.0 for value in interest_debt_parts)
        row.update({
            "revenue_yoy": finance.growth(revenue, previous.get("revenue")),
            "gross_margin": finance.gross_margin(gross_profit, revenue),
            "operating_margin": finance.operating_margin(row.get("operating_profit"), revenue),
            "net_margin": finance._div(row.get("net_profit_parent"), revenue),
            "cash_conversion": finance.cash_conversion(row.get("operating_cash_flow"), row.get("net_profit_parent")),
            "capex_intensity": finance.capex_intensity(row.get("capex"), revenue),
            "debt_to_assets": finance._div(row.get("total_liabilities"), row.get("total_assets")),
            "current_ratio": finance._div(row.get("current_assets"), row.get("current_liabilities")),
            "receivable_days_proxy": finance._div(row.get("accounts_receivable"), revenue),
            "inventory_to_revenue": finance._div(row.get("inventory"), revenue),
        })
        if row.get("operating_cash_flow") is not None and row.get("capex") is not None:
            row["free_cash_flow"] = row["operating_cash_flow"] - row["capex"]


def _risk_checks(records: list[dict], reports: list[dict]) -> list[dict]:
    checks = []
    latest = records[0] if records else {}
    debt_ratio = latest.get("debt_to_assets")
    if debt_ratio is not None:
        level = "WATCH" if debt_ratio >= 0.70 else "OK"
        checks.append(_risk("资产负债率", level, debt_ratio, "高杠杆阈值只作通用筛查，仍需与同行和债务期限结构比较。", latest))
    current_ratio = latest.get("current_ratio")
    if current_ratio is not None:
        level = "WATCH" if current_ratio < 1 else "OK"
        checks.append(_risk("短期偿债", level, current_ratio, "流动比率低于 1 时需继续核对现金、授信和短债到期。", latest))
    cash_conversion = latest.get("cash_conversion")
    if cash_conversion is not None:
        level = "WATCH" if cash_conversion < 0.8 else "OK"
        checks.append(_risk("利润现金含量", level, cash_conversion, "经营现金流/归母净利润持续偏低，需检查应收、存货和一次性利润。", latest))
    negative_fcf = [row.get("year") for row in records[:3] if row.get("free_cash_flow") is not None and row["free_cash_flow"] < 0]
    if negative_fcf:
        checks.append({
            "name": "自由现金流",
            "status": "WATCH" if len(negative_fcf) >= 2 else "INFO",
            "value": "{0} 年为负".format("、".join(str(year) for year in negative_fcf)),
            "interpretation": "区分扩产投入与经营恶化，并核对资本开支回报。",
            "source_number": _row_source(records[0] if records else {}),
        })
    audit = _audit_signal(reports)
    checks.append(audit)
    if not checks[:-1]:
        checks.insert(0, {
            "name": "量化风险筛查", "status": "UNKNOWN", "value": "缺少资产负债表/现金流量表可解析数据",
            "interpretation": "不能因为没有解析到数字就判断没有风险。", "source_number": None,
        })
    return checks


def _audit_signal(reports: list[dict]) -> dict:
    risky = ("保留意见", "无法表示意见", "否定意见", "非标准无保留意见")
    for report in reports:
        body = report.get("text") or ""
        for token in risky:
            if token in body and "标准无保留意见" not in body[max(0, body.find(token) - 20):body.find(token) + len(token) + 20]:
                return {
                    "name": "审计意见", "status": "WATCH", "value": token,
                    "interpretation": "必须阅读审计报告、形成意见的基础和关键审计事项。",
                    "source_number": report.get("source_number"),
                }
    if any("标准无保留意见" in (report.get("text") or "") for report in reports):
        return {
            "name": "审计意见", "status": "OK", "value": "检索到标准无保留意见",
            "interpretation": "无保留意见不等于财务没有经营或估值风险。",
            "source_number": next((row.get("source_number") for row in reports if "标准无保留意见" in (row.get("text") or "")), None),
        }
    return {
        "name": "审计意见", "status": "UNKNOWN", "value": "未从已读正文中核对",
        "interpretation": "下一步直接读取审计报告意见段和关键审计事项。", "source_number": None,
    }


def _analysis_lens(claims: list, records: list) -> dict:
    blob = " ".join((row.get("text") or row.get("evidence_text") or "") for row in claims)
    families = [
        ("电子材料与制造", ("覆铜板", "PCB", "FPC", "电子电路", "铜箔"),
         ["销量与 ASP", "产能利用率", "产品结构与单价", "铜/树脂等原料成本", "存货周转", "应收与客户集中度", "资本开支与新增产能回报"]),
        ("消费与品牌", ("消费品", "品牌", "门店", "经销商"),
         ["同店/销量", "价格与产品结构", "渠道库存", "获客与复购", "毛利率", "营运资本"]),
        ("软件与订阅", ("SaaS", "订阅", "软件服务", "云服务"),
         ["ARR/订阅收入", "留存率", "客户数与客单价", "毛利率", "获客成本", "经营现金流"]),
        ("医药与创新研发", ("创新药", "临床", "管线", "医药"),
         ["管线阶段与成功概率", "研发投入", "专利期限", "商业化进度", "现金跑道", "单品集中度"]),
        ("周期与资源", ("矿", "金属", "化工", "煤", "油气"),
         ["产销量", "产品价格", "现金成本曲线", "资本开支", "库存周期", "净负债"]),
        ("金融", ("银行", "保险", "证券"),
         ["资产质量", "资本充足率", "净息差/承保利润", "拨备", "流动性", "ROE"]),
    ]
    family = "通用企业"
    metrics = ["量价或客户数×客单价", "毛利率与费用率", "经营现金流", "营运资本", "资本开支", "ROIC/ROE", "杠杆与偿债"]
    matched = []
    for label, tokens, focus in families:
        hits = [token for token in tokens if token in blob]
        if hits:
            family, metrics, matched = label, focus, hits
            break

    stage = "UNKNOWN"
    stage_reason = "至少需要连续三年可比收入和再投资数据后再判断。"
    usable = [row for row in records if row.get("revenue_yoy") is not None]
    if len(usable) >= 2:
        average = sum(row["revenue_yoy"] for row in usable[:2]) / min(2, len(usable))
        if average >= 0.20:
            stage, stage_reason = "HIGH_GROWTH", "近两期平均营收增速达到 20% 以上；仍需用市场空间和再投资效率验证持续性。"
        elif average >= 0.05:
            stage, stage_reason = "MATURE_GROWTH", "近两期平均营收保持中个位数以上增长，重点转向利润率、ROIC 与现金兑现。"
        elif average >= -0.05:
            stage, stage_reason = "MATURE_OR_CYCLICAL", "近两期营收总体平稳；需区分成熟稳定与周期位置。"
        else:
            stage, stage_reason = "DECLINE_OR_CYCLE_DOWN", "近两期平均营收负增长；需区分结构性衰退与周期下行。"
    return {
        "industry_family": family,
        "matched_terms": matched,
        "lifecycle_stage": stage,
        "stage_reason": stage_reason,
        "priority_metrics": metrics,
        "note": "行业与阶段决定重点指标，但不改变会计口径和证据要求。阶段是分析标签，不是公司披露事实。",
    }


def _segments_from_claims(claims: list, source_map: dict, sources: list) -> list[dict]:
    rows = []
    seen = set()
    pattern = re.compile(
        r"(?P<name>[\u4e00-\u9fffA-Za-z0-9/+\-]{2,24}(?:板块|业务|产品|组件|模组))"
        r"[^。；]{0,30}?(?:收入|贡献)\s*(?P<revenue>\d+(?:\.\d+)?)\s*亿"
        r"[^。；]{0,40}?(?:占(?:总)?(?:营业)?收入|占比)\s*(?P<share>\d+(?:\.\d+)?)\s*%"
    )
    for claim in claims:
        value = claim.get("text") or claim.get("evidence_text") or ""
        match = pattern.search(value)
        if not match:
            continue
        source_id = claim.get("source_id") or ""
        source = source_map.get(source_id) or {}
        year = _report_year(source, value)
        key = (year, match.group("name"))
        if key in seen:
            continue
        seen.add(key)
        rows.append({
            "year": year, "segment": match.group("name"),
            "revenue_yuan": float(match.group("revenue")) * 100000000,
            "revenue_share": float(match.group("share")) / 100,
            "gross_margin": None,
            "source_number": _source_number(sources, source_id),
        })
    return sorted(rows, key=lambda item: (item.get("year") or 0, item.get("revenue_yuan") or 0), reverse=True)


def _is_annual_report(source: dict, body: str) -> bool:
    if (source.get("source_type") or "") != "COMPANY_FILING":
        return False
    blob = " ".join((source.get("title") or "", (body or "")[:2500]))
    if any(token in blob for token in ("半年度报告", "第一季度报告", "第三季度报告")):
        return False
    return "年度报告" in blob and "摘要" not in (source.get("title") or "")


def _report_year(source: dict, body: str) -> int | None:
    for value in (source.get("title") or "", (body or "")[:3000]):
        match = re.search(r"(20\d{2})\s*年?\s*年度报告", value)
        if match:
            return int(match.group(1))
    published = source.get("published_at") or ""
    match = re.match(r"(20\d{2})", published)
    return int(match.group(1)) - 1 if match else None


def _report_period(source: dict, body: str) -> str:
    if (source.get("source_type") or "") != "COMPANY_FILING":
        return ""
    for value in (source.get("title") or "", (body or "")[:3000]):
        match = re.search(r"(20\d{2})\s*年\s*(第一季度|半年度|第三季度)报告", value)
        if match:
            suffix = {"第一季度": "Q1", "半年度": "H1", "第三季度": "Q3"}[match.group(2)]
            return match.group(1) + suffix
    return ""


def _periodic_record(report: dict) -> dict:
    row = {
        "period": report.get("period") or "",
        "year": report.get("year"),
        "source_number": report.get("source_number"),
        "provenance": {},
    }
    comparatives = {}
    body = report.get("text") or ""
    for metric, label in _SUMMARY_ROWS.items():
        values, evidence = _statement_values(body, label)
        if not values:
            continue
        row[metric] = values[0]
        if len(values) > 1:
            comparatives[metric] = values[1]
        row["provenance"][metric] = {
            "source_id": report.get("source_id") or "",
            "source_number": report.get("source_number"),
            "evidence": evidence,
        }
    for metric, labels in _STATEMENT_ROWS.items():
        if row.get(metric) is not None:
            continue
        for label in labels:
            values, evidence = _statement_values(body, label)
            if not values:
                continue
            row[metric] = values[0]
            row["provenance"][metric] = {
                "source_id": report.get("source_id") or "",
                "source_number": report.get("source_number"),
                "evidence": evidence,
            }
            break
    temporary = {int(report.get("year") or 0): row}
    if comparatives.get("revenue") is not None:
        temporary[int(report.get("year") or 0) - 1] = {"revenue": comparatives["revenue"], "provenance": {}}
    _calculate(temporary)
    row["revenue_yoy"] = finance.growth(row.get("revenue"), comparatives.get("revenue"))
    return row


def _period_order(value: str) -> tuple:
    match = re.match(r"(20\d{2})(Q1|H1|Q3)", value or "")
    if not match:
        return 0, 0
    return int(match.group(1)), {"Q1": 1, "H1": 2, "Q3": 3}[match.group(2)]


def _number(value: str) -> float | None:
    clean = (value or "").replace(",", "").replace("−", "-").replace("—", "-")
    if clean in ("", "-"):
        return None
    return float(clean)


def _segments_from_reports(reports: list[dict]) -> list[dict]:
    rows = []
    for report in sorted(reports, key=lambda item: item.get("year") or 0, reverse=True):
        body = report.get("text") or ""
        year = int(report.get("year") or 0)
        start = _first_position(body, ("（1） 营业收入构成", "（1）营业收入构成", "(1) 营业收入构成"))
        if start < 0:
            continue
        window = body[start:start + 18000]
        product_start = window.find("分产品")
        product_end = window.find("分地区", product_start + 3)
        if product_start < 0 or product_end < 0:
            continue
        block = window[product_start + len("分产品"):product_end]
        for line in block.splitlines():
            parsed = _segment_revenue_line(line)
            if not parsed:
                continue
            name, current_revenue, current_share, previous_revenue, previous_share, yoy = parsed
            rows.extend([
                {
                    "year": year, "segment": name, "revenue_yuan": current_revenue,
                    "revenue_share": current_share, "revenue_yoy": yoy, "gross_margin": None,
                    "source_number": report.get("source_number"),
                },
                {
                    "year": year - 1, "segment": name, "revenue_yuan": previous_revenue,
                    "revenue_share": previous_share, "revenue_yoy": None, "gross_margin": None,
                    "source_number": report.get("source_number"),
                },
            ])
        _apply_segment_margins(rows, window, year, report.get("source_number"))
    return _merge_segments(rows)


def _segment_revenue_line(line: str):
    value = re.sub(r"\s+", " ", (line or "").strip())
    match = re.match(
        r"(.{1,36}?)\s+(" + _NUMBER + r")\s+(" + _NUMBER + r")%\s+"
        r"(" + _NUMBER + r")\s+(" + _NUMBER + r")%\s+(" + _NUMBER + r")%$",
        value,
    )
    if not match:
        return None
    name = re.sub(r"\s+", "", match.group(1)).strip("：:")
    if len(name) < 2 or any(token in name for token in ("金额", "占营业收入", "营业收入合计")):
        return None
    numbers = [_number(item) for item in match.groups()[1:]]
    if any(item is None for item in numbers):
        return None
    return name, numbers[0], numbers[1] / 100, numbers[2], numbers[3] / 100, numbers[4] / 100


def _apply_segment_margins(rows: list[dict], window: str, year: int, source_number) -> None:
    marker = window.find("占公司营业收入或营业利润 10%以上")
    if marker < 0:
        return
    chunk = window[marker:marker + 6000]
    start = chunk.find("分产品")
    end = chunk.find("分地区", start + 3)
    if start < 0 or end < 0:
        return
    for line in chunk[start + 3:end].splitlines():
        value = re.sub(r"\s+", " ", line.strip())
        match = re.match(
            r"(.{1,48}?)\s+(" + _NUMBER + r")\s+(" + _NUMBER + r")\s+(" + _NUMBER + r")%\s+"
            r"(" + _NUMBER + r")%\s+(" + _NUMBER + r")%\s+(" + _NUMBER + r")%$",
            value,
        )
        if not match:
            continue
        name = re.sub(r"\s+", "", match.group(1))
        margin = _number(match.group(4))
        delta = _number(match.group(7))
        if margin is None:
            continue
        for row in rows:
            if row.get("year") not in (year, year - 1) or not _same_segment(row.get("segment") or "", name):
                continue
            row["source_number"] = row.get("source_number") or source_number
            row["gross_margin"] = margin / 100 if row["year"] == year else (
                (margin - delta) / 100 if delta is not None else None
            )


def _same_segment(left: str, right: str) -> bool:
    compact_left = re.sub(r"[（(].*?[）)]|及其相关产品|含半固化片|板", "", left)
    compact_right = re.sub(r"[（(].*?[）)]|及其相关产品|含半固化片|板", "", right)
    return bool(compact_left and compact_right and (compact_left in compact_right or compact_right in compact_left))


def _merge_segments(*groups: list[dict]) -> list[dict]:
    result = []
    positions = {}
    for row in [item for group in groups for item in (group or [])]:
        key = (row.get("year"), row.get("segment"))
        if not key[0] or not key[1]:
            continue
        if key not in positions:
            positions[key] = len(result)
            result.append(dict(row))
            continue
        target = result[positions[key]]
        for field, value in row.items():
            if target.get(field) is None and value is not None:
                target[field] = value
    return sorted(result, key=lambda item: (item.get("year") or 0, item.get("revenue_yuan") or 0), reverse=True)


def _first_position(value: str, tokens: tuple[str, ...]) -> int:
    positions = [value.find(token) for token in tokens if value.find(token) >= 0]
    return min(positions) if positions else -1


def _parse_date(value: str) -> date | None:
    try:
        return date.fromisoformat((value or "")[:10])
    except ValueError:
        return None


def _source_number(sources: list, source_id: str) -> int | None:
    for index, row in enumerate(sources, start=1):
        if row.get("local_id") == source_id:
            return index
    return None


def _row_source(row: dict) -> int | None:
    provenance = row.get("provenance") or {}
    for metric in ("revenue", "total_assets", "operating_cash_flow"):
        if (provenance.get(metric) or {}).get("source_number"):
            return provenance[metric]["source_number"]
    return None


def _risk(name: str, status: str, value: float, interpretation: str, row: dict) -> dict:
    return {
        "name": name, "status": status, "value": value,
        "interpretation": interpretation, "source_number": _row_source(row),
    }


def _coverage_note(required: list[int], found: list[int], data_years: list[int]) -> str:
    missing_reports = [year for year in required if year not in found]
    missing_data = [year for year in required if year not in data_years]
    if not missing_reports and not missing_data:
        return "最近三年官方年报的核心利润与现金流口径已形成基线。"
    parts = []
    if missing_reports:
        parts.append("尚未打开 {0} 年官方年报".format("、".join(str(year) for year in missing_reports)))
    if missing_data:
        parts.append("缺少 {0} 年可核对核心财务数据".format("、".join(str(year) for year in missing_data)))
    return "；".join(parts) + "；对应表格保持 UNKNOWN，不用其他年份或媒体数据代填。"


def _report_sources(reports: list[dict]) -> list[dict]:
    result = []
    seen = set()
    for row in sorted(reports, key=lambda item: item["year"], reverse=True):
        key = (row.get("year"), row.get("source_id"))
        if key in seen:
            continue
        seen.add(key)
        result.append({
            "year": row.get("year"), "source_id": row.get("source_id"),
            "source_number": row.get("source_number"), "title": row.get("title"), "url": row.get("url"),
        })
    return result


def _merge_report_sources(current: list[dict], previous: list[dict]) -> list[dict]:
    result = []
    seen = set()
    for row in list(current or []) + list(previous or []):
        key = (row.get("year"), row.get("source_id") or row.get("url"))
        if not key[0] or key in seen:
            continue
        seen.add(key)
        result.append(dict(row))
    return sorted(result, key=lambda item: item.get("year") or 0, reverse=True)
