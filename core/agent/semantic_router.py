"""确定性降级路由；正常 Agent turn 由模型行动规划器主导。"""
from __future__ import annotations

import json
import re

from core.agent.skill_registry import SKILLS
from core.agent.types import turn_plan
from core.research.entity_resolver import names_in
from core.research.skills import route as research_route

AGENT_ROUTER_PROMPT_VERSION = "ar2"

ROUTER_PROMPT = """
你是用户长期使用的 Investment Agent。你先理解对话，再判断应该直接聊天，还是调用一个垂直 Skill。
只输出 JSON。
当前可用 Skills：
company-research
industry-research
event-impact
candidate-discovery
market-scan
security-snapshot
portfolio-monitor
decision-recorder
guided-review
memory-query
输出 mode、intent、skill、reply、entities、need_network、need_market_data、need_portfolio_context、need_research_memory、need_decision_memory、write_action、confidence、journal。
mode 只能是 CHAT 或 SKILL。
CHAT 时 reply 要像熟悉用户的伙伴，先接住原话，可以只追问一个问题。不要把聊天强行变成研究。
只有用户明确询问公司、行业、事件、市场、持仓、决策记录、复盘或历史模式时才选 Skill。
“今天天气怎么样”“今天好累”“我卖飞了很难受”“然后呢”都是 CHAT，不是 company-research。
提到股票名但在表达情绪或讲刚才发生的事，也不自动进入研究。
用户明确说“帮我记下/记录一下”交易逻辑时，选 decision-recorder；普通心情和想法可在 journal 中建议保存。
journal 结构：save、entry_type、summary。entry_type 只能是 FEELING、THOUGHT、TRADE_NOTE、REVIEW_NOTE、GENERAL。
不要给买卖建议、目标价或仓位建议。
提示词版本 ar2。
""".strip()

_CHAT = {
    "你好", "您好", "你好啊", "在吗", "在不在", "嗨", "哈喽",
    "hello", "hi", "hey", "谢谢", "谢谢你", "早上好", "晚上好",
}
_SMALL = ("好累", "太累", "累了", "状态一般", "想太多", "很难")
_WEATHER = ("天气", "温度", "下雨", "晴天", "降温")
_MEMORY = ("重复问题", "重复犯错", "重复犯", "有什么规则", "是不是一直", "是不是又", "又追高", "看看我最近", "帮我看看我")
_REVIEW = ("复盘", "为什么亏", "为什么又亏", "这笔为什么错")
_RECORD = ("想买", "想建", "建仓", "建一成", "一成仓", "买一点", "10%", "上一成")
_JOURNAL_REQUEST = ("记录一下", "我要记录", "帮我记一下", "帮我记下", "记一下")
_FOLLOW = ("真实", "占比", "这块", "展开", "毛利")
_CLARIFY = {"帮我看一下", "帮我看看", "看一下", "看看"}
_CANDIDATE = ("哪些股票", "什么股票", "相关公司", "哪些公司", "新股票", "利好什么股票", "什么公司受益", "公司受益")
_PORTFOLIO = ("持仓", "我的股票", "我现在的股票", "持有它", "持有")
_MARKET = (
    "钱在哪", "哪个板块", "什么板块", "资金流向", "有主线", "市场风格", "谁更强",
    "板块轮动", "红利", "占优", "盘面", "大盘", "今天市场", "今日市场",
    "A股市场", "A股", "市场怎么样",
)
_SECURITY_MARKET = (
    "现价", "当前价格", "现在多少钱", "多少钱", "股价多少", "最新价格",
    "技术面", "技术分析", "走势", "K线", "k线", "均线", "MACD", "macd",
    "RSI", "rsi", "量能", "放量", "缩量", "波动率",
)
_EVENT = ("增量", "意味着", "有什么影响", "会带来", "新机", "新增量")
_INDUSTRY = ("产业链", "竞争格局", "供需", "赛道", "技术路线", "行业利润", "行业空间")
_COMPANY = (
    "怎么样", "如何", "怎么看", "靠什么赚钱", "核心逻辑", "基本面", "财报", "利润", "真实吗",
    "研究一下", "研究下", "全面研究", "完整研究", "完整更新", "更新档案", "公司档案", "完整档案",
    "季报", "半年报", "现金流", "产品结构",
)
_TRADE_REFLECTION = ("买了", "卖了", "卖飞", "追高", "割了", "亏了", "赚了", "冲动", "难受", "后悔", "烦")
_NON_ENTITIES = {
    "天气", "心情", "状态", "股票", "市场", "今天", "最近", "现在", "这个", "那个",
    "这笔", "那笔", "公司", "行业", "逻辑", "问题", "一下", "怎么样",
}
_DOMAIN = {
    "company-research": "RESEARCH",
    "industry-research": "RESEARCH",
    "event-impact": "RESEARCH",
    "candidate-discovery": "RESEARCH",
    "market-scan": "GENERAL",
    "security-snapshot": "GENERAL",
    "portfolio-monitor": "GENERAL",
    "decision-recorder": "DECISION",
    "guided-review": "REVIEW",
    "memory-query": "GENERAL",
}


def build_plan(message: str, session: dict | None = None, llm=None, messages: list | None = None) -> dict:
    text = (message or "").strip()
    session = session or {}
    summary = session.get("summary") or {}
    if not text:
        return _chat(0, "EMPTY")
    compact = "".join(text.split()).lower()
    if compact in _CHAT or _small_talk(text):
        return _chat(0.99, "CHAT")
    if any(token in text for token in _WEATHER):
        return _chat(0.99, "OUT_OF_DOMAIN")
    if any(token in text for token in _MEMORY):
        return _skill("memory-query", "MEMORY_QUERY", 0.9, "MEMORY_INTENT", _known_entities(text), decision_memory=True)
    if any(token in text for token in _REVIEW):
        return _skill("guided-review", "GUIDED_REVIEW", 0.9, "REVIEW_INTENT", _known_entities(text), decision_memory=True)
    wants_note = any(token in text for token in _JOURNAL_REQUEST)
    looks_like_decision = any(token in text for token in _RECORD) or any(
        token in text for token in ("买入", "卖出", "加仓", "减仓", "仓位", "止损", "失效条件")
    )
    if compact in {"记录一下", "我要记录"} or any(token in text for token in _RECORD) or (wants_note and looks_like_decision):
        return _skill(
            "decision-recorder", "DECISION_RECORD", 0.92, "RECORDER_INTENT",
            _entities(text, summary), write_action=True, decision_memory=True,
        )
    pending_draft = summary.get("pending_recorder_draft_id") or ""
    if pending_draft and compact in {"确认", "确认保存", "保存", "就这样", "没问题"}:
        plan = _skill(
            "decision-recorder", "CONFIRM_DECISION", 0.99, "CONFIRM_PENDING_DRAFT",
            _entities("", summary), write_action=True, decision_memory=True,
        )
        plan["pending_draft_id"] = pending_draft
        return plan
    if pending_draft and compact in {"取消", "不记了", "算了", "放弃"}:
        plan = _skill(
            "decision-recorder", "CANCEL_DECISION", 0.99, "CANCEL_PENDING_DRAFT",
            _entities("", summary), write_action=True, decision_memory=True,
        )
        plan["pending_draft_id"] = pending_draft
        return plan
    active = session.get("active_project_id") or ""
    if active and "展开" in text:
        return _skill(_research_skill(summary), "SECTION_FOCUS", 0.88, "SECTION_FOCUS", _entities("", summary), research=True, network=True)
    if active and any(token in text for token in _FOLLOW) and len(text) <= 40:
        return _skill(_research_skill(summary), "ACTIVE_PROJECT", 0.86, "ACTIVE_PROJECT", _entities("", summary), research=True, network=True)
    named = names_in(text)
    active_name = summary.get("entity_name") or summary.get("active_entity") or ""
    if active and active_name and named and named[0].get("name") == active_name:
        return _skill("company-research", "COMPANY_RESEARCH", 0.9, "SAME_ENTITY", _entities(text, summary), research=True, network=True)
    if compact in _CLARIFY:
        return _clarify()
    contextual = _context_follow(text, summary)
    if contextual:
        return contextual
    early = _offline(text)
    if early.get("skill") in ("market-scan", "security-snapshot", "portfolio-monitor", "event-impact", "candidate-discovery") and early.get("confidence", 0) >= 0.9:
        return _with_context(early, summary)
    # 已识别的公司 + 明确研究问法可以直接走工具；叙述交易和情绪时不能仅因
    # 出现公司名就劫持到 research。
    if named and any(token in text for token in _COMPANY) and not any(token in text for token in _TRADE_REFLECTION):
        return _skill("company-research", "COMPANY_RESEARCH", 0.94, "COMPANY_RESEARCH", _entities(text, summary), research=True, network=True)
    if any(token in text for token in _INDUSTRY) and not named:
        return _skill("industry-research", "INDUSTRY_RESEARCH", 0.92, "INDUSTRY_RESEARCH", [], research=True, network=True)
    researched = research_route(text, llm=None)
    if researched.get("reason_code") == "AMBIGUOUS" and llm is not None:
        return _legacy_llm(llm, text, named) or _clarify("AMBIGUOUS")
    if llm is not None:
        parsed = _semantic(llm, text, summary, messages or [])
        offline_now = _offline(text)
        if parsed and parsed.get("mode") == "CHAT" and offline_now.get("skill") in ("market-scan", "security-snapshot", "portfolio-monitor", "event-impact", "candidate-discovery") and offline_now.get("confidence", 0) >= 0.9:
            return _with_context(offline_now, summary)
        if parsed:
            return _with_context(parsed, summary)
    reason = researched.get("reason_code") or ""
    if reason == "AMBIGUOUS":
        return _clarify("AMBIGUOUS")
    if reason == "NEEDS_CLARIFICATION":
        return _clarify("NEEDS_CLARIFICATION")
    offline = _offline(text)
    if offline.get("confidence", 0) >= 0.8:
        return _with_context(offline, summary)
    return _with_context(offline, summary)


def _small_talk(text: str) -> bool:
    if any(token in text for token in _RECORD + _JOURNAL_REQUEST + _REVIEW + _MEMORY + _COMPANY + _INDUSTRY + _EVENT + _MARKET + _PORTFOLIO + _CANDIDATE):
        return False
    return any(token in text for token in _SMALL)


def _question_like(text: str) -> bool:
    return any(token in text for token in ("怎么", "什么", "吗", "？", "?"))


def _research_skill(summary: dict) -> str:
    last = summary.get("last_research_skill") or summary.get("last_skill") or ""
    if last in ("company-research", "industry-research"):
        return last
    return "company-research"


def _known_entities(text: str) -> list:
    named = names_in(text or "")
    if not named:
        return []
    return [{"mention": named[0].get("name") or "", "type": "company", "code": named[0].get("code") or ""}]


def _entities(text: str, summary: dict | None = None) -> list:
    summary = summary or {}
    named = names_in(text) if text else []
    if named:
        return [{"mention": named[0].get("name") or "", "type": "company", "code": named[0].get("code") or ""}]
    mention, code = _mention(text)
    if mention and mention not in _NON_ENTITIES:
        kind = "technology_platform" if re.search(r"[A-Za-z]", mention) else "company"
        return [{"mention": mention, "type": kind, "code": code}]
    saved = summary.get("active_entity") or summary.get("entity_name") or ""
    if saved:
        return [{"mention": saved, "type": "company", "code": summary.get("entity_code") or ""}]
    return []


def _mention(text: str) -> tuple:
    named = names_in(text or "")
    if named:
        return named[0].get("name") or "", named[0].get("code") or ""
    english = re.findall(r"[A-Za-z][A-Za-z0-9.+-]{1,16}", text or "")
    head = re.split(
        r"[:：]|怎么样|如何|怎么看|财报|季报|半年报|现金流|产品结构|为什么|靠什么|核心逻辑|基本面|真实吗|算吗|"
        r"现价|当前价格|现在多少钱|多少钱|股价多少|最新价格|技术面|技术分析|走势|"
        r"K线|k线|均线|MACD|macd|RSI|rsi|量能|放量|缩量|波动率",
        text or "", maxsplit=1,
    )[0]
    head = re.sub(
        r"^(?:帮我)?(?:完整研究一下|全面研究一下|完整研究|全面研究|完整更新|更新档案|看看|看下|研究一下|研究下)?",
        "",
        head,
    )
    head = re.sub(r"(这个公司|这家公司|公司)$", "", head)
    head = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]", "", head)
    residue = ("如果", "什么", "怎么", "这个", "方向", "最近", "现在", "看看", "帮我", "今天", "我想", "是否", "还是", "一下", "昨天", "那笔", "这笔", "复盘")
    if 2 <= len(head) <= 12 and head not in _NON_ENTITIES and not any(token in head for token in residue):
        return head, ""
    raw = text or ""
    for token in sorted(_RECORD + _JOURNAL_REQUEST + _COMPANY + _EVENT + _CANDIDATE + _REVIEW + _SECURITY_MARKET + ("我想", "今天", "计划", "帮我", "看看", "吗", "呢", "算吗", "昨天", "那笔", "这笔"), key=len, reverse=True):
        raw = raw.replace(token, " ")
    raw = re.sub(r"[？?，,。！!\s]", "", raw).lstrip("那")
    residue = ("如果", "什么", "怎么", "这个", "方向", "最近", "现在", "看看", "帮我", "今天", "我想", "是否", "还是", "一下", "昨天", "那笔", "这笔", "复盘")
    if any(token in raw for token in residue):
        raw = ""
    raw = re.sub(
        r"^(?:帮我)?(?:完整研究一下|全面研究一下|完整研究|全面研究|完整更新|更新档案|看看|看下|研究一下|研究下)?",
        "",
        raw,
    )
    raw = re.sub(r"(这个公司|这家公司|公司)$", "", raw)
    if 2 <= len(raw) <= 16 and raw not in _NON_ENTITIES:
        return raw, ""
    if english:
        return max(english, key=len), ""
    return "", ""


def _chat(confidence: float, reason: str) -> dict:
    return turn_plan(mode="CHAT", intent="GENERAL_CHAT", skill=None, confidence=confidence, reason_code=reason, domain="GENERAL")


def _clarify(reason: str = "CLARIFY") -> dict:
    return turn_plan(mode="CHAT", intent="CLARIFY", skill=None, confidence=0.4, reason_code=reason, domain="GENERAL")


def _unavailable() -> dict:
    return turn_plan(mode="CHAT", intent="LLM_UNAVAILABLE", skill=None, confidence=0.2, reason_code="LLM_UNAVAILABLE", domain="GENERAL")


def _skill(skill: str, intent: str, confidence: float, reason: str, entities: list, *, research=False, network=False, market=False, portfolio=False, write_action=False, decision_memory=False) -> dict:
    return turn_plan(
        mode="SKILL",
        intent=intent,
        skill=skill,
        entities=entities,
        need_network=network,
        need_market_data=market,
        need_portfolio_context=portfolio,
        need_research_memory=research,
        need_decision_memory=decision_memory,
        write_action=write_action,
        confidence=confidence,
        reason_code=reason,
        domain=_DOMAIN.get(skill, "GENERAL"),
    )


def _context_follow(text: str, summary: dict):
    event = summary.get("active_event") or ""
    if event and any(token in text for token in ("哪些股票", "什么股票", "相关公司", "受益", "算吗")):
        if "算吗" in text:
            entities = _entities(text, summary)
            plan = _skill("company-research", "COMPANY_RESEARCH", 0.84, "CONTEXT_ENTITY", entities, research=True, network=True)
            plan["context_event"] = event
            return plan
        plan = _skill("candidate-discovery", "CANDIDATE_DISCOVERY", 0.86, "CONTEXT_EVENT", [{"mention": event, "type": "technology_platform"}], research=True, network=True)
        plan["context_event"] = event
        return plan
    if (summary.get("active_entity") or summary.get("entity_name")) and "持有" in text:
        return _skill("portfolio-monitor", "PORTFOLIO_MONITOR", 0.84, "CONTEXT_PORTFOLIO", _entities("", summary), portfolio=True)
    return None


def _offline(text: str) -> dict:
    entities = _entities(text, {})
    if any(token in text for token in _SECURITY_MARKET) and entities:
        return _skill("security-snapshot", "SECURITY_SNAPSHOT", 0.96, "SECURITY_MARKET_DATA", entities, network=True)
    if any(token in text for token in _CANDIDATE) or ("哪些" in text and "公司" in text) or ("受益" in text and "公司" in text):
        return _skill("candidate-discovery", "CANDIDATE_DISCOVERY", 0.9, "CANDIDATE_DISCOVERY", entities, research=True, network=True)
    if any(token in text for token in _PORTFOLIO):
        return _skill("portfolio-monitor", "PORTFOLIO_MONITOR", 0.9, "PORTFOLIO_MONITOR", entities, portfolio=True)
    if any(token in text for token in _MARKET):
        return _skill("market-scan", "MARKET_SCAN", 0.9, "MARKET_SCAN", [], market=True)
    if any(token in text for token in _EVENT):
        return _skill("event-impact", "EVENT_IMPACT", 0.9, "EVENT_IMPACT", entities, research=True, network=True)
    if any(token in text for token in _INDUSTRY):
        return _skill("industry-research", "INDUSTRY_RESEARCH", 0.88, "INDUSTRY_RESEARCH", [], research=True, network=True)
    if any(token in text for token in _COMPANY) and entities:
        return _skill("company-research", "COMPANY_RESEARCH", 0.9, "COMPANY_RESEARCH", entities, research=True, network=True)
    return _chat(0.66, "CHAT")


def _with_context(plan: dict, summary: dict) -> dict:
    event = summary.get("active_event") or ""
    if event and not plan.get("context_event"):
        plan["context_event"] = event
    if plan.get("skill") in ("decision-recorder", "portfolio-monitor") and not plan.get("entities"):
        saved = summary.get("active_entity") or summary.get("entity_name") or ""
        if saved:
            plan["entities"] = [{"mention": saved, "type": "company", "code": summary.get("entity_code") or ""}]
    return plan


def _legacy_llm(llm, text: str, named: list):
    try:
        raw = llm.generate_structured(
            "只输出 JSON：skill。skill 只能是 industry-research 或 company-research。",
            text,
            {"type": "object"},
            temperature=0,
        )
    except AssertionError:
        raise
    except Exception:
        return None
    try:
        data = json.loads(raw) if isinstance(raw, str) else dict(raw or {})
    except json.JSONDecodeError:
        data = {}
    skill = data.get("skill") or ""
    if skill not in ("industry-research", "company-research"):
        return None
    entities = []
    if named and skill == "company-research":
        entities = [{"mention": named[0].get("name") or "", "type": "company", "code": named[0].get("code") or ""}]
    return _skill(skill, "INDUSTRY_RESEARCH" if skill == "industry-research" else "COMPANY_RESEARCH", 0.7, "LLM_ROUTER", entities, research=True, network=True)


def _semantic(llm, text: str, summary: dict, messages: list | None = None):
    payload = {
        "message": text,
        "active_entity": summary.get("active_entity") or summary.get("entity_name") or "",
        "active_event": summary.get("active_event") or "",
        "active_industry": summary.get("active_industry") or "",
        "last_skill": summary.get("last_skill") or "",
        "recent_conversation": [
            {"role": row.get("role") or "user", "content": (row.get("content") or "")[:600]}
            for row in (messages or [])[-12:]
        ],
    }
    try:
        raw = llm.generate_structured(ROUTER_PROMPT, json.dumps(payload, ensure_ascii=False), {"type": "object"}, temperature=0)
    except AssertionError:
        raise
    except Exception:
        return None
    try:
        data = json.loads(raw) if isinstance(raw, str) else dict(raw or {})
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    mode = (data.get("mode") or "").upper()
    skill = data.get("skill") or None
    if skill == "":
        skill = None
    if mode == "CHAT" or not skill:
        plan = _chat(float(data.get("confidence") or 0.8), "SEMANTIC")
        plan["reply"] = (data.get("reply") or "").strip()
        plan["journal"] = _journal(data.get("journal"))
        return plan
    if skill not in SKILLS:
        return None
    research = skill in ("company-research", "industry-research", "event-impact", "candidate-discovery")
    entities = [row for row in (data.get("entities") or []) if isinstance(row, dict)]
    if not entities:
        entities = _entities(text, summary)
    if skill == "company-research":
        explicit = _entities(text, {})
        contextual_ref = any(token in text for token in ("它", "这家公司", "那家公司", "这块", "这个标的"))
        if not explicit and not contextual_ref:
            plan = _chat(float(data.get("confidence") or 0.75), "SEMANTIC_GUARD")
            plan["reply"] = (data.get("reply") or "").strip()
            plan["journal"] = _journal(data.get("journal"))
            return plan
        entities = explicit or entities
    plan = turn_plan(
        mode="SKILL",
        intent=data.get("intent") or skill,
        skill=skill,
        entities=entities,
        need_network=research if data.get("need_network") is None else bool(data.get("need_network")),
        need_market_data=skill == "market-scan" if data.get("need_market_data") is None else bool(data.get("need_market_data")),
        need_portfolio_context=skill == "portfolio-monitor" if data.get("need_portfolio_context") is None else bool(data.get("need_portfolio_context")),
        need_research_memory=research if data.get("need_research_memory") is None else bool(data.get("need_research_memory")),
        need_decision_memory=bool(data.get("need_decision_memory")),
        write_action=skill == "decision-recorder" if data.get("write_action") is None else bool(data.get("write_action")),
        confidence=float(data.get("confidence") or 0.75),
        reason_code="SEMANTIC",
        domain=_DOMAIN.get(skill, "GENERAL"),
        context_event=summary.get("active_event") or "",
    )
    plan["journal"] = _journal(data.get("journal"))
    return plan


def _journal(raw) -> dict:
    data = raw if isinstance(raw, dict) else {}
    kind = (data.get("entry_type") or "GENERAL").upper()
    if kind not in ("FEELING", "THOUGHT", "TRADE_NOTE", "REVIEW_NOTE", "GENERAL"):
        kind = "GENERAL"
    return {
        "save": bool(data.get("save")),
        "entry_type": kind,
        "summary": (data.get("summary") or "")[:240],
    }
