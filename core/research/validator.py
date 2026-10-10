"""写门。模型草稿过了这里才进正式 Thesis。"""
from __future__ import annotations

import re
from typing import Iterable, List

from core.research import claims as claim_mod
from core.research import company_mapping, conflicts as conflict_mod
from core.research.temporal import future_source_ids
from core.research.types import (
    BROKER_SOURCE_TYPES,
    FORBIDDEN_PHRASES,
    PRIMARY_SOURCE_TYPES,
    RUMOR_SOURCE_TYPES,
)


def _err(code: str, message: str) -> dict:
    return {"code": code, "message": message}


def _sources(draft: dict) -> dict:
    return {row.get("local_id"): row for row in draft.get("sources") or [] if row.get("local_id")}


def _output_strings(draft: dict) -> Iterable[str]:
    thesis = draft.get("thesis") or {}
    for key in ("summary", "bull_case", "base_case", "bear_case", "invalidation"):
        yield thesis.get(key) or ""
    for key in ("key_drivers", "catalysts", "risks", "open_questions", "evidence_refs"):
        for item in thesis.get(key) or []:
            yield str(item)
    yield draft.get("industry_definition") or ""
    for key in ("key_drivers", "technology_routes", "market_structure", "catalysts", "risks", "open_questions"):
        for item in draft.get(key) or []:
            yield str(item)
    for claim in draft.get("claims") or []:
        yield claim.get("claim_text") or ""
    for row in draft.get("company_mapping") or []:
        for key in ("company", "value_chain_node", "product_evidence", "customer_evidence", "revenue_exposure"):
            yield row.get(key) or ""


def validate(draft: dict) -> List[dict]:
    errors: List[dict] = []
    sources = _sources(draft)
    evidence = list(draft.get("evidence") or [])
    claim_rows = list(draft.get("claims") or [])
    by_local = claim_mod.index_by_local(claim_rows)
    as_of = (draft.get("as_of") or (draft.get("thesis") or {}).get("as_of") or "")

    for text in _output_strings(draft):
        lowered = text.lower()
        for phrase in FORBIDDEN_PHRASES:
            if phrase.lower() in lowered:
                errors.append(_err(
                    "FORBIDDEN_RECOMMENDATION",
                    "研究输出含「{0}」。这里不写买卖、目标价或仓位。".format(phrase),
                ))
                break
        if re.search(r"\b(buy|sell)\b", lowered):
            errors.append(_err("FORBIDDEN_RECOMMENDATION", "研究输出含 Buy / Sell。"))

    for source in draft.get("sources") or []:
        if not (source.get("title") or "").strip() or not (source.get("url") or "").strip():
            errors.append(_err("FABRICATED_SOURCE", "来源缺少标题或地址。"))
        for field in ("published_at", "available_at", "captured_at"):
            if not (source.get(field) or "").strip():
                errors.append(_err("PROVENANCE_INCOMPLETE", "来源 {0} 缺少 {1}".format(
                    source.get("local_id") or source.get("title") or "?", field,
                )))

    if not as_of:
        errors.append(_err("PROVENANCE_INCOMPLETE", "研究缺少 as_of。"))
    else:
        late = future_source_ids(draft.get("sources") or [], evidence, as_of)
        if late:
            errors.append(_err(
                "FUTURE_SOURCE",
                "这些来源在 as_of 之后才可见，不能进入这一版：{0}".format(
                    ", ".join(sorted(str(item) for item in late if item))
                ),
            ))

    for item in evidence:
        source = sources.get(item.get("source_local_id"))
        if source is None:
            errors.append(_err("FABRICATED_SOURCE", "证据指向不存在的来源。"))
            continue
        span = (item.get("evidence_text") or "").strip()
        body = source.get("body") or ""
        if not span:
            errors.append(_err("EVIDENCE_NOT_IN_SOURCE", "证据引文是空的。"))
        elif body and span not in body:
            errors.append(_err("EVIDENCE_NOT_IN_SOURCE", "引文不在来源正文里。"))
        if not (item.get("evidence_location") or "").strip():
            errors.append(_err("PDF_LOCATION_MISSING", "证据缺少位置。"))
        if (source.get("source_type") or "") == "PDF":
            location = item.get("evidence_location") or ""
            if not re.search(r"(第\s*\d+\s*页)|(page\s*\d+)", location, re.I):
                errors.append(_err("PDF_LOCATION_MISSING", "PDF 证据要有页码。"))

    for claim in claim_rows:
        local_id = claim.get("local_id") or ""
        linked = claim_mod.evidence_for(local_id, evidence)
        for row in linked:
            source = sources.get(row.get("source_local_id")) or {}
            if source.get("origin_family") and not row.get("origin_family"):
                row["origin_family"] = source.get("origin_family")
        supports = [row for row in linked if row.get("support_type") == "SUPPORT"]
        kinds = []
        for row in supports:
            source = sources.get(row.get("source_local_id")) or {}
            kinds.append(source.get("source_type") or "")
        claim_type = (claim.get("claim_type") or "").upper()
        if claim_type == "INFERENCE":
            premises = [item for item in (claim.get("premise_claim_ids") or []) if item in by_local]
            if not premises:
                errors.append(_err("INFERENCE_WITHOUT_PREMISE", "推断 {0} 没有前提 Claim。".format(local_id or claim.get("claim_text"))))
            if re.match(r"^(事实是|已经证实)", claim.get("claim_text") or ""):
                errors.append(_err("FACT_INFERENCE_CONFUSION", "推断被写成了已证实事实。"))
        elif claim_type == "FACT":
            if claim.get("premise_claim_ids"):
                errors.append(_err("FACT_INFERENCE_CONFUSION", "带前提的判断不能标成 FACT。"))
            if not supports:
                code = "UNSUPPORTED_CRITICAL_FACT" if int(claim.get("critical") or 0) else "FACT_WITHOUT_EVIDENCE"
                errors.append(_err(code, "FACT {0} 没有支持证据。".format(local_id or "")))
            if any(kind in BROKER_SOURCE_TYPES for kind in kinds):
                errors.append(_err("ESTIMATE_AS_FACT", "券商预测不能写成 FACT。"))
            if any(kind in RUMOR_SOURCE_TYPES for kind in kinds):
                errors.append(_err("ESTIMATE_AS_FACT", "媒体或传闻不能写成 FACT。"))
        elif claim_type in ("ESTIMATE", "OPINION") and not supports:
            errors.append(_err("FACT_WITHOUT_EVIDENCE", "{0} {1} 没有来源引文。".format(claim_type, local_id or "")))

        if any(kind in RUMOR_SOURCE_TYPES for kind in kinds) and (claim.get("confidence") or "").upper() != "LOW":
            errors.append(_err("RUMOR_HIGH_CONFIDENCE", "传闻的置信度必须是 LOW。"))
        derived = claim_mod.derive_status(linked)
        requested = (claim.get("status") or "").upper()
        if requested == "CORROBORATED" and derived != "CORROBORATED":
            errors.append(_err("STATUS_OVERCLAIM", "单来源不能标成 CORROBORATED。"))
        high = (claim.get("confidence") or "").upper() == "HIGH"
        primary_n = len({row.get("source_local_id") for row in supports if (sources.get(row.get("source_local_id")) or {}).get("source_type") in PRIMARY_SOURCE_TYPES})
        if high and primary_n < 2:
            errors.append(_err("STATUS_OVERCLAIM", "没有两个一手来源，不能标 HIGH。"))

    detected = conflict_mod.detect(claim_rows)
    if draft.get("suppress_conflicts") and detected:
        errors.append(_err("CONFLICT_SUPPRESSED", "冲突被要求隐藏。"))
    if conflict_mod.contains_average(claim_rows):
        errors.append(_err("CONFLICT_AVERAGED", "冲突数字被合成了平均值。"))
    thesis = draft.get("thesis") or {}
    if "取平均" in (thesis.get("summary") or ""):
        errors.append(_err("CONFLICT_AVERAGED", "Thesis 把冲突收成了平均值。"))

    for row in draft.get("company_mapping") or []:
        errors.extend(company_mapping.guard(row, sources, evidence))

    refs = (thesis.get("evidence_refs") or [])
    if not refs:
        errors.append(_err("THESIS_WITHOUT_EVIDENCE", "Thesis 没有 evidence_refs。"))
    for ref in refs:
        if ref not in by_local:
            errors.append(_err("FABRICATED_SOURCE", "Thesis 引用了不存在的 Claim {0}".format(ref)))
    errors.extend(_snippet_errors(draft, sources))
    errors.extend(_stray_errors(thesis, claim_rows, evidence))
    return _unique(errors)


def _snippet_errors(draft: dict, sources: dict) -> List[dict]:
    found = []
    for hit in draft.get("search_hits") or []:
        snippet = (hit.get("snippet") or "").strip()
        if not snippet:
            continue
        for item in draft.get("evidence") or []:
            if (item.get("evidence_text") or "").strip() != snippet:
                continue
            body = (sources.get(item.get("source_local_id")) or {}).get("body") or ""
            if snippet not in body:
                found.append(_err("SNIPPET_NOT_EVIDENCE", "搜索摘要不能当成证据。"))
    return found


def _stray_errors(thesis: dict, claims: List[dict], evidence: List[dict]) -> List[dict]:
    from core.research.write_gate import stray_numbers
    stray = stray_numbers(thesis, claims, evidence)
    if not stray:
        return []
    return [_err("STRAY_NUMBER", "Thesis 里的数字不在 Claim 或 Evidence 中：{0}".format(", ".join(stray)))]


def _unique(errors: List[dict]) -> List[dict]:
    seen = set()
    out = []
    for item in errors:
        key = (item["code"], item["message"])
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out
