"""AI 电源夹具。正文来自仓库笔记，引文对不上就拒绝跑。"""
from __future__ import annotations

from core.research.fixture_llm import load_case


def packet(as_of: str = "2026-09-26T23:59:59+08:00") -> dict:
    return load_case("ai_power", as_of)
