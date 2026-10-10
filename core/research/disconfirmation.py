"""反证只记录查过什么。没找到反证不等于命题为真。"""
from __future__ import annotations

from core.research.types import DISCONFIRMATION_RESULTS


def normalize(result: str) -> str:
    if result == "PROVEN_TRUE":
        raise ValueError("PROVEN_TRUE")
    if result not in DISCONFIRMATION_RESULTS:
        raise ValueError("DISCONFIRMATION_RESULT")
    return result


def queries_for(claim_text: str) -> list:
    text = claim_text or "关键判断"
    return [
        "{0} 的部署延迟或延期".format(text[:40]),
        "{0} 的替代方案或客户采用低于预期".format(text[:40]),
    ]
