"""研究底稿的枚举、输出版本和完成条件。模型名字不在这里。"""
from __future__ import annotations

CLAIM_TYPES = ("FACT", "ESTIMATE", "INFERENCE", "OPINION")
CLAIM_STATUS = ("SINGLE_SOURCE", "CORROBORATED", "CONTESTED", "SUPERSEDED", "REJECTED")
SUPPORT_TYPES = ("SUPPORT", "CONTRADICT", "CONTEXT")
EXPOSURE_TYPES = ("DIRECT", "INDIRECT", "THEMATIC", "UNKNOWN")
PRIMARY_SOURCE_TYPES = (
    "FILING", "OFFICIAL", "EXCHANGE", "TRANSCRIPT",
    "COMPANY_FILING", "EARNINGS_CALL", "COMPANY_IR",
)
BROKER_SOURCE_TYPES = ("BROKER", "SELL_SIDE")
RUMOR_SOURCE_TYPES = ("MEDIA", "RUMOR", "EXPERT", "OTHER")
SOURCE_TYPES = (
    "OFFICIAL", "COMPANY_FILING", "EARNINGS_CALL", "COMPANY_IR", "INDUSTRY_ORG",
    "SELL_SIDE", "MEDIA", "EXPERT", "OTHER",
    "FILING", "EXCHANGE", "TRANSCRIPT", "BROKER", "RESEARCH_NOTE", "RUMOR",
)
SOURCE_QUALITY = ("PRIMARY", "SECONDARY", "WEAK")

DIFF_VERDICTS = ("STRENGTHENED", "WEAKENED", "UNCHANGED", "INVALIDATED")

RESEARCH_PLANNER_PROMPT_VERSION = "rp2"
CLAIM_EXTRACTOR_PROMPT_VERSION = "rc2"
THESIS_BUILDER_PROMPT_VERSION = "rt1"
THESIS_PROMPT_VERSION = THESIS_BUILDER_PROMPT_VERSION
PROMPT_TEMPERATURE = 0

OUTPUT_KEYS = (
    "research_question",
    "industry_definition",
    "value_chain",
    "key_drivers",
    "technology_routes",
    "market_structure",
    "company_mapping",
    "catalysts",
    "risks",
    "claims",
    "conflicts",
    "open_questions",
    "thesis",
    "evidence_refs",
)

RESERVED_SKILLS = (
    "industry-research",
    "company-research",
    "earnings-analysis",
    "event-impact",
    "thesis-update",
)
IMPLEMENTED_SKILLS = ("industry-research", "company-research", "event-impact")
COMMERCIAL_STAGES = (
    "DEVELOPMENT", "SAMPLE", "QUALIFICATION", "DESIGN_WIN",
    "MASS_PRODUCTION", "ORDER", "REVENUE_RECOGNIZED", "UNKNOWN",
)
RESEARCH_INTENTS = ("INDUSTRY_RESEARCH", "COMPANY_RESEARCH", "UNKNOWN")
DISCONFIRMATION_RESULTS = (
    "COUNTEREVIDENCE_FOUND",
    "NO_COUNTEREVIDENCE_FOUND_IN_CHECKED_SOURCES",
    "UNVERIFIABLE",
)
CLAIM_RELATIONS = ("SUPPORTS", "CONTRADICTS", "PREMISE_OF", "SUPERSEDES")
EXPECTATION_SOURCES = (
    "CONSENSUS_DATA", "MANAGEMENT_GUIDANCE", "SELL_SIDE_ESTIMATE", "MARKET_NARRATIVE",
)

# 研究判断可以写，买卖和仓位不能写。证据引文不在这个扫描范围里。
FORBIDDEN_PHRASES = (
    "建议买入",
    "建议卖出",
    "推荐买入",
    "推荐卖出",
    "目标价",
    "仓位",
    "加仓",
    "减仓",
    "取平均",
)
