"""研究底稿的写入。Thesis 只追加版本。"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Dict, List, Optional

from core.context.temporal import CN_TZ
from core.research import conflicts as conflict_mod
from core.research.claims import derive_status, evidence_for
from core.research.render import loads
from core.research.thesis import classify_diff
from core.research.types import OUTPUT_KEYS
from core.store import STORE, Store


def now_iso() -> str:
    return datetime.now(CN_TZ).isoformat(timespec="seconds")


def dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False)


def _count(conn, table: str) -> int:
    return int(conn.execute("SELECT COUNT(*) FROM {0}".format(table)).fetchone()[0])


def _ids(conn, table: str, prefix: str, n: int) -> List[str]:
    start = _count(conn, table)
    return ["{0}-{1:04d}".format(prefix, start + index + 1) for index in range(n)]


def start_run(store: Store, question: str, skill: str, mode: str, plan: dict, raw: str, model: str, prompt_versions: str) -> str:
    with store.connect() as conn:
        run_id = _ids(conn, "research_run", "RR", 1)[0]
        conn.execute(
            """INSERT INTO research_run
               (id, project_id, skill, question, started_at, status, mode, model,
                prompt_versions, temperature, tool_calls, tool_log_json, llm_calls,
                tokens, cost, error_code, error_message, raw_output, parsed_output, plan_json)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                run_id, "", skill, question, now_iso(), "running", mode, model,
                prompt_versions, 0, 0, "[]", 0,
                None, None, "", "", raw, "", dumps(plan.get("steps") or []),
            ),
        )
    return run_id


def finish_run(store: Store, run_id: str, **fields) -> None:
    allowed = {
        "project_id", "finished_at", "status", "model", "prompt_versions", "temperature",
        "tool_calls", "tool_log_json", "llm_calls", "tokens", "cost", "error_code",
        "error_message", "raw_output", "parsed_output", "plan_json",
        "llm_mode", "iterations", "input_tokens", "output_tokens", "estimated_cost", "question_id",
    }
    fields["finished_at"] = fields.get("finished_at") or now_iso()
    keys = [key for key in fields if key in allowed]
    if not keys:
        return
    sql = "UPDATE research_run SET {0} WHERE id = ?".format(", ".join("{0} = ?".format(key) for key in keys))
    with store.connect() as conn:
        conn.execute(sql, tuple(fields[key] for key in keys) + (run_id,))


def persist_project(store: Store, draft: dict, run_id: str, plan: dict) -> dict:
    """校验已通过。一次事务写入项目、证据和 Thesis v1。"""
    stamp = now_iso()
    claims = list(draft.get("claims") or [])
    sources = list(draft.get("sources") or [])
    evidence = list(draft.get("evidence") or [])
    chain = list(draft.get("value_chain") or [])
    mapping = list(draft.get("company_mapping") or [])
    questions = list(draft.get("open_questions") or [])
    detected = conflict_mod.detect(claims)
    with store.connect() as conn:
        project_id = _ids(conn, "research_project", "RP", 1)[0]
        question_id = _ids(conn, "research_question", "RQ", 1)[0]
        plan_id = _ids(conn, "research_plan", "RN", 1)[0]
        source_ids = _ids(conn, "research_source", "RS", len(sources))
        claim_ids = _ids(conn, "research_claim", "RC", len(claims))
        evidence_ids = _ids(conn, "research_evidence", "RE", len(evidence))
        conflict_ids = _ids(conn, "research_conflict", "RX", len(detected))
        node_ids = _ids(conn, "research_value_chain", "VN", len(chain))
        map_ids = _ids(conn, "research_company_mapping", "RM", len(mapping))
        open_ids = _ids(conn, "research_open_question", "RO", len(questions))
        thesis_id = _ids(conn, "research_thesis", "RT", 1)[0]

        source_of = {row.get("local_id"): source_ids[index] for index, row in enumerate(sources)}
        claim_of = {row.get("local_id"): claim_ids[index] for index, row in enumerate(claims)}
        map_json = {
            "industry_definition": draft.get("industry_definition") or "",
            "key_drivers": draft.get("key_drivers") or [],
            "technology_routes": draft.get("technology_routes") or [],
            "market_structure": draft.get("market_structure") or [],
        }
        if draft.get("company_view"):
            map_json["company_view"] = draft.get("company_view")
        if draft.get("skill"):
            map_json["skill"] = draft.get("skill")
        title = draft.get("industry_or_theme") or draft.get("research_question") or project_id
        conn.execute(
            """INSERT INTO research_project
               (id, title, industry, scope, status, industry_definition, map_json, created_at, updated_at, created_by)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                project_id, title, draft.get("industry_or_theme") or "",
                dumps(draft.get("market_scope") or []), "OPEN",
                draft.get("industry_definition") or "", dumps(map_json), stamp, stamp, "research",
            ),
        )
        conn.execute(
            """INSERT INTO research_question
               (id, project_id, question, status, priority, user_context, created_at, resolved_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (
                question_id, project_id, draft.get("research_question") or "", "OPEN", 1,
                (draft.get("user_context") or "")[:500], stamp, "",
            ),
        )
        conn.execute(
            "INSERT INTO research_plan (id, project_id, run_id, steps_json, created_at) VALUES (?,?,?,?,?)",
            (plan_id, project_id, run_id, dumps(plan), stamp),
        )
        for index, row in enumerate(sources):
            conn.execute(
                """INSERT INTO research_source
                   (id, project_id, url, title, publisher, source_type, published_at, available_at,
                    captured_at, author, source_quality, body, origin_family)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    source_ids[index], project_id, row.get("url") or "", row.get("title") or "",
                    row.get("publisher") or "", row.get("source_type") or "",
                    row.get("published_at") or "", row.get("available_at") or "",
                    row.get("captured_at") or stamp, row.get("author") or "",
                    row.get("source_quality") or "", row.get("body") or "",
                    row.get("origin_family") or "",
                ),
            )
        for index, row in enumerate(claims):
            linked = evidence_for(row.get("local_id"), evidence)
            for item in linked:
                item["source_id"] = source_of.get(item.get("source_local_id"))
            status = derive_status(linked)
            if (row.get("claim_type") or "") == "INFERENCE" and status == "REJECTED":
                status = "SINGLE_SOURCE"
            premises = [claim_of[item] for item in (row.get("premise_claim_ids") or []) if item in claim_of]
            conn.execute(
                """INSERT INTO research_claim
                   (id, project_id, local_id, claim_text, claim_type, subject, predicate, object,
                    unit, period, confidence, status, critical, metric, numeric_value, definition,
                    premise_claim_ids, created_at, run_id)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    claim_ids[index], project_id, row.get("local_id") or "", row.get("claim_text") or "",
                    row.get("claim_type") or "", row.get("subject") or "", row.get("predicate") or "",
                    row.get("object") or "", row.get("unit") or "", row.get("period") or "",
                    row.get("confidence") or "LOW", status, int(row.get("critical") or 0),
                    row.get("metric") or "", row.get("numeric_value"), row.get("definition") or "",
                    dumps(premises), stamp, run_id,
                ),
            )
        for index, row in enumerate(evidence):
            conn.execute(
                """INSERT INTO research_evidence
                   (id, claim_id, source_id, evidence_text, evidence_location, support_type, captured_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (
                    evidence_ids[index], claim_of[row.get("claim_local_id")],
                    source_of[row.get("source_local_id")], row.get("evidence_text") or "",
                    row.get("evidence_location") or "", row.get("support_type") or "SUPPORT",
                    stamp,
                ),
            )
        for index, row in enumerate(detected):
            linked_claims = [
                claim_of[item] for item in (row.get("claim_local_ids") or row.get("claim_ids") or []) if item in claim_of
            ]
            conn.execute(
                """INSERT INTO research_conflict
                   (id, project_id, metric, value_a, definition_a, value_b, definition_b,
                    possible_reason, status, created_at, topic, claim_ids)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    conflict_ids[index], project_id, row.get("metric") or "", row.get("value_a") or "",
                    row.get("definition_a") or "", row.get("value_b") or "", row.get("definition_b") or "",
                    row.get("possible_reason") or "", "OPEN", stamp,
                    row.get("topic") or row.get("metric") or "", dumps(linked_claims),
                ),
            )
        for index, row in enumerate(chain):
            node_refs = [claim_of[item] for item in (row.get("evidence_refs") or []) if item in claim_of]
            conn.execute(
                """INSERT INTO research_value_chain
                   (id, project_id, node_name, upstream_node, downstream_node, role, value_driver,
                    margin_characteristic, bottleneck, parent_node, evidence_refs)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    node_ids[index], project_id, row.get("node_name") or "", row.get("upstream_node") or "",
                    row.get("downstream_node") or "", row.get("role") or "", row.get("value_driver") or "",
                    row.get("margin_characteristic") or "UNKNOWN", row.get("bottleneck") or "UNKNOWN",
                    row.get("parent_node") or row.get("upstream_node") or "", dumps(node_refs),
                ),
            )
        for index, row in enumerate(mapping):
            refs = [claim_of[item] for item in (row.get("evidence_refs") or []) if item in claim_of]
            conn.execute(
                """INSERT INTO research_company_mapping
                   (id, project_id, company, code, value_chain_node, exposure_type, evidence_level,
                    revenue_exposure, customer_evidence, product_evidence, confidence, evidence_refs,
                    revenue_evidence, commercial_stage)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    map_ids[index], project_id, row.get("company") or "", row.get("code") or "",
                    row.get("value_chain_node") or "", row.get("exposure_type") or "UNKNOWN",
                    row.get("evidence_level") or "NONE", row.get("revenue_exposure") or "UNKNOWN",
                    row.get("customer_evidence") or "", row.get("product_evidence") or "",
                    row.get("confidence") or "LOW", dumps(refs),
                    row.get("revenue_evidence") or "",
                    row.get("commercial_stage") or "UNKNOWN",
                ),
            )
        for index, text in enumerate(questions):
            conn.execute(
                """INSERT INTO research_open_question
                   (id, project_id, thesis_version, question, status, created_at)
                   VALUES (?,?,?,?,?,?)""",
                (open_ids[index], project_id, 1, text, "OPEN", stamp),
            )
        thesis = draft.get("thesis") or {}
        refs = [claim_of[item] for item in (thesis.get("evidence_refs") or []) if item in claim_of]
        conn.execute(
            """INSERT INTO research_thesis
               (id, project_id, version, summary, bull_case, base_case, bear_case, key_drivers_json,
                catalysts_json, risks_json, invalidation, open_questions_json, evidence_refs_json,
                map_json, diff_verdict, diff_json, as_of, status, created_at, invalidation_json)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                thesis_id, project_id, 1, thesis.get("summary") or "", thesis.get("bull_case") or "",
                thesis.get("base_case") or "", thesis.get("bear_case") or "",
                dumps(thesis.get("key_drivers") or []), dumps(thesis.get("catalysts") or draft.get("catalysts") or []),
                dumps(thesis.get("risks") or draft.get("risks") or []), thesis.get("invalidation") or "",
                dumps(thesis.get("open_questions") or questions), dumps(refs), dumps(map_json),
                "", "{}", draft.get("as_of") or "", "SAVED", stamp,
                dumps(thesis.get("invalidation_points") or ([thesis.get("invalidation")] if thesis.get("invalidation") else [])),
            ),
        )
    return {"project_id": project_id, "thesis_id": thesis_id, "thesis_version": 1, "question_id": question_id}


def append_thesis_version(store: Store, project_id: str, thesis_id: str, fields: dict, as_of: str, invalidated: bool = False) -> dict:
    current = store.query(
        "SELECT * FROM research_thesis WHERE project_id = ? AND id = ? ORDER BY version DESC LIMIT 1",
        (project_id, thesis_id),
    )
    if not current:
        raise KeyError("找不到 Thesis")
    previous = current[0]
    before_refs = loads(previous.get("evidence_refs_json"), [])
    after_refs = list(fields.get("evidence_refs") or before_refs)
    known = {row["id"] for row in store.query("SELECT id FROM research_claim WHERE project_id = ?", (project_id,))}
    missing = [item for item in after_refs if item not in known]
    if missing:
        raise ValueError("引用了不存在的 Claim")
    before_conflicts = int(store.scalar("SELECT COUNT(*) FROM research_conflict WHERE project_id = ?", (project_id,)) or 0)
    after_conflicts = int(fields.get("conflict_count") if fields.get("conflict_count") is not None else before_conflicts)
    verdict, diff = classify_diff(before_refs, after_refs, before_conflicts, after_conflicts, invalidated)
    version = int(previous["version"]) + 1
    stamp = now_iso()
    summary = fields.get("summary") if fields.get("summary") is not None else previous.get("summary")
    with store.connect() as conn:
        conn.execute(
            """INSERT INTO research_thesis
               (id, project_id, version, summary, bull_case, base_case, bear_case, key_drivers_json,
                catalysts_json, risks_json, invalidation, open_questions_json, evidence_refs_json,
                map_json, diff_verdict, diff_json, as_of, status, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                thesis_id, project_id, version, summary or "",
                fields.get("bull_case", previous.get("bull_case") or ""),
                fields.get("base_case", previous.get("base_case") or ""),
                fields.get("bear_case", previous.get("bear_case") or ""),
                previous.get("key_drivers_json") or "[]",
                previous.get("catalysts_json") or "[]",
                previous.get("risks_json") or "[]",
                fields.get("invalidation", previous.get("invalidation") or ""),
                previous.get("open_questions_json") or "[]",
                dumps(after_refs), previous.get("map_json") or "{}",
                verdict, dumps(diff), as_of or previous.get("as_of") or "", "SAVED", stamp,
            ),
        )
        conn.execute("UPDATE research_project SET updated_at = ? WHERE id = ?", (stamp, project_id))
    unchanged = store.query(
        "SELECT summary FROM research_thesis WHERE id = ? AND version = ?",
        (thesis_id, previous["version"]),
    )[0]["summary"]
    return {"version": version, "diff_verdict": verdict, "previous_summary": unchanged}


def save_live_artifacts(store: Store, project_id: str, artifacts: dict) -> None:
    """反证、Claim 关系、切片和预期分层。正式 Thesis 已经写过才调用。"""
    claims = {
        row["local_id"]: row["id"]
        for row in store.query(
            "SELECT id, local_id FROM research_claim WHERE project_id = ?",
            (project_id,),
        )
    }
    sources = {
        row["url"]: row["id"]
        for row in store.query("SELECT id, url FROM research_source WHERE project_id = ?", (project_id,))
    }
    stamp = now_iso()
    with store.connect() as conn:
        rows = list(artifacts.get("disconfirmation") or [])
        ids = _ids(conn, "research_disconfirmation", "DG", len(rows))
        for index, row in enumerate(rows):
            conn.execute(
                """INSERT INTO research_disconfirmation
                   (id, project_id, claim_id, query, source_ids, result, status, created_at)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (
                    ids[index], project_id,
                    claims.get(row.get("claim_local_id") or "", row.get("claim_id") or ""),
                    row.get("query") or "", dumps(row.get("source_ids") or []),
                    row.get("result") or "", row.get("status") or "ATTEMPTED", stamp,
                ),
            )
        rows = list(artifacts.get("relations") or [])
        ids = _ids(conn, "research_claim_relation", "RL", len(rows))
        for index, row in enumerate(rows):
            conn.execute(
                """INSERT INTO research_claim_relation
                   (id, project_id, source_claim_id, target_claim_id, relation, created_at)
                   VALUES (?,?,?,?,?,?)""",
                (
                    ids[index], project_id,
                    claims.get(row.get("source_claim") or "", ""),
                    claims.get(row.get("target_claim") or "", ""),
                    row.get("relation") or "", stamp,
                ),
            )
        rows = list(artifacts.get("expectations") or [])
        ids = _ids(conn, "research_expectation", "EX", len(rows))
        for index, row in enumerate(rows):
            conn.execute(
                """INSERT INTO research_expectation
                   (id, project_id, source_type, statement, status, created_at)
                   VALUES (?,?,?,?,?,?)""",
                (
                    ids[index], project_id, row.get("source_type") or "",
                    row.get("statement") or "", row.get("status") or "", stamp,
                ),
            )
    chunks = list(artifacts.get("chunks") or [])
    if chunks:
        from core.research.retrieval import index_chunks
        source_id = sources.get(chunks[0].get("url") or "") or (list(sources.values())[:1] or [""])[0]
        if source_id:
            index_chunks(store, source_id, chunks)


def list_projects(store: Store = STORE) -> List[dict]:
    return store.query(
        """SELECT id, title, industry, status, created_at, updated_at
           FROM research_project ORDER BY updated_at DESC"""
    )


def project_view(store: Store, project_id: str) -> Optional[dict]:
    rows = store.query("SELECT * FROM research_project WHERE id = ?", (project_id,))
    if not rows:
        return None
    project = rows[0]
    question = store.query(
        "SELECT question FROM research_question WHERE project_id = ? ORDER BY created_at LIMIT 1",
        (project_id,),
    )
    project["question"] = question[0]["question"] if question else ""
    claims = store.query("SELECT * FROM research_claim WHERE project_id = ? ORDER BY id", (project_id,))
    evidence = store.query(
        """SELECT e.*, s.title AS source_title, s.source_type, s.available_at, s.url
           FROM research_evidence e
           JOIN research_claim c ON c.id = e.claim_id
           JOIN research_source s ON s.id = e.source_id
           WHERE c.project_id = ?""",
        (project_id,),
    )
    by_claim: Dict[str, List[dict]] = {}
    for item in evidence:
        by_claim.setdefault(item["claim_id"], []).append(item)
    grouped = {kind: [] for kind in ("FACT", "ESTIMATE", "INFERENCE", "OPINION")}
    for claim in claims:
        claim["evidence"] = by_claim.get(claim["id"], [])
        claim["premise_claim_ids"] = loads(claim.get("premise_claim_ids"), [])
        grouped.setdefault(claim.get("claim_type") or "", []).append(claim)
    theses = store.query(
        "SELECT * FROM research_thesis WHERE project_id = ? ORDER BY version",
        (project_id,),
    )
    latest = dict(theses[-1]) if theses else {}
    if latest:
        for key in ("key_drivers_json", "catalysts_json", "risks_json", "open_questions_json", "evidence_refs_json", "map_json", "diff_json"):
            latest[key.replace("_json", "")] = loads(latest.get(key), [] if key != "map_json" and key != "diff_json" else {})
    plans = store.query("SELECT * FROM research_plan WHERE project_id = ? ORDER BY created_at", (project_id,))
    waves = []
    if plans:
        parsed = loads(plans[-1].get("steps_json"), {})
        if isinstance(parsed, dict):
            waves = parsed.get("waves") or []
    project["map"] = loads(project.get("map_json"), {})
    return {
        "project": project,
        "questions": store.query("SELECT * FROM research_question WHERE project_id = ?", (project_id,)),
        "plan": plans,
        "waves": waves,
        "disconfirmation": store.query(
            "SELECT * FROM research_disconfirmation WHERE project_id = ? ORDER BY created_at",
            (project_id,),
        ),
        "claim_relations": store.query(
            "SELECT * FROM research_claim_relation WHERE project_id = ?",
            (project_id,),
        ),
        "expectations": store.query(
            "SELECT * FROM research_expectation WHERE project_id = ?",
            (project_id,),
        ),
        "claims": grouped,
        "evidence": evidence,
        "conflicts": store.query("SELECT * FROM research_conflict WHERE project_id = ?", (project_id,)),
        "value_chain": store.query("SELECT * FROM research_value_chain WHERE project_id = ?", (project_id,)),
        "company_mapping": store.query("SELECT * FROM research_company_mapping WHERE project_id = ?", (project_id,)),
        "thesis": latest,
        "thesis_versions": theses,
        "open_questions": store.query(
            "SELECT * FROM research_open_question WHERE project_id = ? ORDER BY created_at",
            (project_id,),
        ),
        "runs": store.query("SELECT * FROM research_run WHERE project_id = ? ORDER BY started_at", (project_id,)),
        "sources": store.query(
            """SELECT id, title, publisher, source_type, published_at, available_at, captured_at, url, source_quality
               FROM research_source WHERE project_id = ?""",
            (project_id,),
        ),
    }


def public_output(store: Store, project_id: str) -> dict:
    view = project_view(store, project_id) or {}
    project = view.get("project") or {}
    thesis = view.get("thesis") or {}
    map_json = loads(project.get("map_json"), {})
    claims = []
    for rows in (view.get("claims") or {}).values():
        claims.extend(rows)
    output = {
        "research_question": project.get("question") or "",
        "industry_definition": project.get("industry_definition") or "",
        "value_chain": view.get("value_chain") or [],
        "key_drivers": map_json.get("key_drivers") or [],
        "technology_routes": map_json.get("technology_routes") or [],
        "market_structure": map_json.get("market_structure") or [],
        "company_mapping": view.get("company_mapping") or [],
        "catalysts": thesis.get("catalysts") or [],
        "risks": thesis.get("risks") or [],
        "claims": claims,
        "conflicts": view.get("conflicts") or [],
        "open_questions": [row.get("question") for row in view.get("open_questions") or []],
        "thesis": {
            "id": thesis.get("id") or "",
            "version": thesis.get("version") or 0,
            "summary": thesis.get("summary") or "",
            "as_of": thesis.get("as_of") or "",
            "diff_verdict": thesis.get("diff_verdict") or "",
        },
        "evidence_refs": thesis.get("evidence_refs") or [],
    }
    missing = [key for key in OUTPUT_KEYS if key not in output]
    if missing:
        raise KeyError("输出缺字段：{0}".format(missing))
    return output
