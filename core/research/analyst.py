"""Cross-source research synthesis performed by the analysis model.

The deterministic layer defines the research contract and verifies citations.
It must not substitute keyword matching for the analyst's interpretation of
what the sources jointly mean.
"""
from __future__ import annotations

import json
from typing import Iterable


FRAMEWORK_LABELS = {
    # Company
    "BUSINESS_MODEL": "公司基本盘与商业模式",
    "MOAT": "核心壁垒",
    "GROWTH_PROFIT": "增长变量与利润驱动",
    "EXPECTATIONS": "管理层、卖方与市场预期",
    "PRICE_EXPECTATION_GAP": "股价与预期差",
    "CATALYST": "可核对催化剂",
    "CHANGES": "事实、预期与判断变化",
    "RISK_INVALIDATION": "风险与失效条件",
    "MONITORING": "下一步监控",
    # Industry
    "INDUSTRY_BOUNDARY": "行业边界与基本逻辑",
    "REFERENCE_CLASS": "历史基准与生命周期",
    "VALUE_CHAIN": "产业链与价值传导",
    "STRUCTURAL_CHANGE": "结构变化与行业阶段",
    "CAUSAL_MODEL": "叙事到数字的因果模型",
    "TECHNOLOGY_ROUTE": "技术路线与商业化阶段",
    "POLICY_SUPPLY_CHAIN": "政策、产地与供应链约束",
    "VALUE_MIGRATION": "价值量与利润池迁移",
    "ECONOMICS": "供需量价成本",
    "CAPITAL_ECONOMICS": "资本回报与增长质量",
    "COMPETITION": "竞争格局与核心瓶颈",
    "EARNINGS_TRACKING": "公司业绩验证",
    "IMPLIED_EXPECTATIONS": "市场隐含预期与兑现门槛",
    "SCENARIOS": "条件化情景",
    "RISK": "风险与反证",
    # Event / theme
    "EVENT_DEFINITION": "事件定义",
    "BASELINE": "事件前基线",
    "STATUS_STAGE": "当前阶段",
    "WHAT_CHANGED": "真正增量",
    "DEFINITION_SCOPE": "定义与边界",
    "ORIGIN_BASELINE": "起源与历史基线",
    "TIMELINE": "演化时间线",
    "CURRENT_CATALYSTS": "近期直接催化",
    "ACTOR_MAP": "关键主体与行动",
    "TECHNICAL_POLICY_TRACKS": "技术与政策分支",
    "CAUSAL_CHAIN": "逻辑与影响传导",
    "ECONOMIC_VARIABLES": "经济变量",
    "AFFECTED_NODES": "产业与板块影响",
    "MARKET_NARRATIVE": "市场叙事与事实差",
    "EXPECTATION_DELTA": "预期变化",
    "MILESTONES": "下一验证点",
    "EARNINGS_LINK": "业绩兑现链",
}

COMPANY_FRAMEWORK = (
    "BUSINESS_MODEL", "MOAT", "GROWTH_PROFIT", "EXPECTATIONS",
    "PRICE_EXPECTATION_GAP", "CATALYST", "CHANGES", "RISK_INVALIDATION", "MONITORING",
)


def framework(required: Iterable[str] | None, skill: str) -> list[dict]:
    keys = list(required or ())
    if skill == "company-research":
        keys = list(COMPANY_FRAMEWORK)
    return [{"key": key, "title": FRAMEWORK_LABELS.get(key, key)} for key in keys]


def synthesize(
    model, *, question: str, subject: str, skill: str, claims: list,
    sources: list, required: Iterable[str] | None = None, previous: dict | None = None,
) -> tuple[dict | None, int, bool]:
    """Ask the strong model to interpret all accepted evidence together.

    Facts remain citation-locked to accepted claim ids. The model can produce
    explicit inference, but cannot silently turn an inference into a fact.
    """
    if model is None or not claims:
        return None, 0, False
    research_framework = framework(required, skill)
    allowed_keys = {row["key"] for row in research_framework}
    claim_rows = [
        {
            "id": row.get("local_id"),
            "type": row.get("claim_type") or "FACT",
            "text": row.get("text") or row.get("evidence_text") or "",
            "evidence": row.get("evidence_text") or "",
            "source_id": row.get("source_id") or "",
            "period": row.get("period") or "",
        }
        for row in claims if row.get("local_id")
    ][:120]
    source_rows = [
        {
            "id": row.get("local_id") or row.get("id") or "",
            "title": row.get("title") or "",
            "publisher": row.get("publisher") or "",
            "published_at": row.get("published_at") or "",
            "tier": row.get("tier") or 3,
        }
        for row in sources
    ][:80]
    system = (
        "你是买方研究团队的主分析师。Reader 已经逐篇阅读来源并生成了带原文引用的 claims。"
        "你的任务不是机械分类，而是跨来源比较、识别时间顺序、解释因果链、区分事实/预期/叙事，"
        "并回答用户真正关心的问题。只能使用 input_claims；不得使用模型记忆补事实。"
        "每一个事实判断必须列出 supporting_claim_ids。允许做推论，但必须明确写成分析判断，"
        "并列出作为前提的 claim ids。相互冲突的材料必须指出，不能强行合并。"
        "claim id 只放在 supporting_claim_ids / claim_ids 数组里，不要写进 analysis 等自然语言字段。"
        "coverage 不是关键词命中：SUPPORTED 代表 claims 足以直接回答该模块；PARTIAL 代表只能回答一部分；"
        "MISSING 代表没有足够证据。SUPPORTED 必须至少有一个有效 claim id。"
        "如果 previous_dossier_summary 非空，key_changes 必须比较旧判断与当前证据，分别说明保留、增强、"
        "削弱、反转或新增；不得把旧档案里已经存在的事实冒充为本轮新增变化。"
        "不要给出你自己的买卖、仓位或目标价建议；允许并且应当比较 input_claims 中具名机构已发布的"
        "目标价、评级和盈利预测，明确它们只是卖方预期及其修订。输出 JSON：executive_summary、key_changes、sections、"
        "causal_chain、contradictions、next_questions、coverage。"
        "sections 每项包含 key、title、analysis、analysis_type(FACT_SYNTHESIS/INFERENCE)、"
        "supporting_claim_ids、confidence(HIGH/MEDIUM/LOW)。"
        "coverage 每项包含 key、status(SUPPORTED/PARTIAL/MISSING)、claim_ids、reason。"
    )
    payload = {
        "question": question,
        "subject": subject,
        "research_type": skill,
        "framework": research_framework,
        "previous_dossier_summary": _previous_summary(previous or {}),
        "sources": source_rows,
        "input_claims": claim_rows,
    }
    try:
        raw = model.generate_structured(
            system, json.dumps(payload, ensure_ascii=False), {"type": "object"},
            temperature=0, timeout=120,
        )
        data = json.loads(raw) if isinstance(raw, str) else dict(raw or {})
    except Exception:
        return None, 1, True
    known = {row["id"] for row in claim_rows}
    sections = []
    for row in data.get("sections") or []:
        if not isinstance(row, dict) or row.get("key") not in allowed_keys:
            continue
        refs = _valid_ids(row.get("supporting_claim_ids"), known)
        analysis = _as_prose(row.get("analysis"))
        if not analysis or not refs:
            continue
        sections.append({
            "key": row["key"],
            "title": _as_prose(row.get("title")) or FRAMEWORK_LABELS.get(row["key"], row["key"]),
            "analysis": analysis,
            "analysis_type": row.get("analysis_type") if row.get("analysis_type") in ("FACT_SYNTHESIS", "INFERENCE") else "INFERENCE",
            "claim_ids": refs,
            "confidence": row.get("confidence") if row.get("confidence") in ("HIGH", "MEDIUM", "LOW") else "MEDIUM",
        })
    coverage = {}
    raw_coverage = data.get("coverage") or []
    if isinstance(raw_coverage, dict):
        coverage_rows = []
        for key, value in raw_coverage.items():
            row = dict(value) if isinstance(value, dict) else {"status": value}
            row["key"] = key
            coverage_rows.append(row)
    else:
        coverage_rows = raw_coverage
    for row in coverage_rows:
        if not isinstance(row, dict) or row.get("key") not in allowed_keys:
            continue
        refs = _valid_ids(row.get("claim_ids"), known)
        status = row.get("status") if row.get("status") in ("SUPPORTED", "PARTIAL", "MISSING") else "MISSING"
        if status == "SUPPORTED" and not refs:
            status = "MISSING"
        coverage[row["key"]] = {
            "status": status, "claim_ids": refs,
            "reason": _as_prose(row.get("reason")),
        }
    view = {
        "model": getattr(model, "name", "analysis-model"),
        "executive_summary": _as_prose(data.get("executive_summary")),
        "key_changes": _strings(data.get("key_changes"), 8),
        "sections": sections,
        "causal_chain": _strings(data.get("causal_chain"), 8),
        "contradictions": _strings(data.get("contradictions"), 8),
        "next_questions": _strings(data.get("next_questions"), 10),
        "coverage": coverage,
    }
    if not view["executive_summary"] and not sections:
        return None, 1, True
    return view, 1, False


def apply_view(dossier: dict, view: dict | None, claims: list, field_map: dict[str, str] | None = None) -> dict:
    if not view:
        return dossier
    result = dict(dossier)
    result["analyst_view"] = view
    if view.get("executive_summary"):
        result["one_line_view"] = view["executive_summary"]
    mapping = field_map or {}
    claim_map = {row.get("local_id"): row for row in claims if row.get("local_id")}
    coverage = dict(result.get("coverage") or {})
    for key, decision in (view.get("coverage") or {}).items():
        status = decision.get("status")
        if status not in ("SUPPORTED", "PARTIAL"):
            continue
        refs = [item for item in decision.get("claim_ids") or [] if item in claim_map]
        if not refs:
            continue
        if status == "SUPPORTED":
            coverage[key] = True
        field = mapping.get(key)
        if field:
            existing = list(result.get(field) or [])
            seen = {row.get("claim_id") for row in existing if isinstance(row, dict)}
            for claim_id in refs:
                if claim_id in seen:
                    continue
                claim = claim_map[claim_id]
                existing.append({
                    "text": claim.get("text") or claim.get("evidence_text") or "",
                    "claim_id": claim_id,
                    "source_id": claim.get("source_id") or "",
                    "claim_type": claim.get("claim_type") or "FACT",
                    "period": claim.get("period") or "",
                })
            result[field] = existing
    if coverage:
        result["coverage"] = coverage
        required = list(result.get("required_evidence") or coverage.keys())
        result["open_questions"] = [key for key in required if not coverage.get(key)]
    return result


def _valid_ids(values, known: set[str]) -> list[str]:
    result = []
    for value in values or []:
        if value in known and value not in result:
            result.append(value)
    return result


def _strings(values, limit: int) -> list[str]:
    rows = values if isinstance(values, list) else ([values] if values else [])
    result = []
    for value in rows:
        if isinstance(value, dict):
            value = (
                value.get("change") or value.get("step") or value.get("description")
                or value.get("text") or value.get("analysis") or ""
            )
        text = _as_prose(value)
        if text:
            result.append(text)
    return result[:limit]


def _as_prose(value) -> str:
    if isinstance(value, (str, int, float)):
        return str(value).strip()
    if isinstance(value, list):
        return "；".join(_as_prose(item) for item in value if _as_prose(item))
    return ""


def _previous_summary(previous: dict) -> dict:
    result = {
        "one_line_view": previous.get("one_line_view") or "",
        "state": previous.get("state") or "",
        "open_questions": previous.get("open_questions") or [],
    }
    # Give the analyst enough of the old dossier to compare judgments instead
    # of treating a re-analysis as first-time research.  Claims are still the
    # only allowed source of facts; this snapshot is comparison context only.
    for key in (
        "company_basics", "moat", "core_thesis", "expectations",
        "price_and_expectations", "changes", "risks_and_invalidation", "monitoring",
    ):
        value = previous.get(key)
        if value not in (None, "", [], {}):
            result[key] = value
    return result
