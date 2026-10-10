"""完成门。没有答案可以是 UNKNOWN，但不能缺检查。"""
from __future__ import annotations

INDUSTRY_CHECKS = (
    "industry_boundary",
    "structural_change",
    "value_chain",
    "key_drivers",
    "critical_claims",
    "company_exposure",
    "risks",
    "disconfirmation",
    "open_questions",
    "thesis",
)

COMPANY_CHECKS = (
    "business_model",
    "revenue_drivers",
    "financial_trend",
    "industry_context",
    "critical_claims",
    "company_exposure",
    "expectations",
    "risks",
    "disconfirmation",
    "invalidation",
    "monitoring",
)


def industry_gate(state: dict) -> dict:
    checks = {name: _present(state, name) for name in INDUSTRY_CHECKS}
    return {"passed": _ok(checks), "checks": checks}


def company_gate(state: dict) -> dict:
    checks = {name: _present(state, name) for name in COMPANY_CHECKS}
    return {"passed": _ok(checks), "checks": checks}


def _ok(checks: dict) -> bool:
    return all(value != "MISSING" for value in checks.values())


def _present(state: dict, name: str) -> str:
    value = (state.get("coverage") or {}).get(name)
    if value in ("PASS", "GROUNDED", "LABELED", "ATTEMPTED", "EXPLICIT", "UNKNOWN_EXPLICIT", "PRESENT"):
        return value
    return "MISSING"
