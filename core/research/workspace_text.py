"""回答只引用已打开正文。不写买卖、目标价和仓位。"""
from __future__ import annotations

import re
from html import unescape

from core.research.types import FORBIDDEN_PHRASES

# A broker target price may appear in a cited source title.  Reporting that a
# sell-side source changed its target is not the product giving a target price;
# direct buy/sell/position language remains blocked.
_ADVICE = tuple(token for token in FORBIDDEN_PHRASES if token != "目标价") + ("值得买", "建议买", "建议卖")


def advice_hits(text: str) -> list:
    return [token for token in _ADVICE if token in (text or "")]


def render(kind, skill, name, primary, claims, gaps, notice, sources):
    if kind == "why":
        return render_why(claims)
    if kind == "comparison":
        return render_compare(primary, name, claims, gaps, notice)
    if skill == "industry-research":
        lines = [
            "研究档案 · 基于已读证据 · 持续更新",
            "当前判断",
            "这是行业问题，技能是 industry-research。",
            "为什么这么看",
            "还没有把未打开的材料写成事实。" if not claims else "下面只引用已打开正文。",
            "核心证据",
        ]
        lines.extend("[{0}] {1}".format(row["local_id"], row["text"]) for row in claims[:4])
        lines.extend([
            "现在还不知道什么",
            "；".join(gaps) if gaps else "边界和传导仍要继续核对。",
            "最大风险",
            "用行业叙事代替已打开的来源。",
        ])
        text = "\n".join(lines)
        if notice:
            text = notice + "\n" + text
        return text, [row["local_id"] for row in claims[:4]], _sources(claims[:4])
    exposure = "INDIRECT" if any(
        token in " ".join(row.get("text") or "" for row in claims)
        for token in ("PCB", "FPC", "光模块", "电源")
    ) else "UNKNOWN"
    lines = ["研究档案 · 基于已读证据 · 持续更新"]
    if notice:
        lines.append(notice)
    lines.extend([
        "当前判断",
        "{0}：{1}".format(name or "这家公司", claims[0]["text"]) if claims else "{0}还没有可引用的正文。".format(name or "这家公司"),
        "为什么这么看",
        "判断只来自已打开正文里的原句。搜索摘要没有当成证据。",
        "核心证据",
    ])
    refs = []
    for row in claims[:4]:
        lines.append("[{0}] {1}".format(row["local_id"], row["text"]))
        refs.append(row["local_id"])
    lines.extend([
        "现在还不知道什么",
        "；".join(gaps) if gaps else "一致预期和预期差仍是 UNKNOWN。",
        "最大风险",
        "把送样、认证、媒体映射或产品存在写成已确认收入。商业阶段是 UNKNOWN，暴露类型是 {0}。".format(exposure),
    ])
    return "\n".join(lines), refs, _sources(claims[:4])


def render_company(dossier: dict, notice: str = ""):
    """Render the user-facing dossier without exposing internal Claim IDs."""
    basics = dossier.get("company_basics") or {}
    moat = dossier.get("moat") or {}
    thesis = dossier.get("core_thesis") or {}
    expectations = dossier.get("expectations") or {}
    market = dossier.get("price_and_expectations") or {}
    technical = market.get("technical") or {}
    changes = dossier.get("changes") or {}
    risks = dossier.get("risks_and_invalidation") or {}
    lines = []
    if notice:
        lines.append(notice)
    completion = dossier.get("research_completion") or {}
    if completion:
        status = completion.get("status") or "PARTIAL"
        mode = completion.get("mode") or "FULL_DOSSIER"
        if status == "COMPLETE":
            lines.append("研究覆盖：{0} · 已完成 {1}/{2} 项必需检查".format(
                mode, completion.get("passed_count") or 0, completion.get("checked_count") or 0,
            ))
        else:
            lines.append("研究覆盖：{0} · {1} · 已完成 {2}/{3} 项；以下结论不是完整研究结论".format(
                mode, status, completion.get("passed_count") or 0, completion.get("checked_count") or 0,
            ))
            gaps = (completion.get("missing_labels") or []) + (completion.get("attempted_unavailable_labels") or [])
            if gaps:
                lines.append("待补覆盖：" + "、".join(gaps))
    lines.extend([
        "# 公司档案",
        "基于已读证据 · 持续更新",
        "## 一句话判断",
        dossier.get("one_line_view") or "尚未形成可核对判断。",
    ])
    _analyst_summary(lines, dossier)
    lines.extend([
        "## 本轮变化",
        changes.get("summary") or "尚未完成变化核对。",
        "## 公司基本盘",
    ])
    _section(lines, "卖什么、卖给谁", basics.get("products_and_customers"))
    _section(lines, "业务分部", basics.get("segments"))
    _section(lines, "收入与利润来源", basics.get("revenue_and_profit_sources"))
    statements = dossier.get("financial_statements") or {}
    _financial_tables(lines, statements)
    lines.append("## 财务质量")
    financial = dossier.get("financial_quality") or {}
    lines.append(financial.get("assessment") or "UNKNOWN（尚无已核对证据）")
    _rows(lines, financial.get("evidence"), "UNKNOWN（尚无已核对财务证据）")
    if financial.get("risk_checks"):
        lines.append("### 财务风险筛查")
        for row in financial.get("risk_checks") or []:
            source = " [{0}]".format(row.get("source_number")) if row.get("source_number") else ""
            lines.append("- **{0} · {1}**：{2}。{3}{4}".format(
                row.get("name") or "检查项", row.get("status") or "UNKNOWN",
                _risk_value(row.get("value"), row.get("name") or ""), row.get("interpretation") or "", source,
            ))
    lens = dossier.get("industry_and_lifecycle_lens") or {}
    if lens:
        lines.extend([
            "## 行业与生命周期分析镜头",
            "- 行业类型：{0}".format(lens.get("industry_family") or "UNKNOWN"),
            "- 生命周期：{0}。{1}".format(lens.get("lifecycle_stage") or "UNKNOWN", lens.get("stage_reason") or ""),
            "- 本行业优先看：{0}".format("、".join(lens.get("priority_metrics") or []) or "UNKNOWN"),
            "- 说明：{0}".format(lens.get("note") or "行业差异不改变证据要求。"),
        ])
    lines.append("## 核心壁垒")
    _rows(lines, moat.get("evidence"), moat.get("assessment") or "UNKNOWN")
    lines.append("## 行业位置与上下游暴露")
    industry = dossier.get("industry_position") or {}
    lines.append(industry.get("assessment") or "UNKNOWN（尚无已核对证据）")
    _rows(lines, industry.get("evidence"), "UNKNOWN（尚无已核对行业位置）")
    _section(lines, "客户与供应商暴露", dossier.get("customer_supplier_exposure"))
    _section(lines, "资本配置", dossier.get("capital_allocation"))
    lines.append("## 当前核心判断")
    _section(lines, "核心增长变量", thesis.get("growth_drivers"))
    _section(lines, "利润驱动", thesis.get("profit_drivers"))
    _section(lines, "判断成立的条件", thesis.get("conditions"))
    lines.append("## 市场预期")
    _section(lines, "公司指引", expectations.get("management_guidance"))
    _section(lines, "一致预期", expectations.get("consensus"))
    _section(lines, "卖方预测", expectations.get("sell_side"))
    _section(lines, "市场叙事", expectations.get("market_narrative"))
    _expectation_timeline(lines, expectations.get("revision_timeline") or [])
    lines.extend([
        "## 股价与预期",
        "行情：{0}（{1}{2}）".format(
            market.get("last_price") if market.get("last_price") is not None else "UNKNOWN",
            market.get("price_date") or "UNKNOWN",
            "，行情可能过期" if market.get("price_is_stale") else "",
        ),
        "股价隐含预期：{0}".format(market.get("price_implied_expectation") or "UNKNOWN"),
        "基本面与股价的 GAP：{0}".format(market.get("expectation_gap") or "UNKNOWN"),
    ])
    lines.append("### 技术面快照")
    if technical.get("ok"):
        ma = technical.get("ma") or {}
        macd = technical.get("macd") or {}
        position = (technical.get("range_20d") or {}).get("position_pct")
        lines.extend([
            "- 趋势：{0}".format(technical.get("trend") or "UNKNOWN"),
            "- 均线：MA5 {0} / MA20 {1} / MA60 {2}".format(
                _value(ma.get("5")), _value(ma.get("20")), _value(ma.get("60")),
            ),
            "- 动量：20日涨跌 {0}% / RSI14 {1} / MACD柱 {2}".format(
                _value(technical.get("return_20d_pct")), _value(technical.get("rsi_14")),
                _value(macd.get("histogram")),
            ),
            "- 波动与位置：ATR14 {0}% / 20日区间位置 {1}%".format(
                _value(technical.get("atr_14_pct")), _value(position),
            ),
            "- 口径：{0}".format(technical.get("disclaimer") or "公开日线本地计算。"),
        ])
    else:
        lines.append("- UNKNOWN（{0}）".format(technical.get("message") or "没有足够历史日线"))
    lines.append("## 催化剂")
    _rows(lines, dossier.get("catalysts"), "UNKNOWN（尚无已核对催化）")
    lines.append("## 风险与失效条件")
    _rows(lines, risks.get("risks"), "UNKNOWN（尚无已核对风险）")
    for item in risks.get("invalidation") or []:
        lines.append("- 失效条件：{0}".format(item))
    lines.append("## 下一步监控")
    for item in dossier.get("monitoring") or []:
        lines.append("- {0}".format(item))
    coverage = dossier.get("source_coverage") or []
    if coverage:
        lines.append("## 数据来源覆盖")
        for row in coverage:
            count = int(row.get("source_count") or 0)
            status = "已读取 {0} 份".format(count) if count else "本轮没有打开可引用正文"
            lines.append("- {0} · {1}：{2}".format(
                row.get("label") or row.get("name") or "来源",
                row.get("evidence_role") or "补充证据",
                status,
            ))
    lines.extend([
        "## 来源",
        "| 编号 | 来源 | 日期 | 用途 |",
        "| ---: | --- | --- | --- |",
    ])
    for row in dossier.get("sources") or []:
        number = row.get("number")
        title = row.get("title") or "来源"
        url = row.get("url") or ""
        published = row.get("published_at") or "网页未标注发布日期"
        is_web = url.startswith(("http://", "https://"))
        label = "[{0}]".format(title) if is_web else title
        linked = "{0}({1})".format(label, url) if is_web else label
        role = "补充资料"
        if row.get("source_label") or row.get("evidence_role"):
            role = "{0}{1}".format(
                row.get("source_label") or "",
                " / " + row.get("evidence_role") if row.get("evidence_role") else "",
            )
        lines.append("| [{0}] | {1} | {2} | {3} |".format(
            number, linked.replace("|", "／"), published, role,
        ))
    refs = [row.get("claim_id") for row in _all_items(dossier) if row.get("claim_id")]
    source_refs = [row.get("id") for row in dossier.get("sources") or [] if row.get("id")]
    rendered = "\n".join(lines)
    rendered = re.sub(r"\[C\d+\]", "", rendered)
    rendered = re.sub(r"\bC\d+\s*[:：]\s*", "", rendered)
    rendered = rendered.replace("UNKNOWN（", "待核对（")
    rendered = re.sub(r"\bUNKNOWN\b", "待核对", rendered)
    return rendered, refs, source_refs


def render_industry(dossier: dict, notice: str = ""):
    """Render a long-lived industry dossier, not a one-off market article."""
    lines = []
    if notice:
        lines.append(notice)
    completion = dossier.get("research_completion") or {}
    if completion:
        lines.append("研究覆盖：行业长期跟踪 · {0} · 已完成 {1}/{2} 项必需检查".format(
            completion.get("status") or "PARTIAL",
            completion.get("passed_count") or 0,
            completion.get("checked_count") or 0,
        ))
    lines.extend([
        "# 行业跟踪档案",
        "结构基线与变化日志分开保存 · 持续更新",
    ])
    playbook = dossier.get("playbook") or {}
    if playbook and playbook.get("id") != "generic":
        focus = (playbook.get("focus_segment") or {}).get("label") or "全产业链"
        lines.append("研究 Playbook：{0} · 产业域：{1} · 聚焦：{2}".format(
            playbook.get("label") or "通用行业", playbook.get("domain") or "未分类行业", focus,
        ))
    lines.extend([
        "## 当前核心判断",
        dossier.get("one_line_view") or "尚未形成有证据支持的行业判断。",
    ])
    _analyst_summary(lines, dossier)
    lines.append("## 本轮逻辑变化")
    _rows(lines, dossier.get("changes"), "本轮没有抽取到足以改变行业判断的新事实。")
    lines.append("## 行业边界与基本产业逻辑")
    _rows(lines, dossier.get("industry_boundary"), "UNKNOWN（行业边界与产品范围尚未核对）")
    lines.append("## 历史基准、生命周期与参考类")
    _rows(lines, dossier.get("reference_class"), "UNKNOWN（尚未用历史基准率和参考类约束当前叙事）")
    lines.append("## 产业链与价值传导")
    _rows(lines, dossier.get("value_chain"), "UNKNOWN（上下游节点与传导仍待核对）")
    lines.append("## 叙事到数字的因果模型")
    _rows(lines, dossier.get("causal_model"), "UNKNOWN（尚未把核心叙事映射为输入、中间变量和可验证输出）")
    lines.append("## 结构变化与行业阶段")
    _rows(lines, dossier.get("structural_change"), "UNKNOWN（需求、供给、技术或政策变化仍待核对）")
    lines.append("## 技术路线与商业化阶段")
    _rows(lines, dossier.get("technology_route"), "UNKNOWN（尚未区分概念、送样、验证、量产和规模收入）")
    lines.append("## 政策、产地与供应链约束")
    _rows(lines, dossier.get("policy_supply_chain"), "UNKNOWN（政策状态、适用范围、产地/BOM 口径和时间仍待核对）")
    lines.append("## 产业链价值量迁移")
    _rows(lines, dossier.get("value_migration"), "UNKNOWN（尚未说明哪些环节受益/受损、幅度和成立条件）")
    lines.append("## 量价成本与价值量")
    _rows(lines, dossier.get("economics"), "UNKNOWN（量、价、成本、产能和利润率仍待核对）")
    lines.append("## 资本回报与增长质量")
    _rows(lines, dossier.get("capital_economics"), "UNKNOWN（资本开支、ROIC、经济利润和自由现金流仍待核对）")
    lines.append("## 技术路线、竞争与核心瓶颈")
    _rows(lines, dossier.get("competition"), "UNKNOWN（份额、认证、良率和替代关系仍待核对）")
    lines.append("## 代表公司业绩验证")
    _rows(lines, dossier.get("earnings_tracking"), "UNKNOWN（尚未用订单、财报和公司指引验证产业逻辑）")
    lines.append("## 市场预期与叙事")
    _rows(lines, dossier.get("expectations"), "UNKNOWN（事实、卖方预测和市场叙事尚未分开核对）")
    lines.append("## 市场隐含预期与兑现门槛")
    _rows(lines, dossier.get("implied_expectations"), "UNKNOWN（尚未说明当前定价要求兑现怎样的增长、份额或利润率）")
    lines.append("## 条件化情景")
    _rows(lines, dossier.get("scenarios"), "UNKNOWN（尚未建立基准、上行和下行情景及其触发条件）")
    lines.append("## 活跃事件主题")
    events = dossier.get("active_events") or []
    if events:
        for item in events:
            if isinstance(item, dict):
                lines.append("- {0} · {1}：{2}".format(
                    item.get("name") or "事件", item.get("status") or "DEVELOPING",
                    item.get("impact") or "影响链待核对",
                ))
            else:
                lines.append("- {0}".format(item))
    else:
        lines.append("- 尚未关联事件档案。后续 Rubin、地缘冲突、监管变化等会以独立事件对象接入，而不是混入新闻流。")
    lines.append("## 行业跟踪仪表盘")
    lines.extend([
        "| 跟踪指标 | 最新值 | 方向 | 状态 |",
        "| --- | ---: | ---: | --- |",
    ])
    for row in dossier.get("monitoring") or []:
        lines.append("| {0} | {1} | {2} | {3} |".format(
            str(row.get("metric") or "指标").replace("|", "／"),
            row.get("latest") or "—", row.get("direction") or "—", row.get("status") or "待更新",
        ))
    lines.append("## 风险与失效条件")
    _rows(lines, dossier.get("risks"), "UNKNOWN（尚未找到足以证伪当前判断的具体证据）")
    lines.append("## 下一步监控")
    for row in dossier.get("monitoring") or []:
        lines.append("- {0}：下一轮补最新口径，并记录方向和是否改变核心判断。".format(row.get("metric") or "指标"))
    open_questions = dossier.get("open_questions") or []
    if open_questions:
        lines.append("## 当前证据缺口")
        for item in open_questions:
            lines.append("- {0}".format(item))
    lines.extend([
        "## 来源",
        "| 编号 | 来源 | 日期 | 类型 |",
        "| ---: | --- | --- | --- |",
    ])
    for row in dossier.get("sources") or []:
        title = row.get("title") or "来源"
        url = row.get("url") or ""
        linked = "[{0}]({1})".format(title, url) if url.startswith(("http://", "https://")) else title
        lines.append("| [{0}] | {1} | {2} | {3} |".format(
            row.get("number") or "", linked.replace("|", "／"),
            row.get("published_at") or "网页未标注发布日期",
            row.get("source_label") or row.get("source_type") or "补充资料",
        ))
    refs = []
    for key in (
        "industry_boundary", "reference_class", "structural_change", "causal_model", "technology_route",
        "policy_supply_chain", "value_migration", "value_chain", "economics",
        "capital_economics", "competition", "earnings_tracking", "expectations",
        "implied_expectations", "scenarios", "risks", "changes",
    ):
        for row in dossier.get(key) or []:
            if isinstance(row, dict) and row.get("claim_id") and row["claim_id"] not in refs:
                refs.append(row["claim_id"])
    source_refs = [row.get("id") for row in dossier.get("sources") or [] if row.get("id")]
    rendered = "\n".join(lines)
    rendered = re.sub(r"\[C\d+\]", "", rendered)
    rendered = re.sub(r"\bC\d+\s*[:：]\s*", "", rendered)
    rendered = rendered.replace("UNKNOWN（", "待核对（")
    rendered = re.sub(r"\bUNKNOWN\b", "待核对", rendered)
    return rendered, refs, source_refs


def render_theme(dossier: dict, notice: str = ""):
    """Render a long-running theme as a map of subevents and mechanisms."""
    lines = []
    if notice:
        lines.append(notice)
    completion = dossier.get("research_completion") or {}
    if completion:
        lines.append("研究覆盖：演化主题跟踪 · {0} · 已完成 {1}/{2} 项必需检查".format(
            completion.get("status") or "PARTIAL", completion.get("passed_count") or 0,
            completion.get("checked_count") or 0,
        ))
    playbook = dossier.get("playbook") or {}
    lines.extend([
        "# 主题跟踪档案",
        "定义、起源、子事件时间线、当前催化和产业影响分别保存 · 持续更新",
        "研究对象：{0}".format(dossier.get("name") or "研究主题"),
        "主题阶段：{0}".format(dossier.get("state") or "UNVERIFIED"),
    ])
    if playbook:
        lines.append("研究分支：{0}".format("、".join(playbook.get("tracks") or []) or "待核对"))
        lines.append("关键主体：{0}".format("、".join(playbook.get("actors") or []) or "待核对"))
    lines.extend([
        "## 一句话判断",
        dossier.get("one_line_view") or "主题边界和近期催化仍待一手来源核对。",
    ])
    _analyst_summary(lines, dossier)
    lines.append("## 本轮变化")
    _rows(lines, dossier.get("changes"), "本轮没有抽取到足以改变主题判断的新事实。")
    diagnostics = dossier.get("gap_diagnostics") or []
    sections = [
        ("定义与边界：它是什么、不是什么", "definition_scope", "DEFINITION_SCOPE", "尚未形成可核对定义"),
        ("起源与历史基线", "origin_baseline", "ORIGIN_BASELINE", "尚未建立主题升温前的基线"),
        ("演化时间线", "timeline", "TIMELINE", "尚未把独立子事件按时间串联"),
        ("为什么现在升温", "current_catalysts", "CURRENT_CATALYSTS", "尚未确认近期直接催化"),
        ("关键主体与行动", "actor_map", "ACTOR_ACTIONS", "尚未核对关键主体的真实行动和立场"),
        ("技术与政策分支", "technical_policy_tracks", "TECHNICAL_POLICY_TRACKS", "尚未拆开风险、防护、评测与治理分支"),
        ("逻辑与影响传导链", "causal_chain", "CAUSAL_CHAIN", "尚未验证主题到产业需求之间的中间变量"),
        ("经济变量", "economic_variables", "ECONOMIC_VARIABLES", "尚未量化安全投入、合规成本或其他经济变量"),
    ]
    for title, key, evidence_key, fallback in sections:
        lines.append("## " + title)
        _rows(lines, dossier.get(key), _diagnostic_fallback(diagnostics, evidence_key, fallback))
    impact = dossier.get("impact_map") or {}
    lines.append("## 产业与板块影响（不等于个股推荐）")
    lines.append("### 可能直接/间接受益")
    _rows(lines, impact.get("positive"), "UNKNOWN（尚未找到带成立条件的正向影响证据）")
    lines.append("### 可能承压")
    _rows(lines, impact.get("negative"), "UNKNOWN（尚未找到带成立条件的负向影响证据）")
    lines.append("### 方向取决于条件")
    _rows(lines, impact.get("conditional"), "UNKNOWN（尚未完成影响条件核对）")
    tail_sections = [
        ("市场叙事与事实差", "market_narrative", "MARKET_NARRATIVE", "尚未区分市场正在交易的叙事和已验证事实"),
        ("预期如何变化", "expectation_delta", "EXPECTATION_DELTA", "尚未记录旧预期、新预期和修订方向"),
        ("下一验证点", "milestones", "MILESTONES", "尚未明确日期、标准、评测或披露来源"),
        ("风险、反证与主题失效条件", "risks", "RISK_INVALIDATION", "尚未找到具体反证或失效条件"),
    ]
    for title, key, evidence_key, fallback in tail_sections:
        lines.append("## " + title)
        _rows(lines, dossier.get(key), _diagnostic_fallback(diagnostics, evidence_key, fallback))
    open_questions = dossier.get("open_questions") or []
    if diagnostics:
        lines.extend([
            "## 证据覆盖与缺口诊断",
            "| 待补模块 | 当前发生在哪一步 | 下一步 |",
            "| --- | --- | --- |",
        ])
        for row in diagnostics:
            lines.append("| {0} | {1} | {2} |".format(
                _table_cell(row.get("label") or row.get("key") or "待核对"),
                _table_cell(row.get("reason") or "尚未确认"),
                _table_cell(row.get("next_step") or "继续核对"),
            ))
    elif open_questions:
        lines.append("## 当前证据缺口")
        lines.extend("- {0}".format(item) for item in open_questions)
    lines.extend(["## 来源", "| 编号 | 来源 | 日期 | 类型 |", "| ---: | --- | --- | --- |"])
    for row in dossier.get("sources") or []:
        title = unescape(row.get("title") or "来源")
        url = row.get("url") or ""
        linked = "[{0}]({1})".format(title, url) if url.startswith(("http://", "https://")) else title
        lines.append("| [{0}] | {1} | {2} | {3} |".format(
            row.get("number") or "", linked.replace("|", "／"),
            row.get("published_at") or "网页未标注发布日期",
            row.get("source_label") or row.get("source_type") or "补充资料",
        ))
    refs = []
    for _, key, _, _ in sections + tail_sections:
        for row in dossier.get(key) or []:
            if isinstance(row, dict) and row.get("claim_id") and row["claim_id"] not in refs:
                refs.append(row["claim_id"])
    for rows in impact.values():
        for row in rows or []:
            if isinstance(row, dict) and row.get("claim_id") and row["claim_id"] not in refs:
                refs.append(row["claim_id"])
    source_refs = [row.get("id") for row in dossier.get("sources") or [] if row.get("id")]
    rendered = "\n".join(lines)
    rendered = re.sub(r"\[C\d+\]", "", rendered)
    rendered = re.sub(r"\bC\d+\s*[:：]\s*", "", rendered)
    rendered = rendered.replace("UNKNOWN（", "待核对（")
    rendered = re.sub(r"\bUNKNOWN\b", "待核对", rendered)
    return rendered, refs, source_refs


def _table_cell(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).replace("|", "／").strip()


def _expectation_timeline(lines: list, rows: list) -> None:
    if not rows:
        return
    labels = {
        "MANAGEMENT_GUIDANCE": "公司指引",
        "CONSENSUS_DATA": "一致预期",
        "SELL_SIDE_ESTIMATE": "卖方预测",
        "MARKET_NARRATIVE": "市场叙事",
    }
    grades = {
        "VENDOR_EXCERPT": "数据商资讯片段",
        "OPENED_REPORT": "已打开研报",
        "RESEARCH_NOTE": "本地研究笔记",
        "SECONDARY_SOURCE": "二手来源",
    }
    lines.extend([
        "### 预期修订时间线",
        "| 日期 | 机构/口径 | 类型 | 状态与内容 | 来源等级 |",
        "| --- | --- | --- | --- | --- |",
    ])
    for row in rows[:12]:
        state = "当前可见最新" if row.get("latest_for_institution") else "历史版本"
        details = [state]
        if row.get("period"):
            details.append("预测期 " + str(row["period"]))
        if row.get("rating"):
            details.append("评级 " + str(row["rating"]))
        if row.get("comparison_basis"):
            details.append(str(row["comparison_basis"]))
        details.append(_table_cell(row.get("statement") or ""))
        lines.append("| {0} | {1} | {2} | {3} · {4} | {5} |".format(
            row.get("date") or "待确认",
            row.get("institution") or "机构待确认",
            labels.get(row.get("kind") or "", row.get("kind") or "其他"),
            " · ".join(details[:-1]),
            details[-1],
            grades.get(row.get("source_grade") or "", row.get("source_grade") or "待确认"),
        ))


def _analyst_summary(lines: list[str], dossier: dict) -> None:
    view = dossier.get("analyst_view") or {}
    if not view:
        return
    lines.append("## AI 跨来源综合分析")
    model = view.get("model") or "研究模型"
    lines.append("研究模型：{0} · 事实仍由引用校验层约束".format(model))
    if view.get("executive_summary"):
        lines.append(view["executive_summary"])
    changes = view.get("key_changes") or []
    if changes:
        lines.append("### 本轮最重要的变化")
        lines.extend("- {0}".format(item) for item in changes)
    for row in view.get("sections") or []:
        lines.append("### " + (row.get("title") or row.get("key") or "分析模块"))
        label = "分析判断" if row.get("analysis_type") == "INFERENCE" else "事实综合"
        lines.append("{0}（{1} · 置信度 {2} · {3} 条已核对证据）".format(
            row.get("analysis") or "",
            label,
            row.get("confidence") or "MEDIUM",
            len(row.get("claim_ids") or []),
        ))
    if view.get("causal_chain"):
        lines.append("### 跨来源因果链")
        lines.extend("- {0}".format(item) for item in view["causal_chain"])
    if view.get("contradictions"):
        lines.append("### 来源分歧与反证")
        lines.extend("- {0}".format(item) for item in view["contradictions"])
    if view.get("next_questions"):
        lines.append("### 下一轮应继续核对")
        lines.extend("- {0}".format(item) for item in view["next_questions"])


def _diagnostic_fallback(diagnostics: list[dict], evidence_key: str, fallback: str) -> str:
    row = next((item for item in diagnostics if item.get("key") == evidence_key), None)
    reason = (row or {}).get("reason") or fallback
    return "UNKNOWN（{0}）".format(reason)


def render_event(dossier: dict, notice: str = ""):
    """Render an event as a stateful verification object, not a news summary."""
    if dossier.get("object_kind") == "EVOLVING_THEME":
        return render_theme(dossier, notice)
    lines = []
    if notice:
        lines.append(notice)
    completion = dossier.get("research_completion") or {}
    if completion:
        lines.append("研究覆盖：事件持续跟踪 · {0} · 已完成 {1}/{2} 项必需检查".format(
            completion.get("status") or "PARTIAL", completion.get("passed_count") or 0,
            completion.get("checked_count") or 0,
        ))
    lines.extend([
        "# 事件跟踪档案",
        "事件不是新闻标题 · 基线、状态、传导与兑现分别保存",
        "研究对象：{0}".format(dossier.get("name") or "事件主题"),
        "事件状态：{0}".format(dossier.get("state") or "UNVERIFIED"),
        "## 一句话判断",
        dossier.get("one_line_view") or "事件尚未获得足够原文确认。",
    ])
    _analyst_summary(lines, dossier)
    lines.append("## 本轮变化")
    _rows(lines, dossier.get("changes"), "本轮没有抽取到足以改变事件判断的新事实。")
    sections = [
        ("事件定义与一手来源", "event_definition", "事件主体、时间、适用范围尚未核对"),
        ("事件前基线", "baseline", "没有基线就无法判断真正增量"),
        ("当前阶段", "status_stage", "尚未确认是传闻、宣布、规则明确、实施还是兑现"),
        ("相对基线改变了什么", "what_changed", "尚未识别增量变量"),
        ("影响传导链（Transmission Map）", "causal_chain", "尚未验证中间传导变量"),
        ("数量、价格、成本与价值量", "economic_variables", "尚未量化经济变量"),
        ("受影响产业链节点", "affected_nodes", "尚未定位影响环节"),
        ("事件前后预期差", "expectation_delta", "尚未记录旧预期、新预期和分歧"),
        ("条件化情景", "scenarios", "尚未区分基准、上行和下行情景"),
        ("下一里程碑", "milestones", "尚未明确日期、动作和验证来源"),
        ("订单与业绩兑现", "earnings_link", "尚未验证订单、收入、利润或现金流"),
        ("风险与失效条件", "risks", "尚未找到具体反证或失效条件"),
    ]
    for title, key, fallback in sections:
        lines.append("## " + title)
        _rows(lines, dossier.get(key), "UNKNOWN（{0}）".format(fallback))
    open_questions = dossier.get("open_questions") or []
    if open_questions:
        lines.append("## 当前证据缺口")
        lines.extend("- {0}".format(item) for item in open_questions)
    lines.extend(["## 来源", "| 编号 | 来源 | 日期 | 类型 |", "| ---: | --- | --- | --- |"])
    for row in dossier.get("sources") or []:
        title = row.get("title") or "来源"
        url = row.get("url") or ""
        linked = "[{0}]({1})".format(title, url) if url.startswith(("http://", "https://")) else title
        lines.append("| [{0}] | {1} | {2} | {3} |".format(
            row.get("number") or "", linked.replace("|", "／"),
            row.get("published_at") or "网页未标注发布日期",
            row.get("source_label") or row.get("source_type") or "补充资料",
        ))
    refs = []
    for _, key, _ in sections:
        for row in dossier.get(key) or []:
            if isinstance(row, dict) and row.get("claim_id") and row["claim_id"] not in refs:
                refs.append(row["claim_id"])
    source_refs = [row.get("id") for row in dossier.get("sources") or [] if row.get("id")]
    rendered = "\n".join(lines)
    rendered = re.sub(r"\[C\d+\]", "", rendered)
    rendered = re.sub(r"\bC\d+\s*[:：]\s*", "", rendered)
    rendered = rendered.replace("UNKNOWN（", "待核对（")
    rendered = re.sub(r"\bUNKNOWN\b", "待核对", rendered)
    return rendered, refs, source_refs


def _section(lines: list, title: str, rows) -> None:
    lines.append("### " + title)
    _rows(lines, rows, "UNKNOWN（尚无已核对证据）")


def _rows(lines: list, rows, fallback: str) -> None:
    if not rows:
        lines.append("- " + fallback)
        return
    for row in rows:
        if isinstance(row, dict):
            suffix = " [{0}]".format(row.get("source_number")) if row.get("source_number") else ""
            labels = []
            if row.get("source_type") == "DATA_VENDOR_NEWS_EXCERPT":
                labels.append("资讯片段")
            claim_label = {
                "FACT": "事实陈述", "ESTIMATE": "预测", "INFERENCE": "推断", "OPINION": "观点",
            }.get(row.get("claim_type") or "")
            if claim_label:
                labels.append(claim_label)
            prefix = "【{0}】".format("·".join(labels)) if labels else ""
            lines.append("- {0}{1}{2}".format(prefix, row.get("text") or "", suffix))
        else:
            lines.append("- {0}".format(row))


def _financial_tables(lines: list, statements: dict) -> None:
    required_years = statements.get("required_years") or []
    required_data_years = [year for year in statements.get("data_years") or [] if year in required_years]
    lines.extend([
        "## 三年年报与最新季报",
        "- 覆盖：{0}（要求年报 {1}；已打开年报 {2}；已取得财务数据 {3}）".format(
            statements.get("coverage_status") or "INCOMPLETE",
            "、".join(str(year) for year in required_years) or "UNKNOWN",
            "、".join(str(year) for year in statements.get("found_years") or []) or "无",
            "、".join(str(year) for year in required_data_years) or "无",
        ),
        "- 口径：{0}".format(statements.get("coverage_note") or "尚未形成三年官方年报基线。"),
    ])
    periodic = statements.get("periodic_records") or []
    lines.append("### 最新季报/半年报（累计口径）")
    if not periodic:
        lines.append("- 待核对（尚未从官方目录打开年报之后的季报或半年报正文）")
    else:
        lines.extend([
            "| 报告期 | 营业收入 | 同比 | 毛利率 | 经营利润率 | 归母净利润 | 扣非归母 | 经营现金流 | 来源 |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
        ])
        for row in periodic[:4]:
            lines.append("| {0} | {1} | {2} | {3} | {4} | {5} | {6} | {7} | {8} |".format(
                row.get("period") or "—", _money(row.get("revenue")), _percent(row.get("revenue_yoy")),
                _percent(row.get("gross_margin")), _percent(row.get("operating_margin")),
                _money(row.get("net_profit_parent")), _money(row.get("adjusted_net_profit")),
                _money(row.get("operating_cash_flow")), _source_cell(row),
            ))
    records = statements.get("records") or []
    if not records:
        lines.append("- UNKNOWN（没有从已读官方年报中安全解析出可比财务表）")
    else:
        lines.extend([
            "### 最近三年年报：盈利与现金流",
            "| 年度 | 营业收入 | 同比 | 毛利率 | 经营利润率 | 归母净利润 | 扣非归母 | 经营现金流 | 来源 |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
        ])
        for row in records[:3]:
            lines.append("| {0} | {1} | {2} | {3} | {4} | {5} | {6} | {7} | {8} |".format(
                row.get("year") or "—", _money(row.get("revenue")), _percent(row.get("revenue_yoy")),
                _percent(row.get("gross_margin")), _percent(row.get("operating_margin")),
                _money(row.get("net_profit_parent")), _money(row.get("adjusted_net_profit")),
                _money(row.get("operating_cash_flow")), _source_cell(row),
            ))
        lines.extend([
            "### 资产负债与投入",
            "| 年度 | 资产负债率 | 有息负债 | 现金 | 流动比率 | 应收/收入 | 存货/收入 | 资本开支 | 自由现金流 |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ])
        for row in records[:3]:
            lines.append("| {0} | {1} | {2} | {3} | {4} | {5} | {6} | {7} | {8} |".format(
                row.get("year") or "—", _percent(row.get("debt_to_assets")),
                _money(row.get("interest_bearing_debt")), _money(row.get("cash")),
                _multiple(row.get("current_ratio")), _percent(row.get("receivable_days_proxy")),
                _percent(row.get("inventory_to_revenue")), _money(row.get("capex")),
                _money(row.get("free_cash_flow")),
            ))
    segments = statements.get("segments") or []
    lines.append("### 产品/业务结构")
    if not segments:
        lines.append("- UNKNOWN（未从已读年报中安全解析出分产品/分业务表；不能用总收入代替）")
    else:
        lines.extend([
            "| 年度 | 产品/业务 | 收入 | 收入占比 | 同比 | 毛利率 | 来源 |",
            "| --- | --- | ---: | ---: | ---: | ---: | --- |",
        ])
        for row in segments[:18]:
            source = "[{0}]".format(row.get("source_number")) if row.get("source_number") else "—"
            lines.append("| {0} | {1} | {2} | {3} | {4} | {5} | {6} |".format(
                row.get("year") or "—", row.get("segment") or "—",
                _money(row.get("revenue_yuan")), _percent(row.get("revenue_share")),
                _percent(row.get("revenue_yoy")), _percent(row.get("gross_margin")), source,
            ))


def _value(value) -> str:
    if isinstance(value, float):
        return str(round(value, 2))
    return "UNKNOWN" if value is None else str(value)


def _money(value) -> str:
    if value is None:
        return "—"
    return "{0:.2f} 亿".format(float(value) / 100000000)


def _percent(value) -> str:
    if value is None:
        return "—"
    return "{0:.1f}%".format(float(value) * 100)


def _multiple(value) -> str:
    if value is None:
        return "—"
    return "{0:.2f}x".format(float(value))


def _source_cell(row: dict) -> str:
    provenance = row.get("provenance") or {}
    numbers = []
    for metric in ("revenue", "net_profit_parent", "operating_cash_flow"):
        number = (provenance.get(metric) or {}).get("source_number")
        if number and number not in numbers:
            numbers.append(number)
    return " ".join("[{0}]".format(number) for number in numbers) or "—"


def _risk_value(value, name: str = "") -> str:
    if isinstance(value, float):
        if name == "资产负债率":
            return "{0:.1f}%".format(value * 100)
        if name in ("短期偿债", "利润现金含量"):
            return "{0:.2f}x".format(value)
        return "{0:.2f}".format(value)
    return str(value or "UNKNOWN")


def _all_items(dossier: dict):
    stack = [dossier]
    result = []
    while stack:
        value = stack.pop()
        if isinstance(value, dict):
            if value.get("text"):
                result.append(value)
            stack.extend(value.values())
        elif isinstance(value, list):
            stack.extend(value)
    return result


def render_why(claims):
    lines = [
        "研究档案 · 基于已读证据 · 持续更新",
        "这是已经记下的证据，没有重新搜索，也没有重新打开来源。",
        "核心证据",
    ]
    refs = []
    for row in claims[:4]:
        lines.append("[{0}] {1}".format(row["local_id"], row["text"]))
        refs.append(row["local_id"])
    lines.extend([
        "现在还不知道什么",
        "没有新的来源，未知项保持原样。",
        "最大风险",
        "把已有原文说成最新公告。",
    ])
    return "\n".join(lines), refs, _sources(claims[:4])


def render_compare(primary, other, claims, gaps, notice):
    left = (primary or {}).get("canonical_name") or "前一家"
    lines = ["研究档案 · 基于已读证据 · 持续更新"]
    if notice:
        lines.append(notice)
    lines.extend([
        "当前判断",
        "{0}和{1}放在同一会话里对照。只比业务暴露、商业阶段、收入暴露、增长驱动、毛利和证据强度。".format(left, other or "另一家"),
        "为什么这么看",
        "两边都只用已打开资料。商业阶段没有从产品存在提升到收入。",
        "核心证据",
    ])
    refs = []
    for row in claims[:6]:
        lines.append("[{0}] {1}".format(row["local_id"], row["text"]))
        refs.append(row["local_id"])
    lines.extend([
        "现在还不知道什么",
        "；".join(gaps) if gaps else "两边的客户和收入暴露都还有缺口。",
        "最大风险",
        "用叙事强弱代替证据强弱。",
    ])
    return "\n".join(lines), refs, _sources(claims[:6])


def unavailable(notice: str) -> str:
    if notice and "联网研究不可用" in notice:
        return "本轮联网研究不可用\n没有可用缓存，不能用记忆补事实。"
    return "本轮研究不可用\n没有已打开的来源，也不能靠模型记忆补最新事实。"


def clarify_text(entity) -> str:
    names = "、".join(row.get("name") or row.get("code") or "" for row in entity.get("candidates") or [])
    return "这个名字对上了多家公司：{0}。要研究哪一家？我不会猜。".format(names)


def _sources(claims):
    refs = []
    for row in claims:
        if row.get("source_id") and row["source_id"] not in refs:
            refs.append(row["source_id"])
    return refs
