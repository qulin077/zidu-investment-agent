"""Recorder JSON Schema。给 LLM structured output 和解析器共用。"""
from __future__ import annotations

from core.review.recorder.types import SCHEMA_VERSION

QUOTED = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "value": {},
        "source_quote": {"type": ["string", "null"]},
        "provenance": {
            "type": "string",
            "enum": [
                "USER_EXPLICIT",
                "NORMALIZED_FROM_USER",
                "SYSTEM_CONTEXT",
                "AGENT_INFERRED",
            ],
        },
    },
    "required": ["value", "source_quote"],
}

RECORDER_JSON_SCHEMA = {
    "name": "recorder_draft",
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "intent": {
                "type": "string",
                "enum": ["CREATE_DECISION", "UPDATE_DRAFT", "CHITCHAT", "UNSUPPORTED"],
            },
            "symbol": QUOTED,
            "thesis": QUOTED,
            "market_context": QUOTED,
            "expectations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "raw_text": {"type": "string"},
                        "source_quote": {"type": "string"},
                        "window": {"type": ["string", "null"]},
                        "confidence": {"type": ["integer", "null"]},
                        "provenance": {"type": "string"},
                    },
                    "required": ["raw_text", "source_quote"],
                },
            },
            "plan": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "entry_rule": QUOTED,
                    "invalidation": QUOTED,
                    "target_size_pct": QUOTED,
                    "holding_period": QUOTED,
                },
            },
            "missing_fields": {"type": "array", "items": {"type": "string"}},
            "ambiguities": {"type": "array", "items": {"type": "string"}},
            "unsupported_fields": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["intent", "missing_fields"],
    },
    "version": SCHEMA_VERSION,
}


def empty_quoted() -> dict:
    return {"value": None, "source_quote": None, "provenance": "USER_EXPLICIT"}
