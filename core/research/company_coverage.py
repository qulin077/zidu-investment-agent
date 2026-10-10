"""Deterministic coverage contract for company research.

The model may decide *how* to search and organise evidence, but it may not
decide that a research task is complete.  Completion is a product contract:
required evidence lanes must have been attempted and the required dossier
modules must contain grounded data.  Explicitly unavailable evidence remains
visible as a gap instead of being silently treated as complete.
"""
from __future__ import annotations

from typing import Iterable


FULL_DOSSIER = "FULL_DOSSIER"
FOCUSED = "FOCUSED"
INCREMENTAL_UPDATE = "INCREMENTAL_UPDATE"

SOURCE_LANES = (
    "filing-analysis",
    "management-communication",
    "sell-side-expectations",
    "market-narrative",
    "risk-disconfirmation",
)

_FULL_WORDS = ("全面", "完整", "公司档案", "深度研究", "系统研究", "基本面研究")
_UPDATE_WORDS = (
    "更新", "最近", "最新", "有没有变化", "发生了什么", "新资料", "再看",
    "重新分析", "升级档案", "新研究架构", "架构升级",
)
_FOCUS_WORDS = (
    "财报", "收入", "利润", "现金流", "毛利", "负债", "基本盘",
    "预期", "估值", "股价", "研报", "一致预期", "风险", "证伪",
    "壁垒", "竞争", "客户", "供应商", "管理层", "电话会", "业绩会",
)


def detect_mode(question: str, kind: str = "new", previous: dict | None = None) -> str:
    """Choose the research contract, not the answer content.

    A first broad company question means building a full baseline.  A narrow
    question remains focused.  A later freshness question checks changes
    against the saved dossier.
    """
    text = (question or "").strip()
    if previous and kind == "followup" and any(token in text for token in _UPDATE_WORDS):
        return INCREMENTAL_UPDATE
    if any(token in text for token in _FULL_WORDS):
        return FULL_DOSSIER
    if any(token in text for token in _FOCUS_WORDS):
        return FOCUSED
    if previous and kind == "followup":
        return FOCUSED
    return FULL_DOSSIER


def check(
    *, mode: str, question: str, source_plan: list, financial_statements: dict,
    dossier: dict, previous: dict | None = None,
) -> dict:
    """Evaluate a completed research run against its deterministic contract."""
    checks: list[dict] = []
    planned = {row.get("name"): row for row in source_plan or [] if row.get("name")}
    required_lanes = _required_lanes(mode, question)

    for lane in required_lanes:
        row = planned.get(lane)
        status, detail = _lane_status(row)
        checks.append(_item("source:" + lane, _lane_label(lane), "SOURCE", status, detail))

    if mode == INCREMENTAL_UPDATE:
        baseline = bool(previous)
        checks.append(_item(
            "prior_baseline", "已加载上次公司档案", "MEMORY",
            "PASS" if baseline else "MISSING",
            "本轮按上次档案检查新增与变化。" if baseline else "没有可比较的历史档案。",
        ))

    focus = _focus(question)
    if mode == FULL_DOSSIER or focus == "financial":
        coverage = (financial_statements or {}).get("coverage_status") or "INCOMPLETE"
        checks.append(_item(
            "financial:three_years", "最近三年年度财务基线", "DOSSIER",
            "PASS" if coverage == "COMPLETE" else _unavailable_if_attempted(planned.get("filing-analysis")),
            "财务解析覆盖状态：{0}".format(coverage),
        ))
        periodic = (financial_statements or {}).get("periodic_records") or []
        checks.append(_item(
            "financial:latest_period", "最新季报/半年报", "DOSSIER",
            "PASS" if periodic else _unavailable_if_attempted(planned.get("filing-analysis")),
            "已解析 {0} 期最新定期报告。".format(len(periodic)) if periodic else "已检查但尚未解析出最新定期报告。",
        ))

    for key, label, value in _required_modules(mode, focus, dossier):
        checks.append(_item(
            "module:" + key, label, "DOSSIER", "PASS" if _has_evidence(value) else "MISSING",
            "已有可展示证据。" if _has_evidence(value) else "档案中仍无可核对证据。",
        ))

    missing = [row["key"] for row in checks if row["status"] == "MISSING"]
    unavailable = [row["key"] for row in checks if row["status"] == "ATTEMPTED_UNAVAILABLE"]
    missing_labels = [row["label"] for row in checks if row["status"] == "MISSING"]
    unavailable_labels = [row["label"] for row in checks if row["status"] == "ATTEMPTED_UNAVAILABLE"]
    critical_unavailable = any(key in unavailable for key in (
        "source:filing-analysis", "financial:three_years",
    ))
    if critical_unavailable:
        status = "SOURCE_UNAVAILABLE"
        reason = "已尝试关键官方来源，但当前无法取得足够财报证据。"
    elif missing:
        status = "PARTIAL"
        reason = "仍有必需模块未执行或没有进入档案。"
    elif unavailable:
        status = "PARTIAL"
        reason = "必需来源已尝试，但部分公开资料不可得。"
    else:
        status = "COMPLETE"
        reason = "本模式要求的来源与档案模块均已覆盖。"
    return {
        "contract_version": "company-coverage-v1",
        "mode": mode,
        "status": status,
        "passed": status == "COMPLETE",
        "can_publish_as_full": mode == FULL_DOSSIER and status == "COMPLETE",
        "checks": checks,
        "missing_required": missing,
        "attempted_unavailable": unavailable,
        "missing_labels": missing_labels,
        "attempted_unavailable_labels": unavailable_labels,
        "completion_reason": reason,
        "checked_count": len(checks),
        "passed_count": sum(row["status"] == "PASS" for row in checks),
    }


def _required_lanes(mode: str, question: str) -> tuple[str, ...]:
    if mode in (FULL_DOSSIER, INCREMENTAL_UPDATE):
        return SOURCE_LANES
    focus = _focus(question)
    relevant = {
        "financial": ("filing-analysis", "management-communication"),
        "expectations": ("filing-analysis", "management-communication", "sell-side-expectations", "market-narrative"),
        "risk": ("filing-analysis", "management-communication", "market-narrative"),
        "moat": ("filing-analysis", "management-communication", "market-narrative"),
        "general": ("filing-analysis", "management-communication"),
    }[focus]
    return tuple(dict.fromkeys(relevant + ("risk-disconfirmation",)))


def _required_modules(mode: str, focus: str, dossier: dict) -> Iterable[tuple[str, str, object]]:
    basics = dossier.get("company_basics") or {}
    thesis = dossier.get("core_thesis") or {}
    expectations = dossier.get("expectations") or {}
    risks = dossier.get("risks_and_invalidation") or {}
    all_modules = (
        ("business", "公司基本盘", basics.get("products_and_customers")),
        ("segments", "业务与收入结构", basics.get("segments") or basics.get("revenue_and_profit_sources")),
        ("moat", "核心壁垒", (dossier.get("moat") or {}).get("evidence")),
        ("industry", "行业位置", (dossier.get("industry_position") or {}).get("evidence")),
        ("drivers", "增长与利润驱动", (thesis.get("growth_drivers") or []) + (thesis.get("profit_drivers") or [])),
        ("expectations", "公司/卖方/市场预期", _flatten(expectations.values())),
        ("price_gap", "股价与预期差", (dossier.get("price_and_expectations") or {}).get("expectation_gap")),
        ("risks", "风险与失效条件", (risks.get("risks") or []) + (risks.get("invalidation") or [])),
        ("monitoring", "下一步监控指标", dossier.get("monitoring")),
    )
    if mode in (FULL_DOSSIER, INCREMENTAL_UPDATE):
        return all_modules
    selected = {
        "financial": {"business", "segments", "drivers", "risks", "monitoring"},
        "expectations": {"expectations", "price_gap", "risks", "monitoring"},
        "risk": {"risks", "monitoring"},
        "moat": {"business", "moat", "industry", "risks", "monitoring"},
        "general": {"business", "drivers", "risks", "monitoring"},
    }[focus]
    return tuple(row for row in all_modules if row[0] in selected)


def _focus(question: str) -> str:
    text = question or ""
    if any(token in text for token in ("财报", "收入", "利润", "现金流", "毛利", "负债", "基本盘")):
        return "financial"
    if any(token in text for token in ("预期", "估值", "股价", "研报", "一致预期")):
        return "expectations"
    if any(token in text for token in ("风险", "失效", "证伪")):
        return "risk"
    if any(token in text for token in ("壁垒", "竞争", "客户", "供应商")):
        return "moat"
    return "general"


def _lane_status(row: dict | None) -> tuple[str, str]:
    if not row:
        return "MISSING", "本模式要求该来源，但计划中没有该动作。"
    status = row.get("status") or "pending"
    count = int(row.get("source_count") or 0)
    if count > 0:
        return "PASS", "已打开 {0} 份可读来源。".format(count)
    if status in ("no-readable-source", "no-results", "failed", "unavailable"):
        detail = "已搜索但没有可读来源。"
        if row.get("error_code"):
            detail += " 错误：{0}。".format(row["error_code"])
        return "ATTEMPTED_UNAVAILABLE", detail
    return "MISSING", "来源动作尚未执行完成。"


def _unavailable_if_attempted(row: dict | None) -> str:
    lane_status, _ = _lane_status(row)
    return "ATTEMPTED_UNAVAILABLE" if lane_status == "ATTEMPTED_UNAVAILABLE" else "MISSING"


def _has_evidence(value: object) -> bool:
    if value is None or value is False:
        return False
    if isinstance(value, str):
        cleaned = value.strip()
        return bool(
            cleaned
            and not cleaned.upper().startswith("UNKNOWN")
            and "尚无已核对" not in cleaned
            and not cleaned.startswith("待核对")
        )
    if isinstance(value, dict):
        return any(_has_evidence(item) for item in value.values())
    if isinstance(value, (list, tuple, set)):
        return any(_has_evidence(item) for item in value)
    return True


def _flatten(values: Iterable[object]) -> list:
    rows = []
    for value in values:
        if isinstance(value, list):
            rows.extend(value)
        elif value:
            rows.append(value)
    return rows


def _lane_label(name: str) -> str:
    return {
        "filing-analysis": "财报与公告",
        "management-communication": "管理层交流/业绩会",
        "sell-side-expectations": "卖方研报与盈利预测",
        "market-narrative": "市场叙事与争议",
        "risk-disconfirmation": "反证与风险检查",
    }.get(name, name)


def _item(key: str, label: str, category: str, status: str, detail: str) -> dict:
    return {"key": key, "label": label, "category": category, "status": status, "detail": detail}
