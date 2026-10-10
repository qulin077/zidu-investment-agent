"""Evidence-convergent research policy used by the workspace executor.

The planner is intentionally small: one search action is executed at a time,
then the observed claims are used to choose the next action or stop.  It does
not expose arbitrary tools and it never performs writes.
"""
from __future__ import annotations

import re

REQUIRED_EVIDENCE = ("BUSINESS_MODEL", "FINANCIAL_TREND", "KEY_DRIVER", "EXPECTATIONS", "RISK")

_COVERAGE_PATTERNS = {
    "BUSINESS_MODEL": ("主营", "主要业务", "产品", "服务", "销售", "生产", "客户"),
    "FINANCIAL_TREND": ("营业收入", "净利润", "经营活动产生的现金流量", "经营现金流", "毛利率"),
    "EXPECTATIONS": ("公司指引", "管理层预计", "一致预期", "盈利预测", "分析师预计", "未来展望"),
    "RISK": ("风险", "下降", "下滑", "减少", "亏损", "不利", "承压", "波动", "减值", "依赖"),
}


def initial_execution(name: str, question: str, kind: str, ticker: str = "", since: str = "") -> dict:
    """Create an executable plan without asserting any company facts."""
    focus = _focus(question)
    if focus:
        query = f"{name} {focus} 公告 投资者关系"
        reason = "先核对用户确认的研究重点，再决定是否补公司基线。"
    elif kind == "followup":
        year_hint = (since or "")[:4]
        query = f"{name} {ticker} 最新公告 财报 业绩说明会 {year_hint}".strip()
        reason = "先检查上次研究以后有没有新披露，而不是直接复述旧结论。"
    elif kind == "comparison":
        query = f"{name} 最新年度报告 主营业务 营业收入 净利润"
        reason = "先为对比对象建立同口径的业务与财务基线。"
    else:
        query = f"{name} 最新年度报告 主营业务 营业收入 净利润"
        reason = "先用一手披露建立公司业务与财务基线。"
    return {
        "mode": "EVIDENCE_CONVERGENCE",
        "hypotheses": [
            {"id": "H1", "text": f"{name}的核心业务与收入来源可以由公司披露确认。", "evidence": "BUSINESS_MODEL", "status": "OPEN"},
            {"id": "H2", "text": "最近一期收入、利润或现金流方向可以由财报确认。", "evidence": "FINANCIAL_TREND", "status": "OPEN"},
            {"id": "H3", "text": "经营变化背后的量、价、成本或订单驱动可以被解释。", "evidence": "KEY_DRIVER", "status": "OPEN"},
            {"id": "H4", "text": "公司指引、一致预期或卖方预测至少有一项可以核对；否则必须明确未知。", "evidence": "EXPECTATIONS", "status": "OPEN"},
            {"id": "H5", "text": "至少一个会削弱当前判断的风险可以被明确。", "evidence": "RISK", "status": "OPEN"},
        ],
        "required_evidence": list(REQUIRED_EVIDENCE),
        "next_action": search_action(query, reason, "找到直接描述公司业务或财务数据的一手正文。"),
        "completed_actions": [],
        "coverage": {key: False for key in REQUIRED_EVIDENCE},
        "stop_conditions": ["关键证据已覆盖", "本轮没有新增正文或事实且下一步已无新查询", "没有安全且不重复的下一步"],
        "stop_reason": "",
        "ticker": ticker or "",
    }


def search_action(query: str, reason: str, success_condition: str) -> dict:
    return {
        "action": "SEARCH",
        "query": (query or "").strip(),
        "reason": (reason or "").strip(),
        "success_condition": (success_condition or "").strip(),
    }


def finish_action(reason: str) -> dict:
    return {"action": "FINISH", "query": "", "reason": reason or "", "success_condition": ""}


def valid_query(query: str, name: str, ticker: str = "") -> bool:
    value = re.sub(r"\s+", " ", (query or "").strip())
    if len(value) < 4 or len(value) > 120 or "\n" in (query or ""):
        return False
    if not ((name and name in value) or (ticker and ticker in value)):
        return False
    return not any(token in value.lower() for token in ("忽略以上", "system prompt", "developer message", "建议买入", "目标价"))


def evidence_coverage(claims: list) -> dict:
    texts = [
        f"{row.get('text') or ''} {row.get('evidence_text') or ''}"
        for row in (claims or [])
    ]
    blob = "\n".join(texts)
    # A margin number is an observation, not an explanation.  A driver only
    # counts when the source connects an operating variable to a change.
    driver_objects = ("价格", "销量", "成本", "原材料", "产能", "利用率", "订单", "需求", "客户")
    causal_words = ("原因", "导致", "由于", "主要受", "驱动", "带动", "影响", "贡献")
    driver = "业绩变动原因" in blob or any(
        any(item in value for item in driver_objects) and any(link in value for link in causal_words)
        for value in texts
    )
    return {
        "BUSINESS_MODEL": any(token in blob for token in _COVERAGE_PATTERNS["BUSINESS_MODEL"]),
        "FINANCIAL_TREND": any(token in blob for token in _COVERAGE_PATTERNS["FINANCIAL_TREND"]),
        "KEY_DRIVER": driver,
        "EXPECTATIONS": any(token in blob for token in _COVERAGE_PATTERNS["EXPECTATIONS"]),
        "RISK": any(token in blob for token in _COVERAGE_PATTERNS["RISK"]),
    }


def missing_evidence(coverage: dict, required=None) -> list:
    return [key for key in (required or REQUIRED_EVIDENCE) if not coverage.get(key)]


def deterministic_next(name: str, coverage: dict, used_queries: list, question: str = "") -> dict:
    """Pick the narrowest useful query; return FINISH if none is novel."""
    focus = _focus(question)
    candidates = []
    if focus and not any(focus in query for query in used_queries):
        candidates.append((f"{name} {focus} 公告 投资者关系", "核对用户点名的具体问题。", "找到该主题的直接披露或明确未披露。"))
    if not coverage.get("BUSINESS_MODEL"):
        candidates.extend((
            (f"{name} 年度报告 主营业务 产品", "补齐公司到底做什么。", "找到主营业务或产品的公司原文。"),
            (f"{name} 投资者关系 产品 客户 收入结构", "从管理层交流补齐产品、客户和收入结构。", "找到产品、客户或收入来源的直接披露。"),
        ))
    if not coverage.get("FINANCIAL_TREND"):
        candidates.extend((
            (f"{name} 最新财报 营业收入 净利润 经营现金流", "补齐最近财务方向。", "找到至少一项带期间的财务数据。"),
            (f"{name} 年报 季报 毛利率 资产负债率 应收 存货", "交叉核对盈利质量和资产负债风险。", "找到带期间的利润率或资产负债数据。"),
        ))
    if not coverage.get("KEY_DRIVER"):
        candidates.extend((
            (f"{name} 业绩变动原因 毛利率 价格 销量 成本", "解释数字变化背后的经营驱动。", "找到管理层对量、价、成本或订单的解释。"),
            (f"{name} 投资者关系活动记录 订单 产能 利用率 原材料", "从管理层交流核对经营变量。", "找到订单、产能、价格或成本变化的直接解释。"),
        ))
    if not coverage.get("EXPECTATIONS"):
        candidates.extend((
            (f"{name} 业绩说明会 公司指引 一致预期 盈利预测", "把公司指引、机构预期和市场叙事分开核对。", "找到至少一种带期间的预期数据，或确认公开材料未披露。"),
            (f"{name} 券商研报 盈利预测 EPS 营收 净利润", "补找可核对的卖方预测及其期间。", "找到预测机构、期间和核心假设。"),
            (f"{name} 市场预期 预期差 估值 争议", "补齐市场叙事与争议，不把观点当事实。", "找到明确署名的市场观点或确认没有可靠公开材料。"),
        ))
    if not coverage.get("RISK"):
        candidates.extend((
            (f"{name} 年报 主要风险 经营风险", "主动寻找会削弱判断的证据。", "找到至少一个公司披露的具体风险。"),
            (f"{name} 监管问询 减值 诉讼 业绩下修", "从反方材料核对可能的失效条件。", "找到监管、减值、诉讼或业绩下修证据。"),
        ))
    used = {re.sub(r"\s+", " ", query).strip() for query in used_queries}
    for query, reason, success in candidates:
        if re.sub(r"\s+", " ", query).strip() not in used:
            return search_action(query, reason, success)
    return finish_action("关键缺口仍存在；已用尽当前可生成的安全且不重复查询，公开来源不足。")


def update_execution(execution: dict, claims: list) -> dict:
    coverage = evidence_coverage(claims)
    execution["coverage"] = coverage
    for hypothesis in execution.get("hypotheses") or []:
        hypothesis["status"] = "SUPPORTED" if coverage.get(hypothesis.get("evidence") or "") else "OPEN"
    return coverage


def _focus(question: str) -> str:
    value = (question or "").strip()
    # The intake answer is free-form.  Pull only research-bearing terms into
    # the query instead of sending conversational boilerplate to search.
    terms = (
        "AI PCB", "覆铜板", "PCB", "数据中心", "液冷", "冷链", "出口", "订单",
        "客户", "产品", "产能", "利用率", "销量", "价格", "涨价", "降价",
        "原材料", "收入", "净利润", "利润弹性", "利润", "毛利率", "现金流",
        "资本开支", "基本盘", "商业模式", "竞争壁垒", "核心壁垒", "竞争格局",
        "市占率", "公司指引", "一致预期", "卖方预测", "市场预期", "预期差",
        "估值", "股价", "风险", "失效条件", "财报", "业绩", "公告",
    )
    hits = []
    for token in terms:
        if token in value and token not in hits:
            hits.append(token)
    return " ".join(hits[:6])
