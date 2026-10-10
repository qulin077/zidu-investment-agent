"""P1.4 Memory 类型。四层分开：Decision / Mistake / Pattern / Rule。"""
from __future__ import annotations

PATTERN_STATUSES = ("OBSERVED", "CANDIDATE", "CONFIRMED", "DISMISSED")
RULE_STATUSES = ("DRAFT", "PROPOSED", "ACTIVE", "REJECTED", "RETIRED")
REMINDER_FEEDBACK = ("RELEVANT", "NOT_RELEVANT")
SUMMARIZER_VERSION = "ps1"
RULE_WORDING_VERSION = "rw1"
REMINDER_LIMIT = 3
CANDIDATE_MIN = 2

FOMO_PHRASES = ("怕踏空", "FOMO", "fomo", "担心错过", "错过这波", "害怕踏空")
PERSONA_BANNED = ("冲动型", "天生容易", "风险控制很差", "你是一个", "人格", "心理疾病")
VAGUE_RULES = ("谨慎一点", "以后谨慎", "冷静一点", "不要贪心", "控制情绪", "别冲动", "不要冲动", "心态")
ACTIONABLE_MARKERS = ("若", "则", "不得", "必须", "只能", "WHEN", "DO", "确认后", "出现")
