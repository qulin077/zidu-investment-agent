"""网页是不可信外部数据。正文不能改系统提示、技能或工具权限。"""
from __future__ import annotations

import re

UNTRUSTED = "UNTRUSTED_EXTERNAL_DATA"

_MARKERS = (
    "ignore previous instructions",
    "reveal system prompt",
    "call this api",
    "mark this company direct",
    "忽略之前的指令",
    "忽略以上指令",
)
_BUY_LINE = re.compile(r"^\s*buy\b", re.I)


def markers(text: str) -> list:
    raw = text or ""
    low = raw.lower()
    found = [token for token in _MARKERS if token in low or token in raw]
    if _BUY_LINE.search(raw):
        found.append("buy")
    return found


def line_is_injection(line: str) -> bool:
    text = (line or "").strip()
    if not text:
        return False
    low = text.lower()
    if any(token in low or token in text for token in _MARKERS):
        return True
    if _BUY_LINE.search(text):
        return True
    return False
