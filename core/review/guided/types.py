"""Guided Review 类型与 prompt 版本。"""
from __future__ import annotations

PROMPT_VERSION = "gr1"
SCHEMA_VERSION = "gs1"

UNRESOLVED = (
    "OUTCOME",
    "VIOLATIONS",
    "ATTRIBUTION",
    "LESSON",
)

ERROR_TYPES = (
    "NONE",
    "RESEARCH_ERROR",
    "EXPECTATION_ERROR",
    "TIMING_ERROR",
    "SIZING_ERROR",
    "EXECUTION_ERROR",
    "RISK_CONTROL_ERROR",
    "EMOTION_ERROR",
    "PROCESS_ERROR",
    "EXTERNAL_SHOCK",
)

QUADRANTS = {
    ("followed", "profit"): "纪律合格盈利",
    ("followed", "loss"): "纪律合格亏损",
    ("violated", "profit"): "纪律违规盈利",
    ("violated", "loss"): "纪律违规亏损",
    ("followed", "flat"): "纪律合格平手",
    ("violated", "flat"): "纪律违规平手",
}
