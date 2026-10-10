"""运行时模型。没有密钥就返回空，不发起请求。"""
from __future__ import annotations

import os

from core.agent.harness import AgentRuntime, MAX_AGENT_STEPS, get_turn, list_turns
from core.research.env import load_local_env

RUNTIME_VERSION = "harness2-model-loop"


def runtime_llm():
    load_local_env()
    if not (os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")):
        return None
    from core.llm.client import OpenAICompatibleClient
    return OpenAICompatibleClient()


def health() -> dict:
    load_local_env()
    configured = bool(os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY"))
    model = os.environ.get("LLM_MODEL") or "gpt-4o-mini"
    search = "Unavailable"
    try:
        import ddgs  # noqa: F401
        search = "DDGS Ready"
    except Exception:
        search = "Unavailable"
    try:
        from core.market_data.ifind import IfindConfig
        ifind = "Configured" if IfindConfig.from_environment() else "Unavailable"
    except Exception:
        ifind = "Unavailable"
    return {
        # 首页读取不能每次都产生一次付费请求。configured 只表示配置存在，
        # 不能再冒充已经完成了远端连通性探测。
        "llm_connected": False,
        "llm_configured": configured,
        "llm_status": "configured_not_probed" if configured else "not_configured",
        "provider": "OpenAI Compatible",
        "model": model if configured else "",
        "search": "DDGS Installed" if search == "DDGS Ready" else search,
        "ifind": ifind,
        "runtime": RUNTIME_VERSION,
        "max_steps": MAX_AGENT_STEPS,
        "planning_mode": "model-loop",
    }


__all__ = [
    "AgentRuntime", "MAX_AGENT_STEPS", "RUNTIME_VERSION", "runtime_llm", "health",
    "get_turn", "list_turns",
]
