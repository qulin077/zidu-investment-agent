"""把已经校验过的草稿收成行业模型。这里不新增事实。"""
from __future__ import annotations


def build_model(draft: dict) -> dict:
    thesis = draft.get("thesis") or {}
    return {
        "industry_definition": draft.get("industry_definition") or "",
        "structural_changes": list(draft.get("key_drivers") or []),
        "value_chain": list(draft.get("value_chain") or []),
        "key_drivers": list(draft.get("key_drivers") or []),
        "economics": list(draft.get("technology_routes") or []),
        "competition": list(draft.get("market_structure") or []),
        "company_exposure": list(draft.get("company_mapping") or []),
        "catalysts": list(draft.get("catalysts") or thesis.get("catalysts") or []),
        "risks": list(draft.get("risks") or thesis.get("risks") or []),
        "open_questions": list(draft.get("open_questions") or []),
    }
