"""研究会话。事件只记工作轨迹，不记模型隐藏推理。"""
from __future__ import annotations

import json
import re
import threading
import time
from datetime import datetime

from core.context.temporal import CN_TZ, parse_dt
from core.research.store import _ids, finish_run, now_iso
from core.store import Store

_LOCK = threading.Lock()
_HIDDEN = {"chain_of_thought", "thinking", "reasoning", "hidden"}


def create_session(store: Store, title: str) -> str:
    stamp = now_iso()
    with store.connect() as conn:
        session_id = _ids(conn, "research_session", "RY", 1)[0]
        conn.execute(
            """INSERT INTO research_session
               (id, title, skill, status, primary_entity_type, primary_entity_name,
                primary_entity_code, primary_entity_exchange, project_id,
                current_thesis_id, current_thesis_version, summary_json,
                created_at, updated_at, last_run_id)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                session_id, title[:80], "", "OPEN", "", "", "", "", "",
                "", 0, "{}", stamp, stamp, "",
            ),
        )
    return session_id


def get_session(store: Store, session_id: str):
    rows = store.query("SELECT * FROM research_session WHERE id = ?", (session_id,))
    if not rows:
        return None
    row = dict(rows[0])
    row["summary"] = _loads(row.get("summary_json"), {})
    return row


def list_sessions(store: Store, limit: int = 40) -> list:
    return store.query(
        """SELECT id, title, skill, status, primary_entity_name, primary_entity_code,
                  updated_at, last_run_id
           FROM research_session ORDER BY updated_at DESC LIMIT ?""",
        (limit,),
    )


def research_library(store: Store, subject_type: str = "company") -> list:
    """Long-lived research objects grouped by subject, not by chat session.

    A session is execution history.  Company, industry and event dossiers are
    the durable user-facing objects.  Event persistence is enabled in the read
    model now even while its workspace executor is being migrated.
    """
    skill_by_type = {
        "company": "company-research",
        "industry": "industry-research",
        "event": "event-impact",
    }
    selected = subject_type if subject_type in skill_by_type else "company"
    skill = skill_by_type[selected]
    rows = store.query(
        """SELECT id, title, status, primary_entity_name, primary_entity_code,
                  primary_entity_exchange, summary_json, updated_at
           FROM research_session
           WHERE skill = ?
           ORDER BY updated_at DESC, id DESC""",
        (skill,),
    )
    grouped = {}
    for raw in rows:
        row = dict(raw)
        name = (row.get("primary_entity_name") or row.get("title") or "").strip()
        code = (row.get("primary_entity_code") or "").strip()
        if not name:
            continue
        if not code and re.search(r"这公司|怎么样|我有同学", name):
            continue
        key = code or name
        grouped.setdefault(key, []).append(row)

    result = []
    for key, items in grouped.items():
        latest = items[0]
        primary = next(
            (row for row in items if row.get("status") not in ("UNAVAILABLE", "INTERRUPTED")),
            latest,
        )
        summary = _loads(primary.get("summary_json"), {})
        status = primary.get("status") or "OPEN"
        if latest["id"] != primary["id"] and latest.get("status") in ("UNAVAILABLE", "INTERRUPTED"):
            status = "STALE"
        result.append({
            "key": key,
            "subject_type": selected,
            "name": primary.get("primary_entity_name") or primary.get("title") or key,
            "code": primary.get("primary_entity_code") or "",
            "exchange": primary.get("primary_entity_exchange") or "",
            "status": status,
            "primary_session_id": primary["id"],
            "latest_session_id": latest["id"],
            "updated_at": latest.get("updated_at") or "",
            "research_count": len(items),
            "source_count": len(summary.get("sources") or []),
            "claim_count": len(summary.get("claims") or []),
            "open_question_count": len(_current_open_questions(summary, skill)),
        })
    return sorted(result, key=lambda row: row["updated_at"], reverse=True)


def company_library(store: Store) -> list:
    """Backward-compatible company-only library."""
    return research_library(store, "company")


def update_session(store: Store, session_id: str, **fields) -> None:
    allowed = {
        "title", "skill", "status", "primary_entity_type", "primary_entity_name",
        "primary_entity_code", "primary_entity_exchange", "project_id",
        "current_thesis_id", "current_thesis_version", "summary_json", "last_run_id",
    }
    fields["updated_at"] = now_iso()
    keys = [key for key in fields if key in allowed or key == "updated_at"]
    sql = "UPDATE research_session SET {0} WHERE id = ?".format(
        ", ".join("{0} = ?".format(key) for key in keys)
    )
    with store.connect() as conn:
        conn.execute(sql, tuple(fields[key] for key in keys) + (session_id,))


def add_message(store: Store, session_id: str, run_id: str, role: str, content: str, claim_refs=None, source_refs=None) -> str:
    if role not in ("USER", "ASSISTANT"):
        raise ValueError("role")
    with store.connect() as conn:
        message_id = _ids(conn, "research_message", "RH", 1)[0]
        conn.execute(
            """INSERT INTO research_message
               (id, session_id, run_id, role, content, claim_refs_json, source_refs_json, created_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (
                message_id, session_id, run_id or "", role, content or "",
                json.dumps(list(claim_refs or []), ensure_ascii=False),
                json.dumps(list(source_refs or []), ensure_ascii=False),
                now_iso(),
            ),
        )
    return message_id


def list_messages(store: Store, session_id: str) -> list:
    rows = store.query(
        "SELECT * FROM research_message WHERE session_id = ? ORDER BY created_at, id",
        (session_id,),
    )
    for row in rows:
        row["claim_refs"] = _loads(row.get("claim_refs_json"), [])
        row["source_refs"] = _loads(row.get("source_refs_json"), [])
    return rows


def add_event(store: Store, session_id: str, run_id: str, event_type: str, status: str, payload: dict) -> int:
    body = {key: value for key, value in dict(payload or {}).items() if key not in _HIDDEN}
    stamp = now_iso()
    with _LOCK:
        with store.connect() as conn:
            current = conn.execute(
                "SELECT COALESCE(MAX(seq), 0) FROM research_event WHERE session_id = ?",
                (session_id,),
            ).fetchone()[0]
            seq = int(current) + 1
            event_id = _ids(conn, "research_event", "RV", 1)[0]
            conn.execute(
                """INSERT INTO research_event
                   (id, seq, session_id, run_id, event_type, status, payload_json, created_at)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (
                    event_id, seq, session_id, run_id or "", event_type, status or "",
                    json.dumps(body, ensure_ascii=False), stamp,
                ),
            )
            conn.execute(
                "UPDATE research_session SET updated_at = ? WHERE id = ?",
                (stamp, session_id),
            )
    return seq


def list_events(store: Store, session_id: str, after_seq: int = 0) -> list:
    rows = store.query(
        """SELECT * FROM research_event
           WHERE session_id = ? AND seq > ? ORDER BY seq""",
        (session_id, int(after_seq or 0)),
    )
    for row in rows:
        row["payload"] = _loads(row.get("payload_json"), {})
    return rows


def iter_sse(store: Store, session_id: str, after_seq: int = 0, wait: bool = False):
    seen = after_seq
    deadline = time.monotonic() + 180
    while True:
        for row in list_events(store, session_id, seen):
            data = {
                "id": row["id"],
                "seq": row["seq"],
                "session_id": row["session_id"],
                "run_id": row["run_id"],
                "event_type": row["event_type"],
                "status": row["status"],
            }
            data.update(row.get("payload") or {})
            seen = row["seq"]
            yield "id: {0}\ndata: {1}\n\n".format(row["seq"], json.dumps(data, ensure_ascii=False))
        session = get_session(store, session_id)
        running = session is not None and session.get("status") == "RUNNING"
        if not wait or not running or time.monotonic() >= deadline:
            return
        yield ": keepalive\n\n"
        time.sleep(0.4)


def bind_run(store: Store, run_id: str, session_id: str) -> None:
    with store.connect() as conn:
        conn.execute("UPDATE research_run SET session_id = ? WHERE id = ?", (session_id, run_id))


def set_run_skill(store: Store, run_id: str, skill: str) -> None:
    """Persist the skill selected by the workspace, not the pre-route guess."""
    with store.connect() as conn:
        conn.execute("UPDATE research_run SET skill = ? WHERE id = ?", (skill or "", run_id))


def runs_for(store: Store, session_id: str) -> list:
    ids = []
    for row in list_messages(store, session_id):
        if row.get("run_id") and row["run_id"] not in ids:
            ids.append(row["run_id"])
    if not ids:
        return []
    marks = ",".join("?" for _ in ids)
    return store.query(
        "SELECT * FROM research_run WHERE id IN ({0}) ORDER BY started_at".format(marks),
        tuple(ids),
    )


def bundle(store: Store, session_id: str):
    session = get_session(store, session_id)
    if session is None:
        return None
    summary = session.get("summary") or {}
    project = None
    project_id = session.get("project_id") or ""
    if project_id:
        from core.research.store import project_view
        project = project_view(store, project_id)
    thesis = summary.get("draft_thesis") or ""
    if summary.get("formal") and summary.get("verified_thesis"):
        thesis = summary.get("verified_thesis")
    # Research is a durable dossier, while the assistant message is only the
    # answer produced for one turn.  A narrow follow-up (or the advice guard
    # seeing a quoted broker rating) must not make the Research page fall back
    # to that transient chat answer and hide newer dossier sections.
    skill = session.get("skill") or ""
    if skill == "company-research" and summary.get("company_dossier"):
        from core.research import workspace_text
        thesis, _, _ = workspace_text.render_company(
            summary["company_dossier"], summary.get("notice") or "",
        )
    elif skill == "industry-research" and summary.get("industry_dossier"):
        from core.research import workspace_text
        thesis, _, _ = workspace_text.render_industry(
            summary["industry_dossier"], summary.get("notice") or "",
        )
    elif skill == "event-impact" and summary.get("event_dossier"):
        from core.research import workspace_text
        thesis, _, _ = workspace_text.render_event(
            summary["event_dossier"], summary.get("notice") or "",
        )
    open_questions = _current_open_questions(summary, session.get("skill") or "")
    return {
        "ok": True,
        "session": session,
        "messages": list_messages(store, session_id),
        "project": project,
        "runs": runs_for(store, session_id),
        "current_thesis": {
            "text": thesis,
            "formal": bool(summary.get("formal")),
            "label": "FORMAL" if summary.get("formal") else "DRAFT",
        },
        "sources": summary.get("sources") or [],
        "claims": summary.get("claims") or [],
        "conflicts": summary.get("conflicts") or [],
        "open_questions": open_questions,
        "events": list_events(store, session_id, 0),
        "notice": summary.get("notice") or "",
        "upgrade_history": summary.get("upgrade_history") or [],
    }


def _current_open_questions(summary: dict, skill: str) -> list:
    open_questions = list(summary.get("open_questions") or [])
    if skill != "company-research":
        return open_questions
    dossier = summary.get("company_dossier") or {}
    analyst_coverage = ((dossier.get("analyst_view") or {}).get("coverage") or {})
    if not analyst_coverage:
        return open_questions
    from core.research.analyst import COMPANY_FRAMEWORK
    required = list(dossier.get("required_evidence") or COMPANY_FRAMEWORK)
    return [
        key for key in required
        if (analyst_coverage.get(key) or {}).get("status") != "SUPPORTED"
    ]


def reap_stale(store: Store, stale_seconds: int = 900) -> list:
    rows = store.query(
        "SELECT id, last_run_id, updated_at, status FROM research_session WHERE status = 'RUNNING'"
    )
    now = datetime.now(CN_TZ)
    marked = []
    for row in rows:
        updated = parse_dt(row.get("updated_at") or "")
        stale = updated is None or (now - updated).total_seconds() > stale_seconds
        if not stale:
            continue
        mark_interrupted(store, row["id"], row.get("last_run_id") or "", "stale")
        marked.append(row["id"])
    return marked


def mark_interrupted(store: Store, session_id: str, run_id: str, reason: str) -> None:
    session = get_session(store, session_id)
    if session is None or session.get("status") == "INTERRUPTED":
        return
    add_event(store, session_id, run_id, "interrupted", "failed", {"reason": reason})
    update_session(store, session_id, status="INTERRUPTED")
    if run_id:
        finish_run(store, run_id, status="interrupted", error_code="INTERRUPTED", error_message=reason)
    add_message(store, session_id, run_id, "ASSISTANT", "这一轮研究中断了，没有把未完成的结果当成结论。")


def cache_get(store: Store, url: str):
    rows = store.query("SELECT * FROM research_source_cache WHERE canonical_url = ?", (url,))
    return rows[0] if rows else None


def cache_put(store: Store, url: str, row: dict) -> None:
    with store.connect() as conn:
        conn.execute(
            """INSERT INTO research_source_cache
               (canonical_url, content_hash, title, publisher, published_at, content_type, text, retrieved_at)
               VALUES (?,?,?,?,?,?,?,?)
               ON CONFLICT(canonical_url) DO UPDATE SET
                 content_hash = excluded.content_hash,
                 title = excluded.title,
                 publisher = excluded.publisher,
                 published_at = excluded.published_at,
                 content_type = excluded.content_type,
                 text = excluded.text,
                 retrieved_at = excluded.retrieved_at""",
            (
                url, row.get("content_hash") or "", row.get("title") or "",
                row.get("publisher") or "", row.get("published_at") or "",
                row.get("content_type") or "", row.get("text") or "",
                row.get("retrieved_at") or now_iso(),
            ),
        )


def extract_get(store: Store, cache_key: str):
    rows = store.query("SELECT claims_json FROM research_extract_cache WHERE cache_key = ?", (cache_key,))
    if not rows:
        return None
    return _loads(rows[0]["claims_json"], [])


def extract_put(store: Store, cache_key: str, claims: list) -> None:
    with store.connect() as conn:
        conn.execute(
            """INSERT INTO research_extract_cache (cache_key, claims_json, created_at)
               VALUES (?,?,?)
               ON CONFLICT(cache_key) DO UPDATE SET claims_json = excluded.claims_json""",
            (cache_key, json.dumps(claims, ensure_ascii=False), now_iso()),
        )


def _loads(raw, fallback):
    try:
        return json.loads(raw or "")
    except (TypeError, json.JSONDecodeError):
        return fallback
