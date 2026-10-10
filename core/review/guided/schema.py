"""Guided Review JSON schema。agent_conclusion 在用户确认前必须为 null。"""
from __future__ import annotations

GUIDED_REVIEW_JSON_SCHEMA = {
    "name": "guided_review_turn",
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "decision_id": {"type": "string"},
            "fact_summary": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "statement": {"type": "string"},
                        "evidence_ref": {"type": "string"},
                    },
                    "required": ["statement", "evidence_ref"],
                },
            },
            "confirmed_violations": {"type": "array", "items": {"type": "string"}},
            "unresolved_dimension": {"type": "string"},
            "question": {"type": "string"},
            "options": {"type": "array"},
            "attribution_candidates": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string"},
                        "reason": {"type": "string"},
                        "evidence_refs": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["type", "reason", "evidence_refs"],
                },
            },
            "needs_user_input": {"type": "boolean"},
            "agent_conclusion": {},
            "recommend_trade": {"type": "boolean"},
        },
        "required": [
            "decision_id", "fact_summary", "unresolved_dimension",
            "question", "needs_user_input", "agent_conclusion",
        ],
    },
}
