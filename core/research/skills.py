"""研究意图路由。能用代码区分的，不调用模型。"""
from __future__ import annotations

import json
import re
from functools import lru_cache

from core.config import ROOT
from core.research.types import IMPLEMENTED_SKILLS, RESERVED_SKILLS

SKILL_DIR = ROOT / ".cursor" / "skills"
_STEP = re.compile(r"^Step\s+(\d+)\s+(.+?)\s*$", re.M)
_TICKER = re.compile(r"\b(\d{6}|[A-Z]{1,5})\b")
_INDUSTRY = (
    "产业链", "行业", "价值链", "竞争格局", "怎么传导", "催化", "技术路线",
    "环节", "供需", "赛道", "行业竞争",
)
_COMPANY_INTENT = (
    "怎么看", "怎么样", "基本面", "核心逻辑", "研究一下", "研究下",
    "全面研究", "完整研究", "完整更新", "更新档案", "公司档案", "完整档案", "财报", "年报",
    "季报", "半年报", "现金流", "产品结构",
    "位置", "暴露", "怎么赚钱", "利润", "估值",
)
_COMPANIES = (
    ("麦格米特", "002851"),
    ("中恒电气", "002364"),
    ("科泰电源", "300153"),
    ("中际旭创", "300308"),
    ("英伟达", "NVDA"),
    ("NVDA", "NVDA"),
)


def _load_md(name: str) -> dict:
    path = SKILL_DIR / name / "SKILL.md"
    text = path.read_text(encoding="utf-8")
    steps = [{"n": int(match.group(1)), "name": match.group(2).strip()} for match in _STEP.finditer(text)]
    return {
        "name": name,
        "path": str(path),
        "text": text,
        "steps": steps,
        "implemented": name in IMPLEMENTED_SKILLS,
    }


@lru_cache(maxsize=4)
def load(name: str = "industry-research") -> dict:
    return _load_md(name)


def reserved() -> tuple:
    return RESERVED_SKILLS


def implemented() -> tuple:
    return IMPLEMENTED_SKILLS


def _entities(text: str) -> list:
    found = []
    seen = set()
    for name, code in _COMPANIES:
        if code in seen:
            continue
        if name in text or code in text:
            found.append({"name": name, "code": code})
            seen.add(code)
    from core.research.entity_resolver import names_in
    for row in names_in(text):
        if row.get("code") in seen:
            continue
        found.append({"name": row.get("name") or "", "code": row.get("code") or ""})
        seen.add(row.get("code") or "")
    for match in _TICKER.findall(text):
        if match.isdigit() and match not in seen:
            found.append({"name": "", "code": match})
            seen.add(match)
    for match in re.findall(r"(?<!\d)(\d{6})(?!\d)", text):
        if match not in seen:
            found.append({"name": "", "code": match})
            seen.add(match)
    return found


def route(question: str, llm=None) -> dict:
    text = (question or "").strip()
    if not text:
        return _decision("", "UNKNOWN", 0, "EMPTY")
    entities = _entities(text)
    named = [row for row in entities if row.get("name")]
    from core.research.entity_resolver import comparison_target
    if len(named) >= 2 and not comparison_target(text):
        return _decision("", "UNKNOWN", 0.35, "NEEDS_CLARIFICATION")
    industry = any(token in text for token in _INDUSTRY)
    company_intent = any(token in text for token in _COMPANY_INTENT)
    if entities and (company_intent or not industry):
        return _decision("company-research", "COMPANY_RESEARCH", 0.9, "COMPANY_INTENT")
    if industry and not entities:
        return _decision("industry-research", "INDUSTRY_RESEARCH", 0.9, "INDUSTRY_INTENT")
    if industry and entities and company_intent:
        return _decision("company-research", "COMPANY_RESEARCH", 0.84, "COMPANY_IN_INDUSTRY")
    if industry and entities:
        if llm is None:
            return _decision("", "UNKNOWN", 0.4, "AMBIGUOUS")
        return _from_llm(llm, text)
    return _decision("", "UNKNOWN", 0.2, "NO_MATCH")


def select(question: str) -> str:
    return route(question).get("skill") or ""


def require(name: str) -> dict:
    if name not in IMPLEMENTED_SKILLS:
        raise KeyError("Skill 尚未实现：{0}".format(name))
    skill = load(name)
    if name == "industry-research" and len(skill["steps"]) != 13:
        raise KeyError("industry-research 应有 13 步，实际 {0}".format(len(skill["steps"])))
    if name == "company-research" and "Business Model" not in skill["text"]:
        raise KeyError("company-research 缺少 Business Model")
    return skill


def _decision(skill: str, intent: str, confidence: float, reason: str) -> dict:
    return {
        "skill": skill,
        "intent": intent,
        "confidence": confidence,
        "reason_code": reason,
    }


def _from_llm(llm, question: str) -> dict:
    raw = llm.generate_structured(
        "只输出 JSON：skill, confidence, reason_code。skill 只能是 industry-research 或 company-research。",
        question,
        {"type": "object"},
        temperature=0,
    )
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return _decision("", "UNKNOWN", 0, "ROUTER_PARSE_FAILED")
    skill = data.get("skill") or ""
    if skill not in ("industry-research", "company-research"):
        return _decision("", "UNKNOWN", 0, "ROUTER_PARSE_FAILED")
    return _decision(skill, "COMPANY_RESEARCH" if skill.startswith("company") else "INDUSTRY_RESEARCH", float(data.get("confidence") or 0), data.get("reason_code") or "LLM_ROUTER")
