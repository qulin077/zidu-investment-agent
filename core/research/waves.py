"""研究按波次走。计划一次，后面用调度器，不每步问模型。"""
from __future__ import annotations

WAVES = (
    "PLAN",
    "PRIMARY_EVIDENCE",
    "GAP_FILLING",
    "DISCONFIRMATION",
    "SYNTHESIS",
)


def schedule(max_waves: int = 4) -> list:
    cap = max(0, min(int(max_waves), 4))
    return [{"wave": index, "name": name} for index, name in enumerate(WAVES[: cap + 1])]
