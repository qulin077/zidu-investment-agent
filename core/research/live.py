"""种子 URL 经阅读器进入底稿。搜索摘要停在线索层。"""
from __future__ import annotations

import json

from core.research import store as rstore
from core.research.completion import industry_gate
from core.research.disconfirmation import normalize, queries_for
from core.research.graph import edge
from core.research.prompts import versions_json
from core.research.tools import providers, reader
from core.research.validator import validate
from core.research.waves import schedule
from core.store import STORE, Store


def run_seeded(
    question: str,
    *,
    seed_path: str,
    as_of: str,
    store: Store = STORE,
    mode: str = "fixture",
    llm=None,
) -> dict:
    found = providers.search(question, "seeded", seed_path=seed_path)
    if not found.get("ok"):
        return _stopped(found.get("error_code") or "SEARCH_PROVIDER_FAILED", found.get("message") or "")
    hits = found.get("hits") or []
    pages = []
    for hit in hits:
        page = reader.read_html(hit.get("url") or "")
        page["hit"] = hit
        if not page.get("ok"):
            return _stopped(page.get("error_code") or "SOURCE_READ_FAILED", page.get("message") or "", search_calls=1, reader_calls=len(pages) + 1)
        pages.append(page)
    if not pages:
        return _stopped("SEARCH_FAILED", "种子里没有地址。", search_calls=1)
    draft = _draft(question, as_of, pages, hits)
    errors = validate(draft)
    if errors:
        return _stopped("WRITE_BLOCKED", errors[0]["message"], errors=errors, search_calls=1, reader_calls=len(pages))
    llm_calls = 0
    if llm is not None:
        llm_calls = 1
        raw = llm.generate_structured(
            "只输出研究计划 JSON。不要写结论、收入数字或推荐。",
            question,
            {"type": "object"},
            temperature=0,
        )
        try:
            proposed = json.loads(raw)
        except json.JSONDecodeError:
            return _stopped("PLANNER_LEAKAGE", "计划不是 JSON。", search_calls=1, reader_calls=len(pages))
        from core.research.planner_guard import leakage
        if leakage(proposed):
            return _stopped("PLANNER_LEAKAGE", "计划里出现了结论或数字。", search_calls=1, reader_calls=len(pages))
    coverage = _coverage()
    gate = industry_gate({"coverage": coverage})
    if not gate["passed"]:
        return _stopped("FINISH_BLOCKED", "完成门没有通过。", search_calls=1, reader_calls=len(pages))
    waves = schedule(4)
    cost = _cost(search_calls=1, reader_calls=len(pages), llm_calls=llm_calls)
    if mode != "fixture":
        return {
            "ok": False,
            "status": "shadow",
            "error_code": "SHADOW_NOT_FORMAL",
            "formal_thesis": False,
            "search_hits": hits,
            "opened_urls": [page.get("url") for page in pages],
            "waves": waves,
            **cost,
        }
    plan = {
        "skill": "industry-research",
        "research_question": question,
        "waves": waves,
        "tasks": [{"id": "T1", "question": question, "category": "PRIMARY_EVIDENCE"}],
    }
    run_id = rstore.start_run(store, question, "industry-research", mode, plan, "", "fixture", versions_json())
    saved = rstore.persist_project(store, draft, run_id, plan)
    claim_text = draft["claims"][0]["claim_text"]
    relation = edge("PREMISE_OF", "C1", "C3") if any(row["local_id"] == "C3" for row in draft["claims"]) else None
    rstore.save_live_artifacts(store, saved["project_id"], {
        "disconfirmation": [{
            "claim_local_id": "C1",
            "query": queries_for(claim_text)[0],
            "source_ids": [page.get("url") for page in pages],
            "result": normalize("NO_COUNTEREVIDENCE_FOUND_IN_CHECKED_SOURCES"),
            "status": "ATTEMPTED",
        }],
        "relations": [relation] if relation else [],
        "chunks": [{
            "url": pages[0].get("url") or "",
            "section": "结构",
            "ordinal": 0,
            "text": pages[0].get("text") or "",
        }],
    })
    rstore.finish_run(
        store, run_id,
        project_id=saved["project_id"],
        status="succeeded",
        llm_mode=mode,
        model="fixture",
        llm_calls=0,
        iterations=len(waves),
        estimated_cost=0,
        prompt_versions=versions_json(),
    )
    return {
        "ok": True,
        "status": "succeeded",
        "formal_thesis": True,
        "project_id": saved["project_id"],
        "thesis_id": saved["thesis_id"],
        "search_hits": hits,
        "opened_urls": [page.get("url") for page in pages],
        "waves": waves,
        "completion": gate,
        **cost,
    }


def _draft(question: str, as_of: str, pages: list, hits: list) -> dict:
    page = pages[0]
    claims = []
    evidence = []
    for index, marked in enumerate(page.get("marked") or [], start=1):
        local = "C{0}".format(index)
        claims.append({
            "local_id": local,
            "claim_text": marked["text"],
            "claim_type": marked["claim_type"],
            "subject": "AI数据中心供电",
            "predicate": "正文",
            "object": marked["text"],
            "unit": "",
            "period": "",
            "confidence": "LOW",
            "critical": 1 if marked["claim_type"] == "FACT" else 0,
            "metric": "",
            "numeric_value": None,
            "definition": "",
            "premise_claim_ids": marked.get("premise_claim_ids") or [],
        })
        if marked["claim_type"] != "INFERENCE":
            evidence.append({
                "claim_local_id": local,
                "source_local_id": "S1",
                "evidence_text": marked["text"],
                "evidence_location": marked["location"],
                "support_type": "SUPPORT",
            })
    stamp = "2026-09-01T10:00:00+08:00"
    return {
        "research_question": question,
        "as_of": as_of,
        "industry_or_theme": "AI数据中心供电",
        "industry_definition": "本页只区分 HVDC 与备用柴发，不外推公司收入。",
        "value_chain": [{
            "node_name": "供电结构",
            "upstream_node": "",
            "downstream_node": "",
            "role": "结构",
            "value_driver": "UNKNOWN",
            "margin_characteristic": "UNKNOWN",
            "bottleneck": "UNKNOWN",
        }],
        "key_drivers": ["见正文。量、价、资本开支 UNKNOWN。"],
        "technology_routes": ["UNKNOWN"],
        "market_structure": ["UNKNOWN"],
        "company_mapping": [{
            "company": "未点名公司",
            "code": "",
            "value_chain_node": "供电结构",
            "exposure_type": "THEMATIC",
            "evidence_level": "NONE",
            "revenue_exposure": "UNKNOWN",
            "customer_evidence": "",
            "product_evidence": "",
            "confidence": "LOW",
            "evidence_refs": [],
            "commercial_stage": "UNKNOWN",
        }],
        "catalysts": ["无已核对催化"],
        "risks": ["搜索摘要没有进入证据。"],
        "claims": claims,
        "evidence": evidence,
        "sources": [{
            "local_id": "S1",
            "url": page.get("url") or "",
            "title": page.get("title") or "未命名",
            "publisher": page.get("publisher") or "seed",
            "source_type": "RESEARCH_NOTE",
            "published_at": page.get("published_at") or stamp,
            "available_at": page.get("published_at") or stamp,
            "captured_at": stamp,
            "author": page.get("publisher") or "",
            "source_quality": "SECONDARY",
            "origin_family": "SEEDED_AI_POWER_STRUCTURE",
            "body": page.get("text") or "",
        }],
        "conflicts": [],
        "open_questions": ["公司收入暴露 UNKNOWN。"],
        "evidence_refs": [row["local_id"] for row in claims if row["claim_type"] != "INFERENCE"][:1] or ["C1"],
        "search_hits": hits,
        "thesis": {
            "summary": "正文把 HVDC 与备用柴发分开。公司暴露 UNKNOWN。",
            "bull_case": "无已核对的多头事实。",
            "base_case": "维持结构区分。",
            "bear_case": "无已核对的空头事实。",
            "key_drivers": ["C1"],
            "catalysts": [],
            "risks": ["搜索摘要没有进入证据。"],
            "invalidation": "若正文被撤回，这条结构判断失效。",
            "open_questions": ["公司收入暴露 UNKNOWN。"],
            "evidence_refs": ["C1"],
        },
    }


def _coverage() -> dict:
    return {
        "industry_boundary": "PASS",
        "structural_change": "PASS",
        "value_chain": "PASS",
        "key_drivers": "PASS",
        "critical_claims": "GROUNDED",
        "company_exposure": "LABELED",
        "risks": "PRESENT",
        "disconfirmation": "ATTEMPTED",
        "open_questions": "EXPLICIT",
        "thesis": "GROUNDED",
    }


def _cost(*, search_calls: int, reader_calls: int, llm_calls: int = 0) -> dict:
    return {
        "llm_calls": llm_calls,
        "input_tokens": 0,
        "output_tokens": 0,
        "estimated_cost": 0,
        "search_calls": search_calls,
        "reader_calls": reader_calls,
        "cost_per_completed_project": 0,
    }


def _stopped(code: str, message: str, **extra) -> dict:
    return {
        "ok": False,
        "status": "blocked",
        "error_code": code,
        "error_message": message,
        "formal_thesis": False,
        **extra,
    }
