"""Recorder 字段契约。模型输出必须能落到这些类型上。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

INTENTS = ("CREATE_DECISION", "UPDATE_DRAFT", "CHITCHAT", "UNSUPPORTED")
PROVENANCES = (
    "USER_EXPLICIT",
    "NORMALIZED_FROM_USER",
    "SYSTEM_CONTEXT",
    "AGENT_INFERRED",
)
DRAFT_STATUSES = (
    "PARSED",
    "VALIDATED",
    "NEEDS_EDIT",
    "CONFIRMED",
    "REJECTED",
    "FAILED",
)
CRITICAL_FIELDS = (
    "symbol",
    "thesis",
    "expectation",
    "entry_rule",
    "invalidation",
    "target_size",
    "holding_period",
)
FORBIDDEN_KEYS = ("stop_price", "target_price", "earning_type", "error_type")
PROMPT_VERSION = "r1"
SCHEMA_VERSION = "s1"


@dataclass
class Quoted:
    value: Any = None
    source_quote: Optional[str] = None
    provenance: str = "USER_EXPLICIT"

    def filled(self) -> bool:
        if self.value is None:
            return False
        if isinstance(self.value, str) and not self.value.strip():
            return False
        return True

    def as_dict(self) -> Dict[str, Any]:
        return {
            "value": self.value,
            "source_quote": self.source_quote,
            "provenance": self.provenance,
        }

    @classmethod
    def from_dict(cls, raw: Any) -> "Quoted":
        if raw is None:
            return cls()
        if not isinstance(raw, dict):
            return cls(value=raw)
        return cls(
            value=raw.get("value"),
            source_quote=raw.get("source_quote"),
            provenance=raw.get("provenance") or "USER_EXPLICIT",
        )


@dataclass
class ExpectationDraft:
    raw_text: str = ""
    source_quote: str = ""
    window: Optional[str] = None
    confidence: Optional[int] = None
    provenance: str = "USER_EXPLICIT"

    def as_dict(self) -> Dict[str, Any]:
        return {
            "raw_text": self.raw_text,
            "source_quote": self.source_quote,
            "window": self.window,
            "confidence": self.confidence,
            "provenance": self.provenance,
        }

    @classmethod
    def from_dict(cls, raw: Any) -> "ExpectationDraft":
        data = raw if isinstance(raw, dict) else {}
        return cls(
            raw_text=str(data.get("raw_text") or ""),
            source_quote=str(data.get("source_quote") or ""),
            window=data.get("window"),
            confidence=data.get("confidence"),
            provenance=data.get("provenance") or "USER_EXPLICIT",
        )


@dataclass
class PlanDraft:
    entry_rule: Quoted = field(default_factory=Quoted)
    invalidation: Quoted = field(default_factory=Quoted)
    target_size_pct: Quoted = field(default_factory=Quoted)
    holding_period: Quoted = field(default_factory=Quoted)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "entry_rule": self.entry_rule.as_dict(),
            "invalidation": self.invalidation.as_dict(),
            "target_size_pct": self.target_size_pct.as_dict(),
            "holding_period": self.holding_period.as_dict(),
        }

    @classmethod
    def from_dict(cls, raw: Any) -> "PlanDraft":
        data = raw if isinstance(raw, dict) else {}
        return cls(
            entry_rule=Quoted.from_dict(data.get("entry_rule")),
            invalidation=Quoted.from_dict(data.get("invalidation")),
            target_size_pct=Quoted.from_dict(data.get("target_size_pct")),
            holding_period=Quoted.from_dict(data.get("holding_period")),
        )


@dataclass
class Envelope:
    raw_text: str
    recorded_at: str = ""
    source: str = "web"
    mode: str = "premarket"
    known_symbol: str = ""
    known_company: str = ""
    account: str = ""
    draft_id: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "raw_text": self.raw_text,
            "recorded_at": self.recorded_at,
            "source": self.source,
            "mode": self.mode,
            "known_symbol": self.known_symbol,
            "known_company": self.known_company,
            "account": self.account,
            "draft_id": self.draft_id,
        }


@dataclass
class RecorderDraft:
    intent: str = "CREATE_DECISION"
    symbol: Quoted = field(default_factory=Quoted)
    thesis: Quoted = field(default_factory=Quoted)
    market_context: Quoted = field(default_factory=Quoted)
    expectations: List[ExpectationDraft] = field(default_factory=list)
    plan: PlanDraft = field(default_factory=PlanDraft)
    missing_fields: List[str] = field(default_factory=list)
    ambiguities: List[str] = field(default_factory=list)
    unsupported_fields: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "intent": self.intent,
            "symbol": self.symbol.as_dict(),
            "thesis": self.thesis.as_dict(),
            "market_context": self.market_context.as_dict(),
            "expectations": [e.as_dict() for e in self.expectations],
            "plan": self.plan.as_dict(),
            "missing_fields": list(self.missing_fields),
            "ambiguities": list(self.ambiguities),
            "unsupported_fields": list(self.unsupported_fields),
        }

    @classmethod
    def from_dict(cls, raw: Any) -> "RecorderDraft":
        data = raw if isinstance(raw, dict) else {}
        expects = data.get("expectations") or []
        if isinstance(expects, dict):
            expects = [expects]
        return cls(
            intent=str(data.get("intent") or "CREATE_DECISION"),
            symbol=Quoted.from_dict(data.get("symbol")),
            thesis=Quoted.from_dict(data.get("thesis")),
            market_context=Quoted.from_dict(data.get("market_context")),
            expectations=[ExpectationDraft.from_dict(item) for item in expects],
            plan=PlanDraft.from_dict(data.get("plan")),
            missing_fields=list(data.get("missing_fields") or []),
            ambiguities=list(data.get("ambiguities") or []),
            unsupported_fields=list(data.get("unsupported_fields") or []),
        )


@dataclass
class GroundingIssue:
    field: str
    code: str
    detail: str

    def as_dict(self) -> Dict[str, Any]:
        return {"field": self.field, "code": self.code, "detail": self.detail}
