"""远程正式写入的第二道门。夹具 PASS 不能打开这道门。"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from core.config import ROOT
from core.research.prompts import VERSIONS
from core.research.shadow_eval import score_thesis

GATE_VERSION = "rg1"
REPORT_PATH = ROOT / "evals" / "research" / "reports" / "research-remote-gate.json"
CASE_DIR = ROOT / "evals" / "research" / "remote_cases"
HARD_ZERO = (
    "fabricated_source",
    "unsupported_critical_fact",
    "wrong_evidence_link",
    "forecast_as_fact",
    "temporal_leakage",
    "stray_critical_number",
    "missing_critical_reference",
    "direct_exposure_overclaim",
)


def case_set_hash() -> str:
    digest = hashlib.sha256()
    paths = sorted(CASE_DIR.glob("*.json")) if CASE_DIR.is_dir() else []
    for path in paths:
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def load_report(path: Path | None = None) -> dict:
    target = path or REPORT_PATH
    if not target.is_file():
        return {}
    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def matches_runtime(path: Path | None = None) -> bool:
    report = load_report(path)
    return gate_matches(
        report,
        model=os.environ.get("LLM_MODEL") or os.environ.get("OPENAI_MODEL") or "",
        prompt_versions=VERSIONS,
        case_set_hash=case_set_hash(),
    )


def gate_matches(report: dict, *, model: str, prompt_versions: dict, case_set_hash: str) -> bool:
    if report.get("status") != "PASS" or report.get("gate_version") != GATE_VERSION:
        return False
    if not model or report.get("model") != model:
        return False
    if report.get("prompt_versions") != prompt_versions:
        return False
    if report.get("case_set_hash") != case_set_hash:
        return False
    metrics = report.get("metrics") or {}
    if any(int(metrics.get(key) or 0) != 0 for key in HARD_ZERO):
        return False
    if metrics.get("critical_evidence_grounding") != 1:
        return False
    return True


def score_regression(case: dict) -> dict:
    thesis = case.get("thesis") or {}
    scored = score_thesis(thesis, case.get("claims") or [])
    direct = list(scored.get("direct_without_gate") or [])
    return {
        "id": case.get("id") or "",
        "direct_exposure_overclaim": len(direct),
        "companies": direct,
        "caught": bool(direct),
    }


def regression_cases() -> list:
    if not CASE_DIR.is_dir():
        return []
    return [json.loads(path.read_text(encoding="utf-8")) for path in sorted(CASE_DIR.glob("*.json"))]
