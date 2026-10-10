"""Grounding V2：确定性语义护栏 + 可选 EntailmentChecker。

Layer 1 不调模型。CONTRADICTED 直接失败；UNCERTAIN 需要人确认。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

NEGATION = ("不是说", "没说", "不代表", "没有打算", "不是我要买", "不是我要做", "不是跌破")
RETRACTION = ("算了", "刚才那句不要", "改成")
HISTORICAL = ("上次", "以前", "之前那次")
HYPOTHETICAL = ("假如", "如果是短线", "还没决定", "还没想好")
UNCERTAIN = ("好像", "应该也是", "可能是", "记不清", "大概是")
OBSERVATION = ("观察位", "观察")

ENTAILED = "ENTAILED"
CONTRADICTED = "CONTRADICTED"
UNCERTAIN_V = "UNCERTAIN"


def _clause_of(raw: str, quote: str) -> str:
    if not quote:
        return ""
    idx = raw.find(quote)
    if idx < 0:
        compact_raw = "".join(raw.split())
        compact_quote = "".join(quote.split())
        idx = compact_raw.find(compact_quote)
        if idx < 0:
            return quote
        return compact_raw
    start = raw.rfind("。", 0, idx)
    start = max(start, raw.rfind("，", 0, idx), raw.rfind(",", 0, idx), raw.rfind("；", 0, idx))
    end = len(raw)
    for mark in ("。", "，", ",", "；", "！", "？"):
        pos = raw.find(mark, idx + len(quote))
        if pos >= 0:
            end = min(end, pos)
    left = 0 if start < 0 else start + 1
    return raw[left:end]


def classify_scope(raw_text: str, source_quote: str, field: str = "") -> str:
    """返回 ENTAILED / CONTRADICTED / UNCERTAIN。"""
    raw = raw_text or ""
    quote = source_quote or ""
    window = _clause_of(raw, quote) or quote
    plan_fields = {
        "invalidation", "entry_rule", "target_size_pct", "holding_period",
        "symbol", "expectation",
    }
    critical = field.split("[")[0].replace("plan.", "") in plan_fields or field in plan_fields

    if any(k in window for k in NEGATION):
        if critical:
            return CONTRADICTED
    if window.startswith("不是") and any(k in window for k in ("跌破", "卖", "止损")):
        if critical:
            return CONTRADICTED
    if "观察位" in window and field in ("invalidation", "plan.invalidation"):
        if "才算" not in window and "失效" not in window:
            return CONTRADICTED
    if any(k in window for k in ("还没想好", "还没决定", "还没定", "先不说")):
        if field in ("invalidation", "holding_period", "target_size_pct"):
            return CONTRADICTED
    if any(k in window for k in HISTORICAL) and any(k in raw for k in ("这次", "还没想好", "还没决定")):
        if field in ("invalidation", "holding_period", "target_size_pct"):
            return CONTRADICTED
    if any(k in window for k in ("如果是", "假如")) and any(k in raw for k in ("还没决定", "还没想好", "没决定做")):
        if field in ("invalidation", "holding_period", "entry_rule", "target_size_pct"):
            return CONTRADICTED
    if any(k in window for k in UNCERTAIN) and field in ("thesis", "expectation"):
        return UNCERTAIN_V
    if any(k in window for k in RETRACTION) and "改成" not in window:
        return CONTRADICTED
    return ENTAILED


@dataclass
class EntailmentResult:
    verdict: str
    reason: str = ""


class EntailmentChecker:
    """默认确定性实现。远程 checker 可选，失败时退回 deterministic。"""

    name = "deterministic-v1"

    def check(self, raw_text: str, field: str, value, source_quote: Optional[str]) -> EntailmentResult:
        verdict = classify_scope(raw_text, source_quote or "", field)
        reason = ""
        if verdict == CONTRADICTED:
            reason = "source_quote 落在否定/撤回/历史/假设范围内，不能作为当前正式 Plan"
        elif verdict == UNCERTAIN_V:
            reason = "原文是不确定回忆，不能标成 USER_EXPLICIT"
        return EntailmentResult(verdict=verdict, reason=reason)
