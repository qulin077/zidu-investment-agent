"""技能是分析步骤，不是另一个 Agent。"""
from __future__ import annotations

from core.config import ROOT

_SKILL_DIR = ROOT / ".cursor" / "skills"

SKILLS = {
    "company-research": {
        "name": "company-research",
        "description": "按问题核对一家公司的业务、驱动、财务和未知。",
        "domain": "RESEARCH",
        "write_action": False,
        "required_context": ["question", "entity"],
        "allowed_tools": ["search", "reader", "pdf", "research_store", "market_data"],
        "runtime": "research",
        "skill_file": str(_SKILL_DIR / "company-research" / "SKILL.md"),
    },
    "industry-research": {
        "name": "industry-research",
        "description": "核对行业边界、价值链、传导和竞争。",
        "domain": "RESEARCH",
        "write_action": False,
        "required_context": ["question"],
        "allowed_tools": ["search", "reader", "pdf", "research_store"],
        "runtime": "research",
        "skill_file": str(_SKILL_DIR / "industry-research" / "SKILL.md"),
    },
    "event-impact": {
        "name": "event-impact",
        "description": "核对一件事改变了什么，以及传导到哪些环节。",
        "domain": "RESEARCH",
        "write_action": False,
        "required_context": ["question", "event"],
        "allowed_tools": ["search", "reader", "research_store"],
        "runtime": "research",
        "skill_file": str(_SKILL_DIR / "event-impact" / "SKILL.md"),
    },
    "candidate-discovery": {
        "name": "candidate-discovery",
        "description": "按暴露程度列出相关公司，不排序成荐股。",
        "domain": "RESEARCH",
        "write_action": False,
        "required_context": ["question"],
        "allowed_tools": ["search", "reader", "research_store"],
        "runtime": "candidates",
        "skill_file": str(_SKILL_DIR / "candidate-discovery" / "SKILL.md"),
    },
    "market-scan": {
        "name": "market-scan",
        "description": "用内部行情看市场强弱和板块，不先上网搜索。",
        "domain": "GENERAL",
        "write_action": False,
        "required_context": ["market_data"],
        "allowed_tools": ["market_data", "board", "sectors", "quotes"],
        "runtime": "market",
        "skill_file": str(_SKILL_DIR / "market-scan" / "SKILL.md"),
    },
    "security-snapshot": {
        "name": "security-snapshot",
        "description": "读取单只股票当前价格，并从前复权日线本地计算技术面。",
        "domain": "GENERAL",
        "write_action": False,
        "required_context": ["entity"],
        "allowed_tools": ["market_data", "quotes"],
        "runtime": "security_snapshot",
        "skill_file": str(_SKILL_DIR / "security-snapshot" / "SKILL.md"),
    },
    "portfolio-monitor": {
        "name": "portfolio-monitor",
        "description": "只看持仓里有没有实质性变化。",
        "domain": "GENERAL",
        "write_action": False,
        "required_context": ["positions"],
        "allowed_tools": ["positions", "quotes", "research_store", "market_data"],
        "runtime": "portfolio",
        "skill_file": str(_SKILL_DIR / "portfolio-monitor" / "SKILL.md"),
    },
    "decision-recorder": {
        "name": "decision-recorder",
        "description": "把一笔打算记进 Decision，确认后才写入。",
        "domain": "DECISION",
        "write_action": True,
        "required_context": ["decision_store"],
        "allowed_tools": ["decision_store"],
        "runtime": "recorder",
        "skill_file": str(_SKILL_DIR / "decision-recorder" / "SKILL.md"),
    },
    "guided-review": {
        "name": "guided-review",
        "description": "对照当时的 Thesis 和现在的 Thesis，不自动写成研究错误。",
        "domain": "REVIEW",
        "write_action": False,
        "required_context": ["decision"],
        "allowed_tools": ["decision_store", "research_store"],
        "runtime": "review",
        "skill_file": str(_SKILL_DIR / "guided-review" / "SKILL.md"),
    },
    "memory-query": {
        "name": "memory-query",
        "description": "查已经确认的 Pattern 和 Rule。",
        "domain": "GENERAL",
        "write_action": False,
        "required_context": ["patterns", "rules"],
        "allowed_tools": ["decision_store"],
        "runtime": "memory",
        "skill_file": str(_SKILL_DIR / "memory-query" / "SKILL.md"),
    },
}


def get(name: str) -> dict:
    return dict(SKILLS.get(name) or {})


def names() -> tuple:
    return tuple(SKILLS)


def allows(skill: str, tool: str) -> bool:
    row = SKILLS.get(skill) or {}
    return tool in (row.get("allowed_tools") or [])
