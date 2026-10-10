"""Policy 接口。底下仍是原来的 Remote Gate 和写门，这里只统一出口。

网页、PDF、用户粘贴的文字都不是政策输入。它们改不了 ALLOW / DENY。
"""
from __future__ import annotations

from core.policy.tools import FORBIDDEN, TOOLS, USER_CONFIRM
from core.review.flags import research_remote_primary_allowed

ALLOW = "ALLOW"
DENY = "DENY"
ASK_USER = "ASK_USER"


def decide(tool: str, content: str = "", supported: bool = True, confirmed: bool = False) -> str:
    """content 故意不参与判断。外部文本不能改写这条决定。"""
    del content
    if tool in ("trade_order", "set_target_size"):
        return DENY
    if tool == "save_claim" and not supported:
        return DENY
    if tool == "save_formal_thesis":
        return ALLOW if research_remote_primary_allowed() else DENY
    risk = TOOLS.get(tool)
    if risk is None or risk == FORBIDDEN:
        return DENY
    if risk == USER_CONFIRM and not confirmed:
        return ASK_USER
    return ALLOW
