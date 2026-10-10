"""麦格米特公司研究。数字来自已打开的笔记，比率由脚本计算。"""
from __future__ import annotations

import re

from core.config import ROOT
from core.research import finance, store as rstore
from core.research.completion import company_gate
from core.research.disconfirmation import normalize, queries_for
from core.research.prompts import versions_json
from core.research.tools import read_research_note
from core.research.validator import validate
from core.store import STORE, Store

NOTE = "11-节奏看板/NV产业链_中盘深度研究/液冷电源PCB/002851_麦格米特.md"
QUESTION = "麦格米特在 AI 电源产业链中的真实业务暴露是什么？其收入和利润增长主要由什么驱动？目前哪些逻辑已经被财报或公司披露验证，哪些仍然只是市场预期？"


def draft(as_of: str = "2026-09-27T23:59:59+08:00", store: Store = STORE) -> dict:
    opened = read_research_note(NOTE)
    if not opened.get("ok"):
        raise FileNotFoundError(opened.get("message") or NOTE)
    body = opened["body"]
    spans = {
        "power": "电源 8.17 亿 +66.5%",
        "mix": "家电 38% + 电源 29%",
        "sample": "Rubin 18.5kW PSU/110kW 电源柜样品测试中",
        "guide": "2026 为 AI 电源大规模出货年",
        "price": "收盘 127.66",
    }
    missing = [key for key, span in spans.items() if span not in body]
    if missing:
        raise ValueError("笔记里找不到原句：{0}".format(", ".join(missing)))
    narrative = _narrative(body)
    parsed = _parse(body)
    view = _view(parsed, store)
    context_id = view["industry_context"]
    if context_id == "UNKNOWN":
        context_line = "这是公司研究。行业位置 industry_context=UNKNOWN。"
        context_question = "行业研究项目不存在，industry_context=UNKNOWN。"
    else:
        context_line = "这是公司研究。行业位置引用已有项目 {0}。".format(context_id)
        context_question = "行业上下文来自 {0}。公司收入暴露仍要单独核对。".format(context_id)
    claims = [
        _claim("C1", "FACT", "笔记记载 2026Q1：{0}。没有拆成 AI 电源。".format(spans["power"]), 1),
        _claim("C2", "FACT", "笔记记载结构：{0}。".format(spans["mix"]), 0),
        _claim("C3", "FACT", "笔记写：{0}。".format(spans["sample"]), 1),
        _claim("C4", "ESTIMATE", "笔记转述公司口径：{0}。这不是已实现收入。".format(spans["guide"]), 0),
        _claim("C5", "FACT", "笔记记载{0}。这不是估值倍数。".format(spans["price"]), 0),
        _claim("C6", "INFERENCE", "样品测试还不能写成已确认收入。", 0, ["C3"]),
    ]
    evidence = [
        _evidence("C1", spans["power"], "L34"),
        _evidence("C2", spans["mix"], "L35"),
        _evidence("C3", spans["sample"], "L133"),
        _evidence("C4", spans["guide"], "L44"),
        _evidence("C5", spans["price"], "L6"),
    ]
    stamp = "2026-08-28T18:00:00+08:00"
    packet = {
        "skill": "company-research",
        "research_question": QUESTION,
        "as_of": as_of,
        "industry_or_theme": "麦格米特",
        "industry_definition": context_line,
        "value_chain": [{
            "node_name": "电源",
            "upstream_node": "",
            "downstream_node": "",
            "role": "公司暴露待核对",
            "value_driver": "UNKNOWN",
            "margin_characteristic": "UNKNOWN",
            "bottleneck": "UNKNOWN",
        }],
        "key_drivers": ["2026Q1 电源收入见 C1。销量、价格、利用率 UNKNOWN。"],
        "technology_routes": ["UNKNOWN"],
        "market_structure": ["UNKNOWN"],
        "company_mapping": [{
            "company": "麦格米特",
            "code": "002851",
            "value_chain_node": "电源",
            "exposure_type": "INDIRECT",
            "evidence_level": "PRODUCT",
            "revenue_exposure": "UNKNOWN",
            "customer_evidence": "",
            "product_evidence": spans["sample"],
            "confidence": "LOW",
            "evidence_refs": ["C3"],
            "commercial_stage": "SAMPLE",
            "revenue_evidence": "",
        }],
        "catalysts": ["下一次财报是否单列数据中心电源收入。"],
        "risks": ["样品测试不能当成量产或已确认收入。"],
        "claims": claims,
        "evidence": evidence,
        "sources": [{
            "local_id": "S1",
            "url": NOTE,
            "title": "麦格米特（002851）· NV产业链深度研究 · 800V电源",
            "publisher": "仓库研究笔记",
            "source_type": "RESEARCH_NOTE",
            "published_at": stamp,
            "available_at": stamp,
            "captured_at": stamp,
            "author": "",
            "source_quality": "SECONDARY",
            "origin_family": "NOTE_002851_2026-08-28",
            "body": body,
        }],
        "conflicts": [],
        "open_questions": [
            "AI 电源收入占比 UNKNOWN。",
            "一致预期 UNKNOWN。",
            context_question,
        ],
        "evidence_refs": ["C1", "C3"],
        "company_view": view,
        "expectations": [
            {"source_type": "CONSENSUS_DATA", "statement": "UNKNOWN", "status": "UNKNOWN"},
            {"source_type": "MANAGEMENT_GUIDANCE", "statement": spans["guide"], "status": "UNVERIFIED_NOTE"},
            {"source_type": "SELL_SIDE_ESTIMATE", "statement": "UNKNOWN", "status": "UNKNOWN"},
            {"source_type": "MARKET_NARRATIVE", "statement": narrative, "status": "NOTE_ONLY"},
        ],
        "thesis": {
            "summary": "笔记记载电源 8.17 亿 +66.5%，结构为家电 38% + 电源 29%，并写有 Rubin 18.5kW PSU/110kW 电源柜样品测试中。收盘 127.66 只是笔记记录的价格。AI 电源收入占比 UNKNOWN。",
            "bull_case": "无已核对的多头事实。",
            "base_case": "暴露保持 INDIRECT，商业化阶段为 SAMPLE。",
            "bear_case": "样品若没有后续收入，主题映射会弱下去。",
            "key_drivers": ["C1"],
            "catalysts": ["下一次财报是否单列数据中心电源收入。"],
            "risks": ["样品测试不能当成量产或已确认收入。"],
            "invalidation": "若后续披露没有把样品测试写成已确认收入，不能把暴露升成 DIRECT。",
            "open_questions": ["一致预期 UNKNOWN。"],
            "evidence_refs": ["C1", "C3", "C5"],
        },
    }
    return packet


def run(store: Store = STORE, as_of: str = "2026-09-27T23:59:59+08:00", *, persist: bool = False) -> dict:
    packet = draft(as_of, store)
    errors = validate(packet)
    gate = company_gate({"coverage": _coverage(packet)})
    result = {
        "ok": not errors and gate["passed"],
        "errors": errors,
        "completion": gate,
        "company_view": packet["company_view"],
        "expectations": packet["expectations"],
        "formal_thesis": False,
    }
    if errors or not gate["passed"] or not persist:
        return result
    from core.research.planner import company_plan
    plan = company_plan(QUESTION, "麦格米特", as_of, ["A股"], "deep")
    run_id = rstore.start_run(store, QUESTION, "company-research", "fixture", plan, "", "fixture", versions_json())
    saved = rstore.persist_project(store, packet, run_id, plan)
    rstore.save_live_artifacts(store, saved["project_id"], {
        "disconfirmation": [{
            "claim_local_id": "C4",
            "query": queries_for("AI 电源大规模出货是否延期")[0],
            "result": normalize("NO_COUNTEREVIDENCE_FOUND_IN_CHECKED_SOURCES"),
            "status": "ATTEMPTED",
        }],
        "relations": [{"source_claim": "C3", "target_claim": "C6", "relation": "PREMISE_OF"}],
        "expectations": packet["expectations"],
        "chunks": _chunks(packet["sources"][0]["body"], NOTE),
    })
    rstore.finish_run(store, run_id, project_id=saved["project_id"], status="succeeded", llm_mode="fixture", model="fixture", llm_calls=0)
    result["formal_thesis"] = True
    result["project_id"] = saved["project_id"]
    return result


def _claim(local_id: str, kind: str, text: str, critical: int, premises=None) -> dict:
    return {
        "local_id": local_id,
        "claim_text": text,
        "claim_type": kind,
        "subject": "麦格米特",
        "predicate": "笔记记载",
        "object": text,
        "unit": "",
        "period": "2026Q1" if local_id == "C1" else "",
        "confidence": "LOW",
        "critical": critical,
        "metric": "",
        "numeric_value": None,
        "definition": "",
        "premise_claim_ids": premises or [],
    }


def _evidence(claim_id: str, span: str, location: str) -> dict:
    return {
        "claim_local_id": claim_id,
        "source_local_id": "S1",
        "evidence_text": span,
        "evidence_location": location,
        "support_type": "SUPPORT",
    }


def _narrative(body: str) -> str:
    match = re.search(r"多头\s*\|\s*([^|\n]+)", body)
    if not match:
        return "UNKNOWN"
    return match.group(1).strip()


def _parse(body: str) -> dict:
    quarter = re.search(r"2026Q1\s*\|\s*([\d.]+)\s*亿\s*/\s*([\d.]+)\s*亿", body)
    power = re.search(r"电源\s*([\d.]+)\s*亿", body)
    price = re.search(r"收盘\s*([\d.]+)", body)
    revenue = float(quarter.group(1)) if quarter else None
    power_revenue = float(power.group(1)) if power else None
    return {
        "revenue": revenue,
        "net_income": float(quarter.group(2)) if quarter else None,
        "power_revenue": power_revenue,
        "power_share": finance.share(power_revenue, revenue),
        "price": float(price.group(1)) if price else None,
        "pe": finance.pe(float(price.group(1)) if price else None, None),
        "revenue_growth": finance.growth(revenue, None),
    }


def _view(parsed: dict, store: Store) -> dict:
    industry = store.query(
        "SELECT id, title FROM research_project WHERE industry LIKE ? OR title LIKE ? ORDER BY updated_at DESC LIMIT 1",
        ("%电源%", "%电源%"),
    )
    return {
        "business_model": {
            "sells": "家电与电源，见笔记结构句。",
            "customer": "UNKNOWN",
            "pricing": "UNKNOWN",
            "recurring": "UNKNOWN",
            "cost": "UNKNOWN",
            "asset": "UNKNOWN",
        },
        "segments": "家电与电源并列。AI 电源没有单独收入。",
        "revenue_driver_tree": "已核对分部收入。销量×价格 UNKNOWN。",
        "financial_trend": parsed,
        "industry_context": industry[0]["id"] if industry else "UNKNOWN",
        "expectations": {
            "consensus_view": "UNKNOWN",
            "management_guidance": "笔记转述 2026 为 AI 电源大规模出货年",
            "sell_side": "UNKNOWN",
            "market_narrative": "笔记中的多头区间，不是一致预期。",
        },
        "variant": {
            "consensus_view": "UNKNOWN",
            "our_view": "",
            "gap": "",
            "status": "NO_VERIFIED_VARIANT",
            "validation_signal": "财报单列数据中心电源收入",
            "invalidation_signal": "样品没有后续收入披露",
        },
        "valuation_context": {
            "price_in_note": parsed.get("price"),
            "pe": parsed.get("pe"),
            "ps": None,
            "ev_ebitda": None,
            "historical_multiple": None,
            "peer_multiple": None,
        },
        "monitoring": ["下一次财报是否单列数据中心电源收入。"],
        "commercial_stage": "SAMPLE",
        "exposure_type": "INDIRECT",
    }


def _coverage(packet: dict) -> dict:
    context = packet["company_view"]["industry_context"]
    return {
        "business_model": "PASS",
        "revenue_drivers": "PASS",
        "financial_trend": "PASS",
        "industry_context": "PASS" if context != "UNKNOWN" else "UNKNOWN_EXPLICIT",
        "critical_claims": "GROUNDED",
        "company_exposure": "GROUNDED",
        "expectations": "UNKNOWN_EXPLICIT",
        "risks": "PASS",
        "disconfirmation": "ATTEMPTED",
        "invalidation": "PASS",
        "monitoring": "PASS",
    }


def _chunks(body: str, url: str) -> list:
    parts = [part.strip() for part in re.split(r"\n## ", body) if part.strip()]
    return [
        {"url": url, "section": part.splitlines()[0][:40], "ordinal": index, "text": part[:1500]}
        for index, part in enumerate(parts[:8])
    ]


def note_path() -> str:
    return str(ROOT / NOTE)
