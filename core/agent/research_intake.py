"""Adaptive human checkpoint for broad company-research requests.

This module is deliberately a policy layer rather than another intent router:
the normal planner still decides whether a turn is company research.  Once it
does, this layer asks one material question only when the requested research
direction is genuinely unresolved.
"""
from __future__ import annotations

import re

from core.research.entity_resolver import names_in


_BROAD_REQUESTS = (
    "怎么样", "如何", "怎么看", "研究一下", "研究下", "了解一下",
    "帮我看看", "帮我看下", "看一下", "看下",
)
_FULL_DOSSIER = (
    "完整档案", "完整公司档案", "全面研究", "全部都看", "都看看", "全都看",
    "系统研究", "完整研究", "从头研究",
)
_SPECIFIC_FOCUS = (
    "卖什么", "卖给谁", "靠什么赚钱", "业务分部", "收入来源", "利润来源",
    "基本面", "商业模式", "核心逻辑", "增长变量", "增长驱动", "利润驱动",
    "利润弹性", "业绩弹性", "量价", "产能", "利用率", "毛利", "净利",
    "现金流", "资本开支", "营运资本", "负债", "财报", "业绩", "收入",
    "核心壁垒", "护城河", "竞争优势", "竞争格局", "市占率", "行业位置",
    "一致预期", "公司指引", "市场预期", "卖方预测", "市场叙事", "预期差",
    "估值", "股价", "隐含预期", "gap", "GAP", "催化剂", "风险", "失效条件",
    "反证", "监控指标", "公告", "电话会", "调研纪要", "订单", "客户",
    "产品", "业务", "板块", "技术", "供应链", "原材料", "成本", "价格", "销量",
    "涨价", "降价", "为什么",
)
_INCREMENTAL_UPDATE = (
    "有什么变化", "有何变化", "最新变化", "新变化", "新增信息", "新信息",
    "最新消息", "新消息", "更新档案", "更新一下", "最近公告", "最新公告",
    "有没有新", "发生了什么",
)
_CANCEL = {"取消", "算了", "先不看", "不看了", "先不研究", "不用了", "放弃"}
_INTERRUPTION = (
    "天气", "几号", "星期几", "几点", "你好", "您好", "谢谢", "在吗",
    "盘面", "大盘", "A股市场", "持仓", "复盘昨天", "记录一下",
)


def resume_pending_intake(message: str, summary: dict, fallback: dict) -> dict | None:
    """Resolve a previous one-question intake, or leave unrelated turns alone."""
    pending = summary.get("pending_research_intake") or {}
    if pending.get("status") != "AWAITING_FOCUS":
        return None
    text = (message or "").strip()
    compact = "".join(text.split())
    if compact in _CANCEL:
        return _chat_route(
            "好，先不展开这家公司。之后你想从财报、增长、预期或风险中的任何一块继续，直接告诉我就行。",
            reason="RESEARCH_INTAKE_CANCELLED",
            entity=pending,
            action="cancelled",
        )

    pending_name = pending.get("entity_name") or ""
    named = names_in(text)
    if named and pending_name and named[0].get("name") != pending_name:
        return None
    if fallback.get("skill") and fallback.get("skill") != "company-research":
        return None
    if not text or any(token in text for token in _INTERRUPTION):
        return None

    focus = _normalize_focus(text)
    code = pending.get("entity_code") or ""
    original = pending.get("original_question") or ""
    research_query = "{0}：这轮重点研究「{1}」".format(pending_name, focus)
    if original:
        research_query += "。原始问题：{0}".format(original)
    return {
        "skill": "company-research",
        "domain": "RESEARCH",
        "entity": {"name": pending_name, "code": code},
        "entities": [{"mention": pending_name, "type": "company", "code": code}],
        "confidence": 1.0,
        "reason_code": "RESEARCH_INTAKE_RESOLVED",
        "intent": "RESEARCH_INTAKE_RESOLVED",
        "mode": "SKILL",
        "need_network": True,
        "need_market_data": False,
        "need_portfolio_context": False,
        "need_research_memory": True,
        "need_decision_memory": False,
        "write_action": False,
        "context_event": "",
        "reply": "",
        "journal": {},
        "research_query": research_query,
        "research_focus": focus,
        "research_focus_category": _focus_category(text),
        "intake_action": "resolved",
    }


def apply_research_intake(route: dict, message: str, summary: dict) -> dict:
    """Ask one adaptive question for a broad, unresolved company request."""
    if route.get("skill") != "company-research":
        return route
    entity = route.get("entity") or {}
    name = (entity.get("name") or "").strip()
    if not name:
        return route
    text = (message or "").strip()

    # An explicit full-dossier request is itself a resolved preference.  Keep
    # it so a later "再看看这家公司" does not restart the same intake.
    if any(token in text for token in _FULL_DOSSIER):
        planned = dict(route)
        planned["research_focus"] = "完整公司档案"
        planned["research_focus_category"] = "FULL_DOSSIER"
        planned["intake_action"] = "resolved"
        return planned

    # Narrow questions and explicit update requests are already well scoped.
    if _is_specific(text) or _has_specific_residual(text, name, entity.get("code") or "") or not _is_broad(text):
        return route

    preferences = summary.get("research_preferences_by_entity") or {}
    saved = preferences.get(name) if isinstance(preferences, dict) else None
    if isinstance(saved, dict) and saved.get("focus"):
        planned = dict(route)
        focus = saved["focus"]
        planned["research_focus"] = focus
        planned["research_focus_category"] = saved.get("category") or "CUSTOM"
        planned["research_query"] = "{0}。沿用你之前确认的研究重点：{1}".format(text, focus)
        planned["reason_code"] = "RESEARCH_PREFERENCE_REUSED"
        planned["intake_action"] = "reused"
        return planned

    code = entity.get("code") or ""
    pending = {
        "status": "AWAITING_FOCUS",
        "entity_name": name,
        "entity_code": code,
        "original_question": text,
        "suggested_focuses": [
            "公司基本盘与竞争壁垒",
            "最近财报和事实变化",
            "增长变量与利润弹性",
            "市场预期、估值与预期差",
            "风险与失效条件",
            "完整公司档案",
        ],
    }
    reply = (
        "可以研究 {0}。不过“怎么样”范围太大，我先确认一个会改变研究路线的问题：\n\n"
        "你这次更关心哪一块——公司基本盘和竞争壁垒、最近财报与变化、增长和利润弹性、"
        "市场预期/估值，还是风险与失效条件？如果都想看，直接说“完整公司档案”。"
    ).format(name)
    return _chat_route(
        reply,
        reason="RESEARCH_INTAKE",
        entity=pending,
        action="awaiting_focus",
        pending=pending,
    )


def _is_specific(text: str) -> bool:
    return any(token in text for token in _FULL_DOSSIER + _SPECIFIC_FOCUS + _INCREMENTAL_UPDATE)


def _is_broad(text: str) -> bool:
    return any(token in text for token in _BROAD_REQUESTS)


def _has_specific_residual(text: str, name: str, code: str = "") -> bool:
    """Recognize free-form product/topic focus without a hard-coded taxonomy."""
    residue = text or ""
    for token in (name, code) + _BROAD_REQUESTS + (
        "帮我", "请", "我想", "想", "了解", "这家公司", "这个公司", "公司",
        "现在", "最近", "目前", "大概", "到底", "一下", "一下子", "吧", "呗", "呢", "的",
    ):
        if token:
            residue = residue.replace(token, " ")
    residue = re.sub(r"[^A-Za-z0-9\u4e00-\u9fff]+", "", residue)
    return len(residue) >= 2


def _normalize_focus(text: str) -> str:
    compact = "".join((text or "").split())
    if any(token in compact for token in _FULL_DOSSIER) or compact in {"全部", "都看", "全面", "完整"}:
        return "完整公司档案"
    numbered = {
        "1": "公司基本盘与竞争壁垒", "第一个": "公司基本盘与竞争壁垒",
        "2": "最近财报和事实变化", "第二个": "最近财报和事实变化",
        "3": "增长变量与利润弹性", "第三个": "增长变量与利润弹性",
        "4": "市场预期、估值与预期差", "第四个": "市场预期、估值与预期差",
        "5": "风险与失效条件", "第五个": "风险与失效条件",
        "6": "完整公司档案", "第六个": "完整公司档案",
    }
    if compact in numbered:
        return numbered[compact]
    for marker, label in numbered.items():
        if len(marker) > 1 and marker in compact:
            return label
    return (text or "").strip()[:160]


def _focus_category(text: str) -> str:
    focus = _normalize_focus(text)
    if focus == "完整公司档案":
        return "FULL_DOSSIER"
    if any(token in text for token in ("财报", "业绩", "变化", "公告", "最新")):
        return "EARNINGS_AND_CHANGE"
    if any(token in text for token in ("增长", "利润", "弹性", "量价", "产能", "毛利")):
        return "GROWTH_AND_PROFIT"
    if any(token in text for token in ("预期", "估值", "股价", "GAP", "gap")):
        return "EXPECTATIONS_AND_VALUATION"
    if any(token in text for token in ("风险", "失效", "反证")):
        return "RISK_AND_INVALIDATION"
    if any(token in text for token in ("基本盘", "壁垒", "竞争", "业务", "护城河")):
        return "BUSINESS_AND_MOAT"
    return "CUSTOM"


def _chat_route(reply: str, *, reason: str, entity: dict, action: str, pending: dict | None = None) -> dict:
    name = entity.get("entity_name") or ""
    code = entity.get("entity_code") or ""
    return {
        "skill": "",
        "domain": "GENERAL",
        "entity": {"name": name, "code": code},
        "entities": [{"mention": name, "type": "company", "code": code}] if name else [],
        "confidence": 1.0,
        "reason_code": reason,
        "intent": reason,
        "mode": "CHAT",
        "need_network": False,
        "need_market_data": False,
        "need_portfolio_context": False,
        "need_research_memory": False,
        "need_decision_memory": False,
        "write_action": False,
        "context_event": "",
        "reply": reply,
        "journal": {},
        "intake_action": action,
        "pending_research_intake": pending or {},
    }
