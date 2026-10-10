"""业务规则校验。Grounding 通过之后再看缺字段、模糊仓位、能否 PLANNED。"""
from __future__ import annotations

from typing import List, Tuple

from core.review.recorder.types import RecorderDraft

FUZZY_SIZE = ("一点", "一些", "看看", "少量", "随便")


def _filled_plan(draft: RecorderDraft) -> dict:
    return {
        "entry_rule": draft.plan.entry_rule.filled(),
        "invalidation": draft.plan.invalidation.filled(),
        "target_size": draft.plan.target_size_pct.filled(),
        "holding_period": draft.plan.holding_period.filled(),
    }


def refresh_missing(draft: RecorderDraft, raw_text: str) -> RecorderDraft:
    """按抽取结果重算 missing / ambiguities，不让模型自己报平安。"""
    missing = []
    if draft.intent in ("CHITCHAT", "UNSUPPORTED"):
        draft.missing_fields = []
        return draft
    if not draft.symbol.filled():
        missing.append("symbol")
    if not draft.thesis.filled():
        missing.append("thesis")
    if not draft.expectations:
        missing.append("expectation")
    plan = _filled_plan(draft)
    for key, ok in plan.items():
        if not ok:
            missing.append(key)
    draft.missing_fields = missing

    ambiguities = list(draft.ambiguities)
    if any(word in raw_text for word in ("修复", "可能", "感觉")) and "验证口径" not in " ".join(ambiguities):
        if "修复" in raw_text or "可能" in raw_text:
            ambiguities.append("市场判断尚未定义验证口径")
    if any(word in raw_text for word in FUZZY_SIZE) and not draft.plan.target_size_pct.filled():
        if "仓位表达模糊，不能量化" not in ambiguities:
            ambiguities.append("仓位表达模糊，不能量化")
    if "和" in raw_text and draft.symbol.filled():
        # 多标的提示由 heuristic 写入；这里不重复发明
        pass
    seen = []
    for item in ambiguities:
        if item not in seen:
            seen.append(item)
    draft.ambiguities = seen
    return draft


def can_plan(draft: RecorderDraft) -> Tuple[bool, List[str]]:
    """能否升到 PLANNED：thesis + expectation + plan.invalidation。仓位/持有期可缺。"""
    missing = []
    if not draft.thesis.filled():
        missing.append("thesis")
    if not draft.expectations:
        missing.append("expectation")
    if not draft.plan.invalidation.filled():
        missing.append("invalidation")
    if not draft.plan.entry_rule.filled():
        missing.append("entry_rule")
    if not draft.symbol.filled():
        missing.append("symbol")
    return (not missing), missing
