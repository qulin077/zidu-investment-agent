"""30 个研究评测。测的是写门会不会放进假事实，不是报告好不好看。"""
from __future__ import annotations

import copy

from core.research.fixtures.structural import minimal


def _draft(theme: str = "样本行业") -> dict:
    return minimal(theme)


def _source(local_id: str, body: str, source_type: str = "RESEARCH_NOTE", available_at: str = "2026-09-01T10:00:00+08:00") -> dict:
    return {
        "local_id": local_id,
        "url": "fixture://{0}".format(local_id),
        "title": local_id,
        "publisher": "fixture",
        "source_type": source_type,
        "published_at": available_at,
        "available_at": available_at,
        "captured_at": "2026-09-20T12:00:00+08:00",
        "author": "fixture",
        "source_quality": "SECONDARY",
        "body": body,
    }


def CASES() -> list:
    cases = []

    draft = _draft()
    cases.append({"id": "01", "name": "single source stays single", "expect": "accept", "draft": draft, "check": "single"})

    two = _draft()
    sentence = two["claims"][0]["claim_text"]
    two["sources"].append(_source("S2", sentence))
    two["evidence"].append({
        "claim_local_id": "C1", "source_local_id": "S2", "evidence_text": sentence,
        "evidence_location": "L1", "support_type": "SUPPORT",
    })
    cases.append({"id": "02", "name": "two sources can corroborate", "expect": "accept", "draft": two, "check": "corroborated"})

    conflict = _draft()
    conflict["sources"].append(_source("SB", "卖方甲：空间 100 亿。卖方乙：空间 300 亿。", "BROKER"))
    conflict["claims"].extend([
        {"local_id": "E1", "claim_text": "卖方甲估计空间 100 亿。", "claim_type": "ESTIMATE", "subject": "空间", "predicate": "估计", "object": "100", "confidence": "LOW", "critical": 0, "metric": "space", "numeric_value": 100, "definition": "口径甲", "premise_claim_ids": []},
        {"local_id": "E2", "claim_text": "卖方乙估计空间 300 亿。", "claim_type": "ESTIMATE", "subject": "空间", "predicate": "估计", "object": "300", "confidence": "LOW", "critical": 0, "metric": "space", "numeric_value": 300, "definition": "口径乙", "premise_claim_ids": []},
    ])
    conflict["evidence"].extend([
        {"claim_local_id": "E1", "source_local_id": "SB", "evidence_text": "空间 100 亿", "evidence_location": "L1", "support_type": "SUPPORT"},
        {"claim_local_id": "E2", "source_local_id": "SB", "evidence_text": "空间 300 亿", "evidence_location": "L1", "support_type": "SUPPORT"},
    ])
    cases.append({"id": "03", "name": "conflict is not averaged", "expect": "accept", "draft": conflict, "check": "conflict"})

    supplier = _draft()
    supplier["company_mapping"][0]["exposure_type"] = "INDIRECT"
    supplier["company_mapping"][0]["product_evidence"] = "有相关产品，市场称核心供应商"
    supplier["company_mapping"][0]["customer_evidence"] = ""
    cases.append({"id": "04", "name": "no customer cannot be core supplier", "expect": "reject", "code": "OVERCLAIM_SUPPLIER", "draft": supplier})

    rumor = _draft()
    rumor["claims"][0]["claim_type"] = "ESTIMATE"
    rumor["claims"][0]["critical"] = 0
    rumor["claims"][0]["confidence"] = "LOW"
    rumor["sources"][0]["source_type"] = "RUMOR"
    cases.append({"id": "05", "name": "rumor stays low-confidence estimate", "expect": "accept", "draft": rumor})

    future = _draft()
    future["sources"][0]["available_at"] = "2026-09-25T10:00:00+08:00"
    future["sources"][0]["published_at"] = "2026-09-25T10:00:00+08:00"
    cases.append({"id": "06", "name": "future filing cannot enter", "expect": "reject", "code": "FUTURE_SOURCE", "gate": "temporal_leak", "draft": future})

    broker = _draft()
    broker["claims"][0]["claim_type"] = "FACT"
    broker["sources"][0]["source_type"] = "BROKER"
    cases.append({"id": "07", "name": "broker forecast is not fact", "expect": "reject", "code": "ESTIMATE_AS_FACT", "draft": broker})

    bare = _draft()
    bare["claims"].append({
        "local_id": "I1", "claim_text": "若需求上升则环节可能受益。", "claim_type": "INFERENCE",
        "subject": "环节", "predicate": "受益", "object": "可能", "confidence": "LOW",
        "critical": 0, "premise_claim_ids": [], "metric": "", "numeric_value": None,
    })
    cases.append({"id": "08", "name": "inference needs premises", "expect": "reject", "code": "INFERENCE_WITHOUT_PREMISE", "draft": bare})

    inferred = _draft()
    inferred["claims"].append({
        "local_id": "I1", "claim_text": "若夹具原文成立，则这个环节可以被单独讨论。", "claim_type": "INFERENCE",
        "subject": "环节", "predicate": "讨论", "object": "可能", "confidence": "LOW",
        "critical": 0, "premise_claim_ids": ["C1"], "metric": "", "numeric_value": None,
    })
    cases.append({"id": "09", "name": "inference with premise", "expect": "accept", "draft": inferred})

    direct = _draft()
    direct["company_mapping"][0]["exposure_type"] = "DIRECT"
    direct["company_mapping"][0]["product_evidence"] = ""
    direct["company_mapping"][0]["customer_evidence"] = ""
    cases.append({"id": "10", "name": "no evidence cannot be direct", "expect": "reject", "code": "CANNOT_DIRECT", "gate": "direct_exposure_overclaim", "draft": direct})

    cases.append({"id": "11", "name": "thematic mapping allowed", "expect": "accept", "draft": _draft(), "check": "thematic"})

    unknown = _draft()
    unknown["company_mapping"][0]["revenue_exposure"] = "UNKNOWN"
    cases.append({"id": "12", "name": "unknown revenue stays unknown", "expect": "accept", "draft": unknown})

    missing = _draft()
    missing["evidence"] = []
    cases.append({"id": "13", "name": "critical fact without evidence", "expect": "reject", "code": "UNSUPPORTED_CRITICAL_FACT", "gate": "unsupported_critical_fact", "draft": missing})

    wrong = _draft()
    wrong["evidence"][0]["evidence_text"] = "这段文字不在正文里"
    cases.append({"id": "14", "name": "citation not in source", "expect": "reject", "code": "EVIDENCE_NOT_IN_SOURCE", "gate": "wrong_evidence_link", "draft": wrong})

    fake = _draft()
    fake["evidence"][0]["source_local_id"] = "NO_SUCH"
    cases.append({"id": "15", "name": "fabricated source", "expect": "reject", "code": "FABRICATED_SOURCE", "gate": "fabricated_source", "draft": fake})

    pdf = _draft()
    pdf["sources"][0]["source_type"] = "PDF"
    pdf["evidence"][0]["evidence_location"] = "见附件"
    cases.append({"id": "16", "name": "pdf needs a page", "expect": "reject", "code": "PDF_LOCATION_MISSING", "draft": pdf})

    noref = _draft()
    noref["thesis"]["evidence_refs"] = []
    cases.append({"id": "17", "name": "thesis needs evidence refs", "expect": "reject", "code": "THESIS_WITHOUT_EVIDENCE", "draft": noref})

    buy = _draft()
    buy["thesis"]["summary"] = "建议买入样本公司。"
    cases.append({"id": "18", "name": "no buy", "expect": "reject", "code": "FORBIDDEN_RECOMMENDATION", "draft": buy})

    sell = _draft()
    sell["thesis"]["summary"] = "建议卖出样本公司。"
    cases.append({"id": "19", "name": "no sell", "expect": "reject", "code": "FORBIDDEN_RECOMMENDATION", "draft": sell})

    size = _draft()
    size["thesis"]["summary"] = "仓位放到三成。"
    cases.append({"id": "20", "name": "no position size", "expect": "reject", "code": "FORBIDDEN_RECOMMENDATION", "draft": size})

    target = _draft()
    target["thesis"]["bull_case"] = "目标价 80 元。"
    cases.append({"id": "21", "name": "no target price", "expect": "reject", "code": "FORBIDDEN_RECOMMENDATION", "draft": target})

    confused = _draft()
    confused["claims"][0]["premise_claim_ids"] = ["C0"]
    cases.append({"id": "22", "name": "fact cannot carry premises", "expect": "reject", "code": "FACT_INFERENCE_CONFUSION", "gate": "fact_inference_confusion", "draft": confused})

    later = _draft()
    later["as_of"] = "2026-09-01T00:00:00+08:00"
    later["thesis"]["as_of"] = later["as_of"]
    later["sources"][0]["available_at"] = "2026-09-20T10:00:00+08:00"
    cases.append({"id": "23", "name": "source after as_of", "expect": "reject", "code": "FUTURE_SOURCE", "gate": "temporal_leak", "draft": later})

    hidden = copy.deepcopy(conflict)
    hidden["suppress_conflicts"] = True
    cases.append({"id": "24", "name": "conflict cannot be suppressed", "expect": "reject", "code": "CONFLICT_SUPPRESSED", "draft": hidden})

    averaged = copy.deepcopy(conflict)
    averaged["claims"].append({
        "local_id": "E3", "claim_text": "空间取中间值。", "claim_type": "ESTIMATE", "subject": "空间",
        "predicate": "平均", "object": "200", "confidence": "LOW", "critical": 0,
        "metric": "space", "numeric_value": 200, "definition": "平均", "premise_claim_ids": [],
    })
    averaged["evidence"].append({
        "claim_local_id": "E3", "source_local_id": "SB", "evidence_text": "空间 100 亿",
        "evidence_location": "L1", "support_type": "SUPPORT",
    })
    cases.append({"id": "25", "name": "average number is blocked", "expect": "reject", "code": "CONFLICT_AVERAGED", "draft": averaged})

    stamped = _draft()
    stamped["claims"][0]["status"] = "CORROBORATED"
    cases.append({"id": "26", "name": "one source cannot be corroborated", "expect": "reject", "code": "STATUS_OVERCLAIM", "draft": stamped})

    crit = _draft()
    crit["evidence"] = []
    crit["claims"][0]["critical"] = 1
    cases.append({"id": "27", "name": "critical fact still needs evidence", "expect": "reject", "code": "UNSUPPORTED_CRITICAL_FACT", "gate": "unsupported_critical_fact", "draft": crit})

    provenance = _draft()
    provenance["sources"][0]["available_at"] = ""
    cases.append({"id": "28", "name": "source needs available_at", "expect": "reject", "code": "PROVENANCE_INCOMPLETE", "draft": provenance})

    cases.append({"id": "29", "name": "web search abstains", "expect": "abstain", "op": "search_web"})

    cases.append({
        "id": "30",
        "name": "three industries share the output contract",
        "expect": "accept",
        "op": "three_themes",
        "drafts": [_draft("光模块"), _draft("半导体设备"), _draft("AI电源")],
    })
    return cases
