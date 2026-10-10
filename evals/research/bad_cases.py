"""Curated production bad cases promoted into deterministic regressions."""
from __future__ import annotations

import json
from pathlib import Path

from core.research import company_dossier, event_tracking, source_skills, theme_intake
from core.research.extract import accept_research_span


ROOT = Path(__file__).resolve().parent / "bad_cases"


def load_cases() -> list[dict]:
    rows = []
    for path in sorted(ROOT.glob("*/case.json")):
        row = json.loads(path.read_text(encoding="utf-8"))
        row["_path"] = str(path)
        rows.append(row)
    return rows


def score(case: dict) -> dict:
    contract = case.get("regression_contract") or {}
    failures = []
    routing = contract.get("routing") or {}
    subject = routing.get("subject") or ""
    detailed = contract.get("detailed_prompt") or ""
    generic = contract.get("generic_prompt") or ""
    if routing:
        actual_kind = event_tracking.object_kind(subject, detailed)
        if actual_kind != routing.get("object_kind"):
            failures.append("object_kind={0}".format(actual_kind))
    if generic:
        action = theme_intake.assess(generic, subject).get("action")
        if action != contract.get("generic_action"):
            failures.append("generic_action={0}".format(action))
    if detailed:
        action = theme_intake.assess(detailed, subject).get("action")
        if action != contract.get("detailed_action"):
            failures.append("detailed_action={0}".format(action))
    required = contract.get("required_evidence") or []
    planned = [key for key, _question in event_tracking.plan_tasks(subject, detailed)]
    missing = [key for key in required if key not in planned]
    if missing:
        failures.append("missing_evidence={0}".format(",".join(missing)))
    company = contract.get("company_expectations") or {}
    if company:
        name = company.get("name") or "公司"
        ticker = company.get("ticker") or ""
        lanes = source_skills.plan(name, ticker, research_mode="FULL_DOSSIER")
        sell_side = next((row for row in lanes if row.get("name") == "sell-side-expectations"), {})
        query_blob = " ".join(sell_side.get("queries") or [])
        for token in company.get("required_query_tokens") or []:
            if token not in query_blob:
                failures.append("missing_query_token={0}".format(token))
        target_text = company.get("target_price_evidence") or ""
        if target_text and not accept_research_span(target_text, "company"):
            failures.append("target_price_evidence_filtered")
        direct_advice = company.get("direct_advice") or ""
        if direct_advice and accept_research_span(direct_advice, "company"):
            failures.append("direct_advice_accepted")
        dossier = company_dossier.build(
            name=name, ticker=ticker,
            claims=company.get("claims") or [], sources=company.get("sources") or [],
            delta={"first_research": True, "added_claims": []}, quote={},
        )
        timeline = (dossier.get("expectations") or {}).get("revision_timeline") or []
        if len(timeline) < int(company.get("minimum_timeline_rows") or 0):
            failures.append("expectation_timeline_too_short={0}".format(len(timeline)))
        expected_latest = company.get("expected_latest_date") or ""
        if expected_latest and (not timeline or timeline[0].get("date") != expected_latest):
            failures.append("latest_expectation_date={0}".format(
                timeline[0].get("date") if timeline else "missing",
            ))
    return {
        "id": case.get("id") or "bad-case",
        "name": case.get("title") or case.get("id") or "bad case",
        "ok": not failures,
        "detail": "; ".join(failures),
    }
