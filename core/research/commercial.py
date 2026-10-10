"""商业化阶段不能从相邻词升级。"""
from __future__ import annotations

from core.research.types import COMMERCIAL_STAGES


def errors(stage: str, evidence_text: str) -> list:
    stage = (stage or "").upper()
    if not stage or stage == "UNKNOWN":
        return []
    if stage not in COMMERCIAL_STAGES:
        return [{"code": "STAGE_UNKNOWN", "message": "未知商业化阶段。"}]
    text = evidence_text or ""
    if stage == "MASS_PRODUCTION" and any(token in text for token in ("送样", "样品")) and "量产" not in text:
        return [{"code": "STAGE_CONFUSION", "message": "送样或样品不能写成量产。"}]
    if stage == "QUALIFICATION" and "样品" in text and "认证" not in text and "通过" not in text:
        return [{"code": "STAGE_CONFUSION", "message": "送样不能写成认证通过。"}]
    if stage == "REVENUE_RECOGNIZED" and "订单" in text and "收入" not in text:
        return [{"code": "STAGE_CONFUSION", "message": "订单不能写成已确认收入。"}]
    if stage == "ORDER" and "样品" in text and "订单" not in text:
        return [{"code": "STAGE_CONFUSION", "message": "样品不能写成订单。"}]
    return []
