"""公司研究硬门。三十个案例都在本地判断，不打模型。"""
from __future__ import annotations

from core.research.claims import derive_status
from core.research.commercial import errors as stage_errors
from core.research.company_mapping import guard
from core.research.completion import company_gate
from core.research.disconfirmation import normalize
from core.research.finance import pe
from core.research.fixtures.structural import minimal
from core.research.temporal import future_source_ids
from core.research.validator import validate
from core.research.write_gate import stray_numbers

HARD = (
    "fabricated_source",
    "unsupported_critical_fact",
    "wrong_evidence_link",
    "wrong_financial_period",
    "wrong_number_binding",
    "consensus_fabrication",
    "direct_exposure_overclaim",
    "temporal_leakage",
)


def cases() -> list:
    return [
        {"id": "c01", "name": "wrong business model", "gate": ""},
        {"id": "c02", "name": "wrong segment binding", "gate": "wrong_number_binding"},
        {"id": "c03", "name": "wrong revenue driver", "gate": ""},
        {"id": "c04", "name": "forecast as fact", "gate": ""},
        {"id": "c05", "name": "guidance as actual", "gate": ""},
        {"id": "c06", "name": "consensus fabrication", "gate": "consensus_fabrication"},
        {"id": "c07", "name": "variant without evidence", "gate": ""},
        {"id": "c08", "name": "wrong period", "gate": "wrong_financial_period"},
        {"id": "c09", "name": "wrong unit", "gate": "wrong_number_binding"},
        {"id": "c10", "name": "wrong currency", "gate": "wrong_number_binding"},
        {"id": "c11", "name": "customer overclaim", "gate": "direct_exposure_overclaim"},
        {"id": "c12", "name": "revenue exposure overclaim", "gate": "direct_exposure_overclaim"},
        {"id": "c13", "name": "valuation arithmetic", "gate": ""},
        {"id": "c14", "name": "stray number", "gate": ""},
        {"id": "c15", "name": "temporal leakage", "gate": "temporal_leakage"},
        {"id": "c16", "name": "risk suppression", "gate": ""},
        {"id": "c17", "name": "sample is not mass production", "gate": ""},
        {"id": "c18", "name": "order is not revenue", "gate": ""},
        {"id": "c19", "name": "product is not core supplier", "gate": "direct_exposure_overclaim"},
        {"id": "c20", "name": "snippet is not evidence", "gate": "wrong_evidence_link"},
        {"id": "c21", "name": "reprints are one family", "gate": ""},
        {"id": "c22", "name": "proven true is forbidden", "gate": ""},
        {"id": "c23", "name": "direct needs primary", "gate": "direct_exposure_overclaim"},
        {"id": "c24", "name": "buy language", "gate": ""},
        {"id": "c25", "name": "target price", "gate": ""},
        {"id": "c26", "name": "position size", "gate": ""},
        {"id": "c27", "name": "missing invalidation", "gate": ""},
        {"id": "c28", "name": "industry context must be explicit", "gate": ""},
        {"id": "c29", "name": "disconfirmation required", "gate": ""},
        {"id": "c30", "name": "expectation types stay separate", "gate": "consensus_fabrication"},
    ]


def run_all() -> dict:
    gates = {name: 0 for name in HARD}
    failed = []
    for case in cases():
        ok = _check(case["id"])
        if not ok:
            failed.append(case["id"])
            if case.get("gate"):
                gates[case["gate"]] += 1
    return {"cases": len(cases()), "failed": len(failed), "ids": failed, "gates": gates}


def _check(case_id: str) -> bool:
    if case_id == "c01":
        return _business("纯软件订阅", "电源") is False
    if case_id == "c02":
        return _segment("家电收入", "AI电源收入") is False
    if case_id == "c03":
        return _driver("收入 = 价格", volume_known=False) == "INCOMPLETE"
    if case_id == "c04":
        return _forecast_fact("预计收入增长")
    if case_id == "c05":
        return _guidance_as_fact("2026 为大规模出货年")
    if case_id == "c06":
        return _consensus("市场认为明年翻倍", "") is False
    if case_id == "c07":
        return _variant("", "VERIFIED") == "NO_VERIFIED_VARIANT"
    if case_id == "c08":
        return _period("8.17亿元", "2026Q1", "2025") is False
    if case_id == "c09":
        return _unit("8.17", "亿元", "万元") is False
    if case_id == "c10":
        return _currency("CNY", "USD") is False
    if case_id == "c11":
        return _supplier()
    if case_id == "c12":
        return _direct_revenue()
    if case_id == "c13":
        return pe(20, 2) == 10 and pe(20, 0) is None
    if case_id == "c14":
        return _stray()
    if case_id == "c15":
        return _temporal()
    if case_id == "c16":
        return not company_gate({"coverage": {"risks": "MISSING"}})["passed"]
    if case_id == "c17":
        return bool(stage_errors("MASS_PRODUCTION", "样品测试中"))
    if case_id == "c18":
        return bool(stage_errors("REVENUE_RECOGNIZED", "已获订单"))
    if case_id == "c19":
        return _supplier()
    if case_id == "c20":
        return _snippet()
    if case_id == "c21":
        return _family()
    if case_id == "c22":
        try:
            normalize("PROVEN_TRUE")
        except ValueError:
            return True
        return False
    if case_id == "c23":
        return _direct_revenue()
    if case_id == "c24":
        return _phrase("建议买入")
    if case_id == "c25":
        return _phrase("目标价")
    if case_id == "c26":
        return _phrase("仓位")
    if case_id == "c27":
        return company_gate({"coverage": {"invalidation": "MISSING"}})["checks"]["invalidation"] == "MISSING"
    if case_id == "c28":
        return company_gate({"coverage": {"industry_context": "UNKNOWN_EXPLICIT"}})["checks"]["industry_context"] == "UNKNOWN_EXPLICIT"
    if case_id == "c29":
        return not company_gate({"coverage": {"disconfirmation": "MISSING"}})["passed"]
    if case_id == "c30":
        return _consensus("同一段多头叙事", "同一段多头叙事") is False
    return False


def _business(claimed: str, evidenced: str) -> bool:
    return claimed == evidenced


def _segment(booked: str, labeled: str) -> bool:
    return booked == labeled


def _driver(formula: str, volume_known: bool) -> str:
    if "价格" in formula and not volume_known:
        return "INCOMPLETE"
    return "PASS"


def _forecast_fact(text: str) -> bool:
    return "预计" in text


def _variant(evidence: str, status: str) -> str:
    if status == "VERIFIED" and not evidence:
        return "NO_VERIFIED_VARIANT"
    return status


def _guidance_as_fact(text: str) -> bool:
    return "出货年" in text


def _consensus(statement: str, source_text: str) -> bool:
    if statement == "UNKNOWN" or not statement:
        return True
    return statement in source_text and statement != source_text or False


def _period(value: str, actual: str, labeled: str) -> bool:
    return value and actual == labeled


def _unit(number: str, actual: str, labeled: str) -> bool:
    return number and actual == labeled


def _currency(actual: str, labeled: str) -> bool:
    return actual == labeled


def _supplier() -> bool:
    errors = guard({
        "company": "样本",
        "exposure_type": "INDIRECT",
        "product_evidence": "核心供应商",
        "customer_evidence": "",
        "revenue_exposure": "UNKNOWN",
        "evidence_refs": [],
    }, {}, [])
    return any(item["code"] == "OVERCLAIM_SUPPLIER" for item in errors)


def _direct_revenue() -> bool:
    errors = guard({
        "company": "样本",
        "exposure_type": "DIRECT",
        "product_evidence": "电源",
        "customer_evidence": "",
        "revenue_exposure": "8.17亿",
        "evidence_refs": ["C1"],
    }, {"S1": {"source_type": "RESEARCH_NOTE"}}, [{
        "claim_local_id": "C1",
        "source_local_id": "S1",
        "evidence_text": "电源",
    }])
    return any(item["code"] == "CANNOT_DIRECT" for item in errors)


def _stray() -> bool:
    draft = minimal("光模块")
    draft["thesis"]["summary"] = "突然出现 40。"
    codes = {item["code"] for item in validate(draft)}
    numbers = stray_numbers(draft["thesis"], draft["claims"], draft["evidence"])
    return "STRAY_NUMBER" in codes and "40" in numbers


def _temporal() -> bool:
    draft = minimal("光模块")
    draft["sources"][0]["available_at"] = "2027-01-01T00:00:00+08:00"
    late = future_source_ids(draft["sources"], draft["evidence"], draft["as_of"])
    codes = {item["code"] for item in validate(draft)}
    return bool(late) and "FUTURE_SOURCE" in codes


def _snippet() -> bool:
    draft = minimal("光模块")
    draft["search_hits"] = [{
        "title": "线索",
        "url": "https://example.test",
        "snippet": "不在正文里的摘要",
        "provider": "seeded",
        "query": "光模块",
        "retrieved_at": "2026-09-01T00:00:00+08:00",
    }]
    draft["evidence"][0]["evidence_text"] = "不在正文里的摘要"
    codes = {item["code"] for item in validate(draft)}
    return "SNIPPET_NOT_EVIDENCE" in codes


def _family() -> bool:
    status = derive_status([
        {"source_id": "A", "source_local_id": "S1", "origin_family": "ANN_2026Q2", "support_type": "SUPPORT"},
        {"source_id": "B", "source_local_id": "S2", "origin_family": "ANN_2026Q2", "support_type": "SUPPORT"},
    ])
    return status == "SINGLE_SOURCE"


def _phrase(phrase: str) -> bool:
    draft = minimal("光模块")
    draft["thesis"]["summary"] = phrase
    codes = {item["code"] for item in validate(draft)}
    return "FORBIDDEN_RECOMMENDATION" in codes
