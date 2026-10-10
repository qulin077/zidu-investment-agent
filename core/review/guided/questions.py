"""一次只问一个未决判断。候选不等于归因写入。"""
from __future__ import annotations

from typing import Any, Dict, List

from core.review.guided.types import PROMPT_VERSION


def next_unresolved(facts: Dict[str, Any]) -> str:
    if not facts.get("outcome_confirmed"):
        return "OUTCOME"
    if not facts.get("violations_confirmed"):
        return "VIOLATIONS"
    if not facts.get("attribution_confirmed"):
        return "ATTRIBUTION"
    if not (facts.get("lesson") or "").strip():
        return "LESSON"
    return ""


def _refs(*keys: str) -> List[str]:
    return list(keys)


def build_turn(facts: Dict[str, Any], unresolved: str = "") -> Dict[str, Any]:
    unresolved = unresolved or next_unresolved(facts)
    summary = list(facts.get("fact_summary") or [])
    codes = list(facts.get("violation_codes") or [])
    plan_size = facts.get("plan", {}).get("target_size_pct")
    actual = facts.get("actual", {}).get("max_size_pct")
    question = ""
    options: List[Dict[str, str]] = []
    candidates: List[Dict[str, Any]] = []

    if unresolved == "OUTCOME":
        coverage = facts.get("quote_coverage") or "none"
        extra = ""
        if coverage != "full":
            extra = " 行情覆盖是 {0}，MFE/MAE 不能当完整事实。".format(coverage)
        question = "这条 Outcome 是否确认？实现盈亏见事实卡。{0}".format(extra).strip()
        options = [
            {"id": "YES", "label": "确认，结果记录无误"},
            {"id": "NO", "label": "有误，先不进入归因"},
        ]
    elif unresolved == "VIOLATIONS":
        if codes:
            question = (
                "以下是系统算出的 process violation（事实，不是原因）：{0}。"
                "请确认这些违规记录是否属实。"
            ).format("、".join(codes))
        else:
            question = "系统未发现 process violation。请确认：这次按计划执行，没有流程违规。"
        options = [
            {"id": "YES", "label": "确认"},
            {"id": "NO", "label": "有误"},
        ]
    elif unresolved == "LESSON":
        question = "下次遇到类似情况要注意什么？只写纪律/过程提醒，不要写明天买什么。"
        options = []
    else:
        # ATTRIBUTION
        if "SIZE_EXCEEDED" in codes:
            question = (
                "系统已知：你计划 {0}%，实际 {1}%，因此 SIZE_EXCEEDED 是事实。"
                "现在只需确认：你认为这次超仓主要是："
            ).format(plan_size, actual)
            options = [
                {"id": "A", "label": "原计划本身低估所需仓位"},
                {"id": "B", "label": "临盘追加"},
                {"id": "C", "label": "害怕踏空"},
                {"id": "D", "label": "其它"},
            ]
            candidates = [
                {
                    "type": "SIZING_ERROR",
                    "reason": "计划仓位与实际仓位不一致",
                    "evidence_refs": _refs("plan.target_size", "actual.size", "violation.SIZE_EXCEEDED"),
                },
                {
                    "type": "EXECUTION_ERROR",
                    "reason": "可能是临盘追加，而不是计划写错",
                    "evidence_refs": _refs("plan.target_size", "actual.size", "violation.SIZE_EXCEEDED"),
                },
            ]
        elif "NO_PLAN" in codes:
            question = (
                "事实是没有事前计划（NO_PLAN）。这还不是归因。"
                "你认为这次主要应记为："
            )
            options = [
                {"id": "A", "label": "流程缺失（没做计划）"},
                {"id": "B", "label": "事后才想起当时的想法"},
                {"id": "C", "label": "外部冲击，计划本来也难写"},
                {"id": "D", "label": "其它"},
            ]
            candidates = [
                {
                    "type": "PROCESS_ERROR",
                    "reason": "无事前计划是事实，是否记 PROCESS_ERROR 需你确认",
                    "evidence_refs": _refs("violation.NO_PLAN"),
                },
            ]
        elif facts.get("research_vs_expectation") and facts.get("pnl_sign") == "loss":
            question = (
                "产业判断本身没有被当前证据自动推翻，但价格预期未兑现。"
                "你认为主要问题更接近："
            )
            options = [
                {"id": "A", "label": "产业判断本身有误"},
                {"id": "B", "label": "从产业逻辑推导到短期价格时出了问题"},
                {"id": "C", "label": "时间窗口设置过短"},
                {"id": "D", "label": "其它"},
            ]
            candidates = [
                {
                    "type": "RESEARCH_ERROR",
                    "reason": "若产业判断本身错了",
                    "evidence_refs": _refs("decision.thesis"),
                },
                {
                    "type": "EXPECTATION_ERROR",
                    "reason": "若产业没错但价格预期错了",
                    "evidence_refs": _refs("decision.thesis"),
                },
                {
                    "type": "TIMING_ERROR",
                    "reason": "若方向对但窗口太短",
                    "evidence_refs": _refs("decision.thesis"),
                },
            ]
        elif facts.get("process_followed") and facts.get("pnl_sign") == "loss":
            question = (
                "计划完整且未见 process violation，结果是亏损。"
                "亏损不等于决策错误。你认为这次结果和预期不一致，主要更接近："
            )
            options = [
                {"id": "A", "label": "噪声范围内，记 NONE"},
                {"id": "B", "label": "预期推导有误"},
                {"id": "C", "label": "时间窗口错了"},
                {"id": "D", "label": "外部冲击"},
                {"id": "E", "label": "其它"},
            ]
            candidates = [
                {"type": "NONE", "reason": "按计划执行的亏损可以不是错误", "evidence_refs": _refs("outcome.realized_pct")},
                {"type": "EXPECTATION_ERROR", "reason": "价格预期可能错了", "evidence_refs": _refs("outcome.realized_pct")},
                {"type": "EXTERNAL_SHOCK", "reason": "若有不可合理预见事件，需你确认", "evidence_refs": _refs("outcome.realized_pct")},
            ]
        elif facts.get("process_violated") and facts.get("pnl_sign") == "profit":
            question = (
                "这笔交易盈利，但 process violation 仍在（{0}）。"
                "盈利不等于好决策。你认为这次违规主要为什么发生？"
            ).format("、".join(codes) or "见事实卡")
            options = [
                {"id": "A", "label": "执行偏离计划"},
                {"id": "B", "label": "计划本身不完整"},
                {"id": "C", "label": "其它"},
            ]
            candidates = [
                {
                    "type": "EXECUTION_ERROR",
                    "reason": "违规是事实，原因待你确认",
                    "evidence_refs": _refs(*["violation.{0}".format(c) for c in codes[:3]]),
                },
                {
                    "type": "PROCESS_ERROR",
                    "reason": "也可能是流程本身有缺口",
                    "evidence_refs": _refs(*["violation.{0}".format(c) for c in codes[:3]]),
                },
            ]
        else:
            question = (
                "有几种可能的原因，系统不能替你选。"
                "你认为这次结果和预期不一致，主要更接近哪一类？"
            )
            options = [
                {"id": "A", "label": "执行问题"},
                {"id": "B", "label": "预期问题"},
                {"id": "C", "label": "外部冲击"},
                {"id": "D", "label": "其它 / 暂时不判断"},
            ]
            candidates = [
                {"type": "EXECUTION_ERROR", "reason": "候选，需你确认", "evidence_refs": _refs("execution.first")},
                {"type": "EXPECTATION_ERROR", "reason": "候选，需你确认", "evidence_refs": _refs("decision.thesis")},
                {"type": "EXTERNAL_SHOCK", "reason": "候选，需你确认", "evidence_refs": _refs("outcome.realized_pct")},
            ]

        if facts.get("emotion_self_report"):
            candidates.append({
                "type": "EMOTION_ERROR",
                "reason": "你此前自述过情绪，是否记入需确认",
                "evidence_refs": _refs("decision.thesis"),
            })

    return {
        "decision_id": facts.get("decision_id") or "",
        "fact_summary": summary,
        "confirmed_violations": codes if facts.get("violations_confirmed") else [],
        "unresolved_dimension": unresolved,
        "question": question,
        "options": options,
        "attribution_candidates": candidates,
        "needs_user_input": True,
        "agent_conclusion": None,
        "prompt_version": PROMPT_VERSION,
        "quadrant": facts.get("quadrant"),
        "counterfactual": facts.get("counterfactual"),
        "recommend_trade": False,
    }
