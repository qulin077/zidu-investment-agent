"""窄任务：Pattern Summarizer + Rule Candidate Wording。默认确定性模板，不调第二模型。"""
from __future__ import annotations

from typing import Any, Dict, List

from core.review.memory.fingerprint import loads_list
from core.review.memory.types import RULE_WORDING_VERSION, SUMMARIZER_VERSION
from core.review.memory.validator import personality_hits


def summarize(mistakes: List[Dict[str, Any]]) -> Dict[str, Any]:
    n = len(mistakes)
    errors = sorted({m.get("primary_error") or "" for m in mistakes if m.get("primary_error")})
    codes = []
    for m in mistakes:
        codes.extend(loads_list(m.get("violation_codes")))
    code_set = sorted(set(codes))
    emotions = sorted({m.get("emotion_tag") or "" for m in mistakes if m.get("emotion_tag")})
    contexts = []
    for m in mistakes:
        contexts.extend(loads_list(m.get("market_context_tags")))
    ctx = sorted(set(contexts))
    fomo_n = sum(1 for m in mistakes if m.get("emotion_tag") == "FOMO")
    size_n = sum(1 for m in mistakes if "SIZE_EXCEEDED" in loads_list(m.get("violation_codes")))
    parts = ["过去 {0} 条已确认 Decision 中".format(n)]
    if size_n:
        parts.append("有 {0} 条出现超计划仓位".format(size_n))
    if fomo_n:
        parts.append("有 {0} 条明确自述怕踏空/FOMO".format(fomo_n))
    if ctx:
        parts.append("场景标签：{0}".format("、".join(ctx)))
    summary = "，".join(parts) + "。"
    trigger = "、".join(ctx or emotions) or "（实例未写共同场景，保留各条 context）"
    behavior = "、".join(code_set or errors) or "行为待用户确认"
    for blob in (summary, trigger, behavior):
        if personality_hits(blob):
            summary = "过去 {0} 条已确认 Decision 存在可核对的重复结构。".format(n)
            trigger = "见各条 Decision 证据"
            behavior = "见 violation / attribution"
            break
    return {
        "pattern_summary": summary,
        "common_trigger": trigger,
        "common_behavior": behavior,
        "model": "memory-heuristic-ps1",
        "prompt_version": SUMMARIZER_VERSION,
        "n": n,
        "errors": errors,
        "violation_codes": code_set,
        "context_differences": ctx,
    }


def rule_candidates(pattern: Dict[str, Any], mistakes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    key = pattern.get("pattern_key") or ""
    evidence = [m.get("decision_id") for m in mistakes if m.get("decision_id")]
    has_size = "SIZE_EXCEEDED" in key
    has_fomo = "FOMO" in key
    out: List[Dict[str, Any]] = []
    if has_size:
        out.append({
            "rule_text": "若已有事前 target_size，则盘中不得因为怕踏空提高仓位上限。",
            "trigger_text": "已有事前 target_size",
            "expected_behavior": "盘中不得因为怕踏空提高仓位上限",
        })
        out.append({
            "rule_text": "出现 SIZE_EXCEEDED 后，下一次同类 Decision 必须在下单前确认 target_size。",
            "trigger_text": "准备下单且存在已确认的超仓模式",
            "expected_behavior": "下单前确认 target_size，不自动改仓位",
        })
    if has_fomo and not has_size:
        out.append({
            "rule_text": "若用户自述怕踏空，则必须先确认计划仓位，才能继续创建 Decision。",
            "trigger_text": "用户自述怕踏空 / FOMO",
            "expected_behavior": "先确认计划仓位，不自动改数字",
        })
    if not out:
        error = (pattern.get("pattern_key") or "").split("|")[0] or "已确认错误"
        out.append({
            "rule_text": "若再次出现已确认的 {0}，则下单前必须打开对应历史 Decision 证据。".format(error),
            "trigger_text": "新 Decision 命中已确认模式 {0}".format(error),
            "expected_behavior": "打开历史证据并确认，不自动改计划",
        })
    for item in out[:3]:
        item["evidence_decision_ids"] = evidence
        item["prompt_version"] = RULE_WORDING_VERSION
        item["proposed_by"] = "system"
    return out[:3]
