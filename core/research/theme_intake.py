"""Human checkpoint for broad, long-running investment themes.

The checkpoint is intentionally narrow: a detailed research request should run
immediately, while a bare ``分析一下某主题`` benefits from one question that
changes the research emphasis.  The generic event/theme skill remains
comprehensive in either case; the answer only changes ordering and emphasis.
"""
from __future__ import annotations

import re


_FULL = (
    "全面研究", "完整研究", "完整主题", "系统研究", "从头研究", "全部都看",
    "都要", "都看", "全都看", "完整分析",
)
_BROAD = (
    "分析一下", "分析下", "研究一下", "研究下", "看一下", "看下", "怎么看",
    "怎么样", "了解一下", "帮我看看", "帮我看下",
)
_CANCEL = {"取消", "算了", "先不看", "不看了", "先不研究", "不用了", "放弃"}

_DIMENSIONS = {
    "definition_scope": ("是什么", "定义", "边界", "包括什么", "不包括什么", "概念"),
    "origin_timeline": ("起源", "从什么时候", "什么时候开始", "发展", "演进", "时间线", "到现在"),
    "current_catalysts": ("为什么", "原因", "催化", "升温", "炒作", "最近", "近期", "当前"),
    "investment_impact": ("影响", "利好", "利空", "受益", "承压", "板块", "产业链", "价值量"),
    "expectation_change": ("预期", "变化", "修订", "市场叙事", "一致预期"),
    "validation": ("风险", "反证", "失效", "验证", "跟踪", "里程碑", "监控"),
}


def assess(question: str, subject: str, summary: dict | None = None) -> dict:
    """Return a public research brief and whether one clarification is useful."""
    text = (question or "").strip()
    dimensions = [
        key for key, tokens in _DIMENSIONS.items()
        if any(token.lower() in text.lower() for token in tokens)
    ]
    explicit_full = any(token in text for token in _FULL)
    preference = _saved_preference(summary or {}, subject)
    residual = _residual(text, subject)
    generic = (
        not explicit_full
        and not dimensions
        and (not residual or any(token in text for token in _BROAD))
    )
    needs_clarification = bool(generic and not preference)
    focus = preference or (
        "完整主题档案"
        if explicit_full or len(dimensions) >= 2
        else _focus_from_dimensions(dimensions)
    )
    if not focus:
        focus = "完整主题档案（优先近期催化与投资影响）"
    brief = {
        "subject": subject,
        "object_kind": "EVOLVING_THEME",
        "scope": "COMPREHENSIVE",
        "focus": focus,
        "time_horizon": "MID_TERM",
        "market_scope": "CN_EQUITY_WITH_GLOBAL_CAUSAL_CHAIN",
        "requested_dimensions": dimensions,
        "default_if_skipped": "完整主题档案（优先近期催化与投资影响，中线视角）",
    }
    pending = {
        "status": "AWAITING_THEME_FOCUS",
        "subject": subject,
        "original_question": text,
        "research_brief": brief,
        "options": [
            "概念、起源与时间线",
            "最近为什么升温",
            "产业链与板块影响",
            "市场预期与验证指标",
            "全部都看",
        ],
    }
    reply = (
        "可以研究 {0}。这个主题范围很大，我只确认一个会改变研究重点的问题：\n\n"
        "你更想先看哪一层——①概念、起源与时间线，②最近为什么升温，"
        "③产业链和板块影响，④市场预期与后续验证，还是全部都看？\n\n"
        "如果你不选，我默认做完整主题档案，优先近期催化和投资影响，按中线视角展开。"
    ).format(subject)
    return {
        "action": "CLARIFY" if needs_clarification else "PROCEED",
        "needs_clarification": needs_clarification,
        "research_brief": brief,
        "pending": pending,
        "reply": reply,
        "reason": "MISSING_RESEARCH_EMPHASIS" if needs_clarification else "REQUEST_SUFFICIENT",
    }


def resume(message: str, summary: dict) -> dict | None:
    """Resolve a pending theme checkpoint into a concrete research question."""
    pending = summary.get("pending_theme_intake") or {}
    if pending.get("status") != "AWAITING_THEME_FOCUS":
        return None
    text = (message or "").strip()
    if not text:
        return None
    if "".join(text.split()) in _CANCEL:
        return {
            "action": "CANCEL",
            "subject": pending.get("subject") or "这个主题",
            "reply": "好，这轮主题研究先不展开。之后直接告诉我想看哪个主题或哪条变化就行。",
        }
    focus = normalize_focus(text)
    subject = pending.get("subject") or "研究主题"
    original = pending.get("original_question") or subject
    query = "{0}。用户补充的研究重点：{1}".format(original, focus)
    brief = dict(pending.get("research_brief") or {})
    brief.update({"subject": subject, "focus": focus, "scope": "COMPREHENSIVE"})
    return {
        "action": "PROCEED",
        "subject": subject,
        "research_query": query,
        "research_brief": brief,
        "focus": focus,
    }


def normalize_focus(value: str) -> str:
    text = (value or "").strip()
    compact = "".join(text.split())
    if any(token in compact for token in _FULL) or compact in {"全部", "全面", "完整", "默认"}:
        return "完整主题档案（优先近期催化与投资影响）"
    numbered = {
        "1": "概念、起源与时间线", "第一个": "概念、起源与时间线",
        "2": "最近升温的直接催化", "第二个": "最近升温的直接催化",
        "3": "产业链与板块影响", "第三个": "产业链与板块影响",
        "4": "市场预期与验证指标", "第四个": "市场预期与验证指标",
        "5": "完整主题档案（优先近期催化与投资影响）", "第五个": "完整主题档案（优先近期催化与投资影响）",
    }
    if compact in numbered:
        return numbered[compact]
    return text[:160]


def save_preference(summary: dict, subject: str, brief: dict) -> None:
    preferences = dict(summary.get("theme_research_preferences") or {})
    preferences[subject] = {
        "focus": brief.get("focus") or "",
        "time_horizon": brief.get("time_horizon") or "MID_TERM",
    }
    summary["theme_research_preferences"] = preferences


def _saved_preference(summary: dict, subject: str) -> str:
    row = (summary.get("theme_research_preferences") or {}).get(subject) or {}
    return row.get("focus") or ""


def _focus_from_dimensions(dimensions: list[str]) -> str:
    labels = {
        "definition_scope": "概念与边界",
        "origin_timeline": "起源与时间线",
        "current_catalysts": "近期催化",
        "investment_impact": "产业链与板块影响",
        "expectation_change": "市场预期变化",
        "validation": "风险、反证与验证指标",
    }
    return "、".join(labels[item] for item in dimensions if item in labels)


def _residual(text: str, subject: str) -> str:
    value = text
    for token in (subject,) + _BROAD + ("请", "你", "帮我", "我想", "一下", "这个", "主题", "事件", "的", "呢", "吧"):
        if token:
            value = value.replace(token, " ")
    return re.sub(r"[^A-Za-z0-9\u4e00-\u9fff]+", "", value)
