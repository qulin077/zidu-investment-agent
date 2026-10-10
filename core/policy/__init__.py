"""哨兵的薄接口。不替换 Write Gate、Remote Gate、Temporal Gate。"""
from core.policy.decision import ALLOW, ASK_USER, DENY, decide
from core.policy.tools import TOOLS

__all__ = ["ALLOW", "ASK_USER", "DENY", "TOOLS", "decide"]
