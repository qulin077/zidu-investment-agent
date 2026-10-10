"""Long-lived industry research policy and dossier builder.

An industry dossier is not a large company report.  It keeps a stable value-
chain model and records what changed around it.  Event themes can later attach
to the same variables without rewriting the structural baseline.
"""
from __future__ import annotations

from datetime import date, timedelta
import re

from core.research import industry_playbooks


REQUIRED_EVIDENCE = (
    "INDUSTRY_BOUNDARY",
    "REFERENCE_CLASS",
    "VALUE_CHAIN",
    "STRUCTURAL_CHANGE",
    "CAUSAL_MODEL",
    "TECHNOLOGY_ROUTE",
    "POLICY_SUPPLY_CHAIN",
    "VALUE_MIGRATION",
    "ECONOMICS",
    "CAPITAL_ECONOMICS",
    "COMPETITION",
    "EARNINGS_TRACKING",
    "EXPECTATIONS",
    "IMPLIED_EXPECTATIONS",
    "SCENARIOS",
    "RISK",
)

_PATTERNS = {
    "INDUSTRY_BOUNDARY": ("行业", "产业", "市场规模", "应用领域", "产品定义", "产业链"),
    "REFERENCE_CLASS": ("历史", "基准率", "基准", "周期", "渗透率", "生命周期", "可比行业"),
    "STRUCTURAL_CHANGE": ("变化", "增长", "下降", "替代", "升级", "渗透率", "政策", "周期"),
    "CAUSAL_MODEL": ("导致", "驱动", "传导", "因此", "从而", "敏感性", "瓶颈"),
    "TECHNOLOGY_ROUTE": ("技术路线", "可插拔", "NPO", "CPO", "光引擎", "ELS", "FAU", "硅光", "EML", "3.2T"),
    "POLICY_SUPPLY_CHAIN": ("FCC", "限制", "禁令", "国产", "美国制造", "BOM", "产地", "供应链", "制裁", "合规"),
    "VALUE_MIGRATION": ("价值量", "受益", "受损", "利空", "利好", "份额转移", "利润池", "光芯片", "DSP", "连接器", "封装"),
    "VALUE_CHAIN": ("上游", "中游", "下游", "供应链", "产业链", "原材料", "设备", "终端"),
    "ECONOMICS": ("销量", "出货量", "价格", "ASP", "成本", "毛利率", "产能", "利用率", "资本开支"),
    "CAPITAL_ECONOMICS": ("ROIC", "投入资本回报", "资本回报", "经济利润", "现金回报", "资本密集", "自由现金流"),
    "COMPETITION": ("竞争格局", "市场份额", "市占率", "壁垒", "认证", "良率", "龙头"),
    "EARNINGS_TRACKING": ("营业收入", "净利润", "订单", "业绩", "财报", "同比", "环比"),
    "EXPECTATIONS": (
        "一致预期", "盈利预测", "市场预期", "出货预期", "公司指引", "卖方",
        "预测", "预计", "上调", "下调", "估值", "叙事",
    ),
    "IMPLIED_EXPECTATIONS": ("隐含预期", "估值隐含", "市场定价", "预期差", "需要达到", "兑现门槛"),
    "SCENARIOS": ("情景", "基准", "乐观", "悲观", "概率", "敏感性", "如果"),
    "RISK": ("风险", "不确定", "下滑", "过剩", "降价", "延迟", "制裁", "替代", "证伪"),
}


def subject_from_question(question: str, fallback: str = "") -> str:
    """Extract a research object without pretending it is a listed company."""
    value = (question or "").strip()
    subjects = industry_playbooks.subjects_from_question(value)
    if subjects:
        return " / ".join(subjects[:3])
    match = re.search(r"(?:研究|分析|跟踪|看看|了解)(?:一下)?([A-Za-z0-9\u4e00-\u9fff]{2,18})(?:行业|产业链|板块|赛道)", value)
    if match:
        return match.group(1).strip("的关于 ")
    return (fallback or "行业主题").strip()


def resolve_subject(question: str, previous: dict | None = None) -> dict:
    current = dict(previous or {})
    name = subject_from_question(question, current.get("canonical_name") or "")
    playbook = industry_playbooks.describe(name)
    return {
        "status": "RESOLVED" if name and name != "行业主题" else "UNVERIFIED",
        "canonical_name": name,
        "ticker": "",
        "exchange": "",
        "path": current.get("path") or "",
        "universe_status": "NOT_APPLICABLE",
        "aliases": [name] if name else [],
        "chains": [],
        "verified_source": "",
        "playbook_id": playbook.get("id") or "generic",
        "playbook_label": playbook.get("label") or "通用行业",
        "focus_segment": playbook.get("focus_segment") or {},
    }


def search_action(query: str, reason: str, success_condition: str) -> dict:
    return {
        "action": "SEARCH", "query": (query or "").strip(),
        "reason": (reason or "").strip(),
        "success_condition": (success_condition or "").strip(),
    }


def finish_action(reason: str) -> dict:
    return {"action": "FINISH", "query": "", "reason": reason or "", "success_condition": ""}


def valid_query(query: str, name: str, ticker: str = "") -> bool:
    value = re.sub(r"\s+", " ", (query or "").strip())
    if len(value) < 4 or len(value) > 140 or "\n" in (query or ""):
        return False
    topics = [part.strip() for part in (name or "").split("/") if part.strip()]
    if topics and not any(topic in value for topic in topics):
        return False
    return not any(token in value.lower() for token in ("忽略以上", "system prompt", "developer message", "建议买入", "目标价"))


def initial_execution(name: str, question: str, kind: str, ticker: str = "", since: str = "") -> dict:
    playbook = industry_playbooks.describe(name)
    if kind == "followup":
        query = f"{name} 最新 产业链 景气 订单 业绩 变化 {str(since)[:10]}".strip()
        reason = "先检查上次行业档案以后，供需、技术、订单和业绩是否出现新变化。"
    else:
        configured = industry_playbooks.gap_queries(name, "INDUSTRY_BOUNDARY")
        query = configured[0] if configured else f"{name} 行业 产业链 上游 下游 商业模式 市场规模".strip()
        reason = "先定义行业边界和产业链，避免把主题概念直接当成研究结论。"
    hypotheses = [
        ("行业边界与产品范围可以被明确。", "INDUSTRY_BOUNDARY"),
        ("行业的历史基准率、生命周期和合适参考类可以被明确。", "REFERENCE_CLASS"),
        ("当前结构变化可以拆为需求、供给、技术或政策变量。", "STRUCTURAL_CHANGE"),
        ("核心叙事可以转换成可验证的因果变量。", "CAUSAL_MODEL"),
        ("关键产品或技术路线的阶段、替代边界和量产节点可以被区分。", "TECHNOLOGY_ROUTE"),
        ("政策和供应链本地化要求可以拆到具体环节、时间和口径。", "POLICY_SUPPLY_CHAIN"),
        ("变化对各产业链节点的价值量、利润池和受益受损方向可以被解释。", "VALUE_MIGRATION"),
        ("产业链节点和价值传导可以被画清。", "VALUE_CHAIN"),
        ("量、价、成本、产能或利润率至少一项可以被持续跟踪。", "ECONOMICS"),
        ("增长所需资本、资本回报和现金回报可以被核对。", "CAPITAL_ECONOMICS"),
        ("竞争和瓶颈可以由份额、认证、良率或客户关系解释。", "COMPETITION"),
        ("代表公司业绩能够用于验证产业判断。", "EARNINGS_TRACKING"),
        ("事实、卖方预期和市场叙事能够分开。", "EXPECTATIONS"),
        ("当前定价需要兑现的经营门槛和预期差可以被描述。", "IMPLIED_EXPECTATIONS"),
        ("基准、上行和下行情景及触发条件可以被区分。", "SCENARIOS"),
        ("至少一个会证伪当前判断的风险可以被明确。", "RISK"),
    ]
    return {
        "mode": "INDUSTRY_EVIDENCE_CONVERGENCE",
        "hypotheses": [
            {"id": f"IH{index}", "text": text, "evidence": evidence, "status": "OPEN"}
            for index, (text, evidence) in enumerate(hypotheses, start=1)
        ],
        "required_evidence": list(REQUIRED_EVIDENCE),
        "next_action": search_action(query, reason, "找到行业定义、产业链或协会/公司一手材料。"),
        "completed_actions": [],
        "coverage": {key: False for key in REQUIRED_EVIDENCE},
        "stop_conditions": ["关键证据已覆盖", "没有新增正文且没有安全、不重复的新查询"],
        "stop_reason": "",
        "ticker": "",
        "playbook": {
            "id": playbook.get("id") or "generic",
            "label": playbook.get("label") or "通用行业",
            "domain": playbook.get("domain") or "未分类行业",
            "focus_segment": playbook.get("focus_segment") or {},
        },
    }


def evidence_coverage(claims: list) -> dict:
    blob = "\n".join(f"{row.get('text') or ''} {row.get('evidence_text') or ''}" for row in claims or [])
    return {key: any(token in blob for token in tokens) for key, tokens in _PATTERNS.items()}


def missing_evidence(coverage: dict, required=None) -> list:
    return [key for key in (required or REQUIRED_EVIDENCE) if not coverage.get(key)]


def update_execution(execution: dict, claims: list) -> dict:
    coverage = evidence_coverage(claims)
    execution["coverage"] = coverage
    for hypothesis in execution.get("hypotheses") or []:
        hypothesis["status"] = "SUPPORTED" if coverage.get(hypothesis.get("evidence") or "") else "OPEN"
    return coverage


def deterministic_next(name: str, coverage: dict, used_queries: list, question: str = "") -> dict:
    candidates = []
    reasons = {
        "INDUSTRY_BOUNDARY": ("按行业 Playbook 补齐边界和价值链。", "找到行业范围、产品分类或上下游节点。"),
        "REFERENCE_CLASS": ("用历史基准率约束行业叙事。", "找到历史周期、渗透率、增长或利润率的合理参考类。"),
        "CAUSAL_MODEL": ("把行业故事转换成可验证变量。", "明确输入变量、中间传导、输出指标和成立条件。"),
        "TECHNOLOGY_ROUTE": ("核对该行业关键路线的商业化阶段。", "区分概念、验证、量产与规模收入。"),
        "POLICY_SUPPLY_CHAIN": ("核对政策和供应链约束的状态与范围。", "找到政策原文或明确范围、时间和受影响环节。"),
        "VALUE_MIGRATION": ("把变化翻译成产业链价值量和利润池迁移。", "明确受影响节点、方向和成立条件。"),
        "ECONOMICS": ("核对行业 Playbook 定义的量价和经营指标。", "找到带时间口径的量、价、成本、产能或利用率数据。"),
        "CAPITAL_ECONOMICS": ("核对增长质量和利润池是否创造资本回报。", "找到资本开支、投入资本回报、自由现金流或经济利润证据。"),
        "EARNINGS_TRACKING": ("用行业适配的财务指标验证产业逻辑。", "找到代表公司收入、利润、订单、现金流或行业特有指标。"),
        "EXPECTATIONS": ("记录预测值、修订方向和市场分歧。", "找到预测方、期间、数值及上调/下调参照。"),
        "IMPLIED_EXPECTATIONS": ("区分好行业和好预期差。", "明确当前定价需要兑现的增长、份额或利润率门槛。"),
        "SCENARIOS": ("用条件化情景处理不确定性。", "列出基准、上行、下行情景的触发变量和验证点。"),
        "RISK": ("主动寻找会削弱当前判断的证据。", "找到具体反证、风险或失效条件。"),
    }
    for category in (
        "INDUSTRY_BOUNDARY", "REFERENCE_CLASS", "CAUSAL_MODEL", "TECHNOLOGY_ROUTE",
        "POLICY_SUPPLY_CHAIN", "VALUE_MIGRATION", "ECONOMICS", "CAPITAL_ECONOMICS",
        "EARNINGS_TRACKING", "EXPECTATIONS", "IMPLIED_EXPECTATIONS", "SCENARIOS", "RISK",
    ):
        if coverage.get(category):
            continue
        reason, success = reasons[category]
        candidates.extend((query, reason, success) for query in industry_playbooks.gap_queries(name, category))
    if not coverage.get("INDUSTRY_BOUNDARY") or not coverage.get("VALUE_CHAIN"):
        candidates.extend((
            (f"{name} 行业定义 产业链 上游 中游 下游", "补齐行业边界和产业链节点。", "找到行业协会、官方或龙头公司对产业链的说明。"),
            (f"{name} 技术路线 产品分类 应用领域", "核对产品和技术路线，避免主题边界漂移。", "找到产品分类、技术路线或应用范围。"),
        ))
    if not coverage.get("REFERENCE_CLASS"):
        candidates.append((f"{name} 历史周期 渗透率 增长 利润率 基准", "用参考类和基准率约束外推。", "找到历史区间、生命周期或可比行业基准。"))
    if not coverage.get("CAUSAL_MODEL"):
        candidates.append((f"{name} 核心驱动 传导 敏感性 瓶颈 验证指标", "把叙事映射到可验证变量。", "明确驱动、中间变量、输出和失效条件。"))
    if not coverage.get("STRUCTURAL_CHANGE") or not coverage.get("ECONOMICS"):
        candidates.extend((
            (f"{name} 供需 价格 库存 产能 利用率 最新", "核对景气和经济变量。", "找到带时间口径的量、价、库存或产能数据。"),
            (f"{name} 订单 出货 ASP 成本 毛利率 最新", "核对变化如何传到收入和利润。", "找到订单、出货、价格、成本或利润率证据。"),
        ))
    if not coverage.get("TECHNOLOGY_ROUTE"):
        candidates.append((f"{name} 技术路线 替代 量产 客户验证", "核对技术路线和商业化阶段。", "找到带时间的验证或量产节点。"))
    if not coverage.get("POLICY_SUPPLY_CHAIN"):
        candidates.append((f"{name} 政策 限制 产地 本地化 供应链 最新", "核对政策与供应链变化。", "找到明确范围、时间和受影响环节。"))
    if not coverage.get("VALUE_MIGRATION"):
        candidates.append((f"{name} 产业链 价值量 利润池 受益 受损", "核对利润池和价值量迁移。", "明确受影响节点、方向和条件。"))
    if not coverage.get("COMPETITION"):
        candidates.append((f"{name} 竞争格局 市场份额 壁垒 良率 认证", "核对竞争、瓶颈和替代关系。", "找到份额、认证、良率或供给瓶颈证据。"))
    if not coverage.get("EARNINGS_TRACKING"):
        candidates.append((f"{name} 龙头 公司 财报 业绩 订单 指引", "用代表公司业绩验证产业逻辑。", "找到代表公司收入、利润、订单或指引。"))
    if not coverage.get("EXPECTATIONS"):
        candidates.append((f"{name} 券商 预测 市场预期 争议 估值", "区分事实、卖方预测和市场叙事。", "找到带来源和期间的预测或明确争议。"))
    if not coverage.get("CAPITAL_ECONOMICS"):
        candidates.append((f"{name} 资本开支 ROIC 自由现金流 经济利润 资本回报", "检查增长是否创造资本回报。", "找到行业或代表公司的资本回报与现金回报证据。"))
    if not coverage.get("IMPLIED_EXPECTATIONS"):
        candidates.append((f"{name} 估值 隐含预期 增长门槛 利润率 预期差", "检查市场已经计入什么。", "找到估值、隐含增长或兑现门槛证据。"))
    if not coverage.get("SCENARIOS"):
        candidates.append((f"{name} 基准情景 上行情景 下行情景 敏感性 触发条件", "把不确定性写成条件化情景。", "找到关键变量的合理区间或情景条件。"))
    if not coverage.get("RISK"):
        candidates.append((f"{name} 风险 过剩 降价 延迟 替代 证伪", "主动寻找会削弱产业判断的证据。", "找到具体反证、风险或失效条件。"))
    used = {re.sub(r"\s+", " ", value).strip() for value in used_queries}
    for query, reason, success in candidates:
        if re.sub(r"\s+", " ", query).strip() not in used:
            return search_action(query, reason, success)
    return finish_action("行业证据仍有缺口；已用尽当前安全且不重复的查询，缺项保留为待核对。")


def vendor_queries(name: str, question: str = "") -> list[str]:
    """Small semantic queries work better than one overloaded vendor query.

    The public search planner can still generate broader follow-up queries.  This
    lane deliberately separates expectations, technology and policy because
    iFinD semantic search loses recall when all three are packed into one query.
    """
    subject = (name or "行业").split("/")[0].strip()
    configured = industry_playbooks.vendor_queries(subject)
    if configured:
        return configured
    return [
        f"{subject} 出货 价格 研报 预测 上调 下调",
        f"{subject} 技术路线 政策 供应链 价值量 变化",
    ]


def vendor_window_start(as_of: str = "", lookback_days: int = 550) -> str:
    """Return a rolling history window for expectation and logic revisions.

    ``last_live_checked_at`` is intentionally not used here.  A change study
    needs the old forecast as well as the new one, and a same-day last-check
    watermark would otherwise hide the history needed to identify a revision.
    Existing source hashes still prevent duplicate evidence from being saved.
    """
    try:
        anchor = date.fromisoformat((as_of or "")[:10]) if as_of else date.today()
    except ValueError:
        anchor = date.today()
    return (anchor - timedelta(days=max(int(lookback_days), 30))).isoformat()


def analysis_context(name: str) -> str:
    return industry_playbooks.analysis_context(name)


def _items(claims: list, category: str, limit: int = 6) -> list:
    tokens = _PATTERNS[category]
    result = []
    for row in claims or []:
        body = f"{row.get('text') or ''} {row.get('evidence_text') or ''}"
        if not any(token in body for token in tokens):
            continue
        result.append({
            "text": row.get("text") or row.get("evidence_text") or "",
            "claim_id": row.get("local_id") or "",
            "source_id": row.get("source_id") or "",
            "claim_type": row.get("claim_type") or "",
            "source_type": row.get("source_type") or "",
            "estimator": row.get("estimator") or "",
            "period": row.get("period") or "",
            "comparison_basis": row.get("comparison_basis") or "",
        })
        if len(result) >= limit:
            break
    return result


def monitoring_metrics(name: str) -> list:
    result = industry_playbooks.monitoring_metrics(name)
    if not result:
        result.extend(("需求/出货或订单", "价格与库存", "产能、利用率和资本开支", "代表公司收入、利润率与指引"))
    return list(dict.fromkeys(result))


def build_dossier(name: str, claims: list, sources: list, delta: dict, execution: dict, previous: dict | None = None) -> dict:
    playbook = industry_playbooks.describe(name)
    coverage = evidence_coverage(claims)
    source_numbers = {row.get("local_id"): index for index, row in enumerate(sources or [], start=1)}
    source_rows = [{
        "number": index, "id": row.get("local_id") or "", "title": row.get("title") or "来源",
        "url": row.get("url") or "", "published_at": row.get("published_at") or row.get("available_at") or "",
        "source_type": row.get("source_type") or "", "source_label": row.get("source_label") or "",
    } for index, row in enumerate(sources or [], start=1)]
    sections = {key.lower(): _items(claims, key) for key in REQUIRED_EVIDENCE}
    for rows in sections.values():
        for row in rows:
            row["source_number"] = source_numbers.get(row.get("source_id"))
    added = {
        row.get("id") if isinstance(row, dict) else row
        for row in ((delta or {}).get("added_claims") or [])
    }
    changes = [row for row in claims or [] if row.get("local_id") in added]
    return {
        "name": name,
        "playbook": {
            "id": playbook.get("id") or "generic",
            "label": playbook.get("label") or "通用行业",
            "domain": playbook.get("domain") or "未分类行业",
            "focus_segment": playbook.get("focus_segment") or {},
        },
        "one_line_view": (
            (sections["structural_change"][0]["text"] if sections["structural_change"] else "")
            or (sections["industry_boundary"][0]["text"] if sections["industry_boundary"] else "")
            or "尚未形成有证据支持的行业判断。"
        ),
        "industry_boundary": sections["industry_boundary"],
        "reference_class": sections["reference_class"],
        "structural_change": sections["structural_change"],
        "causal_model": sections["causal_model"],
        "technology_route": sections["technology_route"],
        "policy_supply_chain": sections["policy_supply_chain"],
        "value_migration": sections["value_migration"],
        "value_chain": sections["value_chain"],
        "economics": sections["economics"],
        "capital_economics": sections["capital_economics"],
        "competition": sections["competition"],
        "earnings_tracking": sections["earnings_tracking"],
        "expectations": sections["expectations"],
        "implied_expectations": sections["implied_expectations"],
        "scenarios": sections["scenarios"],
        "risks": sections["risk"],
        "changes": [{"text": row.get("text") or row.get("evidence_text") or "", "claim_id": row.get("local_id") or ""} for row in changes[:8]],
        "monitoring": [{"metric": metric, "status": "待接入/待更新", "latest": "—", "direction": "—"} for metric in monitoring_metrics(name)],
        "active_events": list((previous or {}).get("active_events") or []),
        "coverage": coverage,
        "open_questions": [key for key, ok in coverage.items() if not ok],
        "sources": source_rows,
        "execution": execution,
    }


def completion(dossier: dict) -> dict:
    coverage = dossier.get("coverage") or {}
    checks = [{"key": key, "passed": bool(coverage.get(key))} for key in REQUIRED_EVIDENCE]
    passed = sum(1 for row in checks if row["passed"])
    return {
        "mode": "INDUSTRY_TRACKING",
        "status": "COMPLETE" if passed == len(checks) else "PARTIAL",
        "passed": passed == len(checks),
        "passed_count": passed,
        "checked_count": len(checks),
        "missing_required": [row["key"] for row in checks if not row["passed"]],
        "checks": checks,
    }
