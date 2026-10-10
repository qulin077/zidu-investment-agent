"""公司映射只标暴露，不升成核心供应商。"""
from __future__ import annotations

from typing import Iterable, List

from core.research.commercial import errors as stage_errors
from core.research.types import PRIMARY_SOURCE_TYPES


def _known_revenue(value: str) -> bool:
    text = (value or "").strip()
    return bool(text) and text.upper() != "UNKNOWN"


def guard(row: dict, sources_by_local: dict, evidence: Iterable[dict]) -> List[dict]:
    errors = []
    exposure = (row.get("exposure_type") or "UNKNOWN").upper()
    product = (row.get("product_evidence") or "").strip()
    customer = (row.get("customer_evidence") or "").strip()
    revenue = (row.get("revenue_exposure") or "UNKNOWN").strip()
    refs = row.get("evidence_refs") or []
    blob = " ".join([
        row.get("company") or "",
        product,
        customer,
        row.get("value_chain_node") or "",
    ])
    if _known_revenue(revenue) and not refs:
        errors.append({
            "code": "GUESSED_REVENUE",
            "message": "{0} 的收入暴露没有证据，应写 UNKNOWN".format(row.get("company") or "公司"),
        })
    if "核心供应商" in blob and exposure != "DIRECT":
        errors.append({
            "code": "OVERCLAIM_SUPPLIER",
            "message": "{0} 没有一手客户证据，不能写成核心供应商".format(row.get("company") or "公司"),
        })
    errors.extend(_stage(row, evidence))
    if exposure == "THEMATIC" or exposure == "UNKNOWN":
        return errors
    if exposure == "INDIRECT" and not product:
        errors.append({
            "code": "CANNOT_INDIRECT",
            "message": "{0} 没有产品证据，不能标 INDIRECT".format(row.get("company") or "公司"),
        })
        return errors
    if exposure != "DIRECT":
        return errors
    if not product or (not customer and not _known_revenue(revenue)):
        errors.append({
            "code": "CANNOT_DIRECT",
            "message": "{0} 缺少产品或客户/收入证据，不能标 DIRECT".format(row.get("company") or "公司"),
        })
        return errors
    primary = False
    for ref in refs:
        for item in evidence:
            if item.get("claim_local_id") != ref and item.get("claim_id") != ref:
                continue
            source = sources_by_local.get(item.get("source_local_id")) or sources_by_local.get(item.get("source_id"))
            if source and (source.get("source_type") or "") in PRIMARY_SOURCE_TYPES:
                primary = True
    if not primary:
        errors.append({
            "code": "CANNOT_DIRECT",
            "message": "{0} 的客户或收入证据还不是公告/电话会原文，不能标 DIRECT".format(row.get("company") or "公司"),
        })
    return errors


def _stage(row: dict, evidence: Iterable[dict]) -> List[dict]:
    stage = (row.get("commercial_stage") or "").strip()
    if not stage or stage.upper() == "UNKNOWN":
        return []
    refs = set(row.get("evidence_refs") or [])
    blob = " ".join(
        (item.get("evidence_text") or "")
        for item in evidence
        if not refs or item.get("claim_local_id") in refs or item.get("claim_id") in refs
    )
    return stage_errors(stage, blob)
