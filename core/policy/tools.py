"""工具权限。主 Agent 不自带无限权限。"""
from __future__ import annotations

READ_ONLY = "READ_ONLY"
WRITE_INTERNAL = "WRITE_INTERNAL"
USER_CONFIRM = "USER_CONFIRM"
FORBIDDEN = "FORBIDDEN"

TOOLS = {
    "search_web": READ_ONLY,
    "read_pdf": READ_ONLY,
    "read_filing": READ_ONLY,
    "save_claim": WRITE_INTERNAL,
    "save_formal_thesis": USER_CONFIRM,
    "attach_thesis": USER_CONFIRM,
    "activate_rule": USER_CONFIRM,
    "set_target_size": FORBIDDEN,
    "trade_order": FORBIDDEN,
}
