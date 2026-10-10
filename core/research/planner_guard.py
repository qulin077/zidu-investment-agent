"""计划里不能出现结论、收入数字或推荐。"""
from __future__ import annotations

import re

_LEAK = ("一定受益", "推荐", "目标价", "仓位", "建议买入", "建议卖出", "市场规模")
_REVENUE = re.compile(r"收入\s*\d")


def leakage(plan: dict) -> list:
    blob = " ".join(_texts(plan))
    found = [token for token in _LEAK if token in blob]
    if _REVENUE.search(blob):
        found.append("收入数字")
    return found


def _texts(plan: dict) -> list:
    rows = [plan.get("research_goal") or ""]
    for task in plan.get("tasks") or []:
        if isinstance(task, dict):
            rows.append(task.get("question") or "")
            rows.append(task.get("completion_condition") or "")
        elif isinstance(task, str):
            rows.append(task)
    return rows
