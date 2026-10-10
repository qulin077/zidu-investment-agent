"""Unsupported Field Check：非空抽取必须能追到 raw_text 子串。"""
from __future__ import annotations

from typing import List, Tuple

from core.review.recorder.entailment import (
    CONTRADICTED,
    UNCERTAIN_V,
    EntailmentChecker,
)
from core.review.recorder.types import (
    Envelope,
    GroundingIssue,
    Quoted,
    RecorderDraft,
)

GROUNDING_FAILED = "GROUNDING_FAILED"
AGENT_INFERRED_BLOCKED = "AGENT_INFERRED"
MISSING_QUOTE = "MISSING_QUOTE"
QUOTE_NOT_IN_SOURCE = "QUOTE_NOT_IN_SOURCE"
FORBIDDEN_INFERENCE = "FORBIDDEN_INFERENCE"
SCOPE_CONTRADICTED = "SCOPE_CONTRADICTED"
NEEDS_CONFIRMATION = "NEEDS_CONFIRMATION"


def _contains(raw: str, quote: str) -> bool:
    if not quote:
        return False
    compact_raw = "".join(raw.split())
    compact_quote = "".join(quote.split())
    return quote in raw or compact_quote in compact_raw


def _check_quoted(field: str, item: Quoted, envelope: Envelope, issues: List[GroundingIssue]) -> None:
    if not item.filled():
        return
    prov = item.provenance or "USER_EXPLICIT"
    if prov == "AGENT_INFERRED":
        issues.append(GroundingIssue(field, AGENT_INFERRED_BLOCKED, "推断字段不得进入 Write Gate"))
        return
    if prov == "SYSTEM_CONTEXT":
        known = envelope.known_symbol or envelope.known_company
        if str(item.value) not in (envelope.known_symbol, envelope.known_company) and not (
            known and str(item.value) and known in str(item.value)
        ):
            if envelope.known_symbol and str(item.value) != envelope.known_symbol:
                issues.append(GroundingIssue(
                    field, GROUNDING_FAILED,
                    "SYSTEM_CONTEXT 与 envelope.known_symbol 不一致",
                ))
        return
    quote = (item.source_quote or "").strip()
    if not quote:
        issues.append(GroundingIssue(field, MISSING_QUOTE, "非空字段缺少 source_quote"))
        return
    if not _contains(envelope.raw_text, quote):
        issues.append(GroundingIssue(
            field, QUOTE_NOT_IN_SOURCE,
            "source_quote 不是 raw_text 的子串：{0!r}".format(quote[:40]),
        ))
        return
    verdict = EntailmentChecker().check(envelope.raw_text, field, item.value, quote)
    if verdict.verdict == CONTRADICTED:
        issues.append(GroundingIssue(field, SCOPE_CONTRADICTED, verdict.reason))
    elif verdict.verdict == UNCERTAIN_V:
        issues.append(GroundingIssue(field, NEEDS_CONFIRMATION, verdict.reason))


def check(draft: RecorderDraft, envelope: Envelope) -> Tuple[bool, List[GroundingIssue]]:
    issues: List[GroundingIssue] = []
    if draft.intent in ("CHITCHAT", "UNSUPPORTED"):
        return True, issues
    _check_quoted("symbol", draft.symbol, envelope, issues)
    _check_quoted("thesis", draft.thesis, envelope, issues)
    _check_quoted("market_context", draft.market_context, envelope, issues)
    _check_quoted("entry_rule", draft.plan.entry_rule, envelope, issues)
    _check_quoted("invalidation", draft.plan.invalidation, envelope, issues)
    _check_quoted("target_size_pct", draft.plan.target_size_pct, envelope, issues)
    _check_quoted("holding_period", draft.plan.holding_period, envelope, issues)
    for index, exp in enumerate(draft.expectations):
        fake = Quoted(value=exp.raw_text or None, source_quote=exp.source_quote, provenance=exp.provenance)
        _check_quoted("expectation[{0}]".format(index), fake, envelope, issues)
        if exp.raw_text and not exp.source_quote:
            issues.append(GroundingIssue("expectation[{0}]".format(index), MISSING_QUOTE, "expectation 缺 source_quote"))
    hard = [i for i in issues if i.code != NEEDS_CONFIRMATION]
    return (not hard), issues
