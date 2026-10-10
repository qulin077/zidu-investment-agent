"""产品开关。统一从 config/review.yaml + 环境变量读取，页面只显示这里。"""
from __future__ import annotations

import json
import os
from typing import Optional

from core.config import ROOT
from core.review.defs import load


def _cfg() -> dict:
    return load() or {}


def _normalize_recorder_mode(raw: str) -> str:
    text = (raw or "").strip().lower()
    if text in ("shadow", "remote_shadow"):
        return "remote_shadow"
    if text in ("primary", "remote", "remote_primary"):
        return "remote_primary"
    if text in ("heuristic", "offline"):
        return "heuristic"
    return text or "heuristic"


def recorder_remote_mode() -> str:
    raw = (os.environ.get("RECORDER_REMOTE_MODE") or os.environ.get("RECORDER_MODE") or "").strip()
    if raw:
        return _normalize_recorder_mode(raw)
    rec = _cfg().get("recorder") or {}
    return _normalize_recorder_mode(str(rec.get("remote_mode") or "heuristic"))


def remote_primary_allowed() -> bool:
    rec = _cfg().get("recorder") or {}
    env = os.environ.get("RECORDER_REMOTE_PRIMARY")
    if env is not None:
        return env.lower() in ("1", "true", "yes")
    return bool(rec.get("remote_primary_allowed"))


def guided_review_enabled() -> bool:
    env = os.environ.get("GUIDED_REVIEW_ENABLED")
    if env is not None:
        return env.lower() in ("1", "true", "yes")
    block = _cfg().get("guided_review") or {}
    return bool(block.get("enabled"))


def has_remote_key() -> bool:
    return bool(os.environ.get("OPENAI_API_KEY") or os.environ.get("LLM_API_KEY"))


def _bool_env(name: str) -> Optional[bool]:
    env = os.environ.get(name)
    if env is None:
        return None
    return env.lower() in ("1", "true", "yes")


def memory_enabled() -> bool:
    env = _bool_env("MEMORY_ENABLED")
    if env is not None:
        return env
    block = _cfg().get("memory") or {}
    if "enabled" in block:
        return bool(block.get("enabled"))
    return True


def decision_context_enabled() -> bool:
    env = _bool_env("DECISION_CONTEXT_ENABLED")
    if env is not None:
        return env
    block = _cfg().get("decision_context") or {}
    if "enabled" in block:
        return bool(block.get("enabled"))
    return True


def pilot_mode() -> bool:
    env = _bool_env("PILOT_MODE")
    if env is not None:
        return env
    block = _cfg().get("pilot") or {}
    return bool(block.get("enabled"))


def current_environment() -> str:
    raw = (os.environ.get("SA_ENVIRONMENT") or "").strip().lower()
    if raw:
        return raw
    if os.environ.get("SA_DEMO") in ("1", "true", "yes"):
        return "test"
    return "prod"


def is_demo() -> bool:
    env = _bool_env("SA_DEMO")
    if env is not None:
        return env
    return current_environment() in ("test", "eval", "demo")


def research_enabled() -> bool:
    env = _bool_env("RESEARCH_ENABLED")
    if env is not None:
        return env
    block = _cfg().get("research") or {}
    if "enabled" in block:
        return bool(block.get("enabled"))
    return True


def research_remote_enabled() -> bool:
    env = _bool_env("RESEARCH_REMOTE_ENABLED")
    if env is not None:
        return env
    block = _cfg().get("research") or {}
    if "remote_enabled" in block:
        return bool(block.get("remote_enabled"))
    return False


def research_llm_mode() -> str:
    raw = (os.environ.get("RESEARCH_LLM_MODE") or "").strip()
    if raw in ("fixture", "remote_shadow", "remote_primary"):
        return raw
    block = _cfg().get("research") or {}
    cfg = str(block.get("llm_mode") or "fixture")
    if cfg in ("fixture", "remote_shadow", "remote_primary"):
        return cfg
    return "fixture"


def research_remote_primary_allowed() -> bool:
    """正式远程 Thesis 要开关、夹具门、远程门三者同时成立。夹具 PASS 只允许 shadow。"""
    env = _bool_env("RESEARCH_REMOTE_PRIMARY_ALLOWED")
    if env is None:
        block = _cfg().get("research") or {}
        env = bool(block.get("remote_primary_allowed", False))
    if not env:
        return False
    report = ROOT / "evals" / "research" / "reports" / "research-eval.json"
    if not report.is_file():
        return False
    try:
        data = json.loads(report.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if data.get("status") != "PASS" or data.get("model") != "fixture":
        return False
    from core.research.remote_gate import matches_runtime
    return matches_runtime()


def research_budget() -> dict:
    block = _cfg().get("research") or {}

    def _num(env_key: str, cfg_key: str, default: int) -> int:
        raw = os.environ.get(env_key)
        if raw is not None and str(raw).strip() != "":
            return int(raw)
        if cfg_key in block and block.get(cfg_key) is not None:
            return int(block.get(cfg_key))
        return default

    return {
        "max_iterations": _num("RESEARCH_MAX_ITERATIONS", "max_iterations", 8),
        "max_llm_calls": _num("RESEARCH_MAX_LLM_CALLS", "max_llm_calls", 20),
        "max_input_tokens": _num("RESEARCH_MAX_INPUT_TOKENS", "max_input_tokens", 200000),
        "max_output_tokens": _num("RESEARCH_MAX_OUTPUT_TOKENS", "max_output_tokens", 20000),
    }


def snapshot() -> dict:
    return {
        "RECORDER_REMOTE_MODE": recorder_remote_mode(),
        "remote_primary_allowed": remote_primary_allowed(),
        "GUIDED_REVIEW_ENABLED": guided_review_enabled(),
        "MEMORY_ENABLED": memory_enabled(),
        "DECISION_CONTEXT_ENABLED": decision_context_enabled(),
        "PILOT_MODE": pilot_mode(),
        "RESEARCH_ENABLED": research_enabled(),
        "RESEARCH_REMOTE_ENABLED": research_remote_enabled(),
        "RESEARCH_LLM_MODE": research_llm_mode(),
        "RESEARCH_REMOTE_PRIMARY_ALLOWED": research_remote_primary_allowed(),
        "environment": current_environment(),
        "demo": is_demo(),
    }
