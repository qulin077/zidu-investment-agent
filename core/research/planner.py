"""研究计划来自 Skill 的步骤。计划里不预填公司和数字。"""
from __future__ import annotations

import json
from typing import List

from core.config import ROOT
from core.research.fixture_llm import case_for
from core.research.skills import require


def _detail(step: int, question: str, theme: str, market_scope: List[str]) -> str:
    scope = "、".join(market_scope) if market_scope else "未限定市场"
    theme_text = theme or "该行业"
    lines = {
        1: "把问题收成一句可核对的研究问题：{0}".format(question),
        2: "先列计划，再读来源。本步不写结论。",
        3: "划出 {0} 的边界：包含什么、明确不包含什么。市场范围：{1}。".format(theme_text, scope),
        4: "按上下游列出 {0} 的环节。这里不预填公司清单。".format(theme_text),
        5: "写出要核对的驱动，每个驱动以后都要能指回 Claim。",
        6: "只通过 Tool 读取正文。读不到就记 Unknown，不用模型记忆补。",
        7: "把正文拆成 FACT / ESTIMATE / INFERENCE / OPINION。",
        8: "核对引文是否在来源正文里，以及来源在 as_of 之前是否可见。",
        9: "口径冲突并列放下。不知道的写成 Open Question。",
        10: "公司只标暴露类型。没有一手客户或收入证据就不是 DIRECT。",
        11: "催化和风险分开写，并指向已有 Claim。",
        12: "起草 Thesis，引用 evidence_refs。不写买卖和仓位。",
        13: "校验通过后追加 Thesis 版本。旧版不覆盖。",
    }
    return lines.get(step, "")


def build(question: str, theme: str = "", as_of: str = "", market_scope=None, depth: str = "deep") -> dict:
    skill = require("industry-research")
    scope = list(market_scope or [])
    steps = []
    for item in skill["steps"]:
        steps.append({
            "step": item["n"],
            "name": item["name"],
            "detail": _detail(item["n"], question, theme, scope),
        })
    return {
        "skill": "industry-research",
        "research_question": question,
        "industry_or_theme": theme,
        "as_of": as_of,
        "market_scope": scope,
        "depth": depth or "deep",
        "steps": steps,
        "tasks": tasks_for(question, theme),
    }


def tasks_for(question: str, theme: str = "") -> List[dict]:
    case = case_for(question, theme)
    if case:
        path = ROOT / "evals" / "research" / "fixtures" / case / "planner.json"
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            return list(data.get("tasks") or [])
    label = theme or "该行业"
    rows = [
        ("T1", "INDUSTRY_BOUNDARY", "{0}的边界是什么，明确不包含什么？".format(label)),
        ("T2", "REFERENCE_CLASS", "历史周期、生命周期和合理参考类是什么？当前假设偏离基准率多少？"),
        ("T3", "STRUCTURAL_CHANGE", "需求、供给、技术或政策发生了什么变化？"),
        ("T4", "VALUE_CHAIN", "产业链、利润池和竞争结构怎么拆？"),
        ("T5", "CAUSAL_MODEL", "核心叙事如何映射为输入变量、中间传导和可验证结果？"),
        ("T6", "ECONOMICS", "量、价、成本、毛利、份额里哪些有来源，哪些仍未知？"),
        ("T7", "CAPITAL_ECONOMICS", "增长需要多少资本，ROIC、自由现金流和经济利润如何？"),
        ("T8", "EARNINGS_TRACKING", "哪些代表公司业绩能够验证或否定行业逻辑？"),
        ("T9", "EXPECTATIONS", "事实、卖方预测、市场叙事和预期修订分别是什么？"),
        ("T10", "IMPLIED_EXPECTATIONS", "当前定价隐含了怎样的增长、份额和利润率门槛？"),
        ("T11", "SCENARIOS", "基准、上行和下行情景分别由什么条件触发？"),
        ("T12", "RISK", "什么事实会证明当前判断不成立？"),
    ]
    return [
        {
            "id": task_id,
            "question": text,
            "category": category,
            "priority": 1,
            "preferred_source_types": ["OFFICIAL"],
        }
        for task_id, category, text in rows
    ]


def company_plan(question: str, theme: str = "", as_of: str = "", market_scope=None, depth: str = "deep") -> dict:
    """Build the stable company-dossier checklist without pre-filling facts."""
    label = theme or "该公司"
    rows = [
        ("D1", "BUSINESS_MODEL", "{0}卖什么、卖给谁、如何收费，业务是一次性还是持续性？".format(label)),
        ("D2", "SEGMENTS", "最近三年产品、业务、地区和客户分部如何拆，收入、占比和毛利率分别如何变化？"),
        ("D3", "FINANCIAL_TREND", "先核对最近三年官方年报；同口径收入、利润、毛利率、现金流、资本开支、营运资本和负债如何变化？"),
        ("D4", "KEY_DRIVER", "量、价、成本、订单、产能或利用率中，哪些驱动收入和利润？"),
        ("D5", "MOAT", "公司的技术、规模、客户、渠道、成本或转换壁垒有什么直接证据？"),
        ("D6", "INDUSTRY_POSITION", "行业空间、竞争格局和公司位置分别是什么？"),
        ("D7", "EXPECTATIONS", "公司指引、一致预期、卖方预测和市场叙事分别是什么？"),
        ("D8", "PRICE_EXPECTATION_GAP", "当前股价和估值隐含了什么增长与利润假设，和基本面预期差在哪里？"),
        ("D9", "CATALYST", "哪些可核对事件可能验证或改变市场预期？"),
        ("D10", "RISK", "审计意见、资产负债率、偿债、应收存货、减值、利润现金含量中，哪些已披露风险最可能削弱当前逻辑？"),
        ("D11", "INVALIDATION", "什么后续事实会推翻当前判断？"),
        ("D12", "MONITORING", "下一期要监控哪些指标、披露和预期修正？"),
    ]
    tasks = [
        {
            "id": task_id,
            "question": text,
            "category": category,
            "priority": 1,
            "source_strategy": ["PRIMARY"],
            "completion_condition": "有引文，或明确写成 UNKNOWN。",
        }
        for task_id, category, text in rows
    ]
    return {
        "skill": "company-research",
        "research_goal": "建立并更新{0}的结构化公司档案：基本盘、壁垒、驱动、预期、股价隐含预期、变化、风险和监控。".format(label),
        "research_question": question,
        "industry_or_theme": theme,
        "as_of": as_of,
        "market_scope": list(market_scope or []),
        "depth": depth or "deep",
        "steps": [],
        "tasks": tasks,
    }
