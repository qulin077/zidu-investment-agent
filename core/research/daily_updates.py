"""Turn daily news into user-reviewed research update candidates.

This module deliberately stops before evidence collection.  A title or feed
summary may suggest that a dossier changed, but only the Research Workspace is
allowed to read sources, search for corroboration and write the next version.
"""
from __future__ import annotations

from datetime import date, timedelta
import hashlib
import json
import re
from typing import Any

from core.research import industry_playbooks
from core.research.store import now_iso
from core.store import Store


_TRIGGERS = {
    "POLICY": ("政策", "监管", "规则", "关税", "制裁", "禁令", "豁免", "生效", "征求意见", "FCC"),
    "TECHNOLOGY": ("发布", "新品", "平台", "量产", "送样", "验证", "认证", "技术路线", "替代"),
    "EXECUTION": ("中标", "订单", "合同", "扩产", "投产", "停产", "涨价", "并购", "重组", "交付"),
    "EARNINGS": ("年报", "季报", "业绩", "预告", "快报", "指引", "上调", "下调", "营收", "利润"),
    "DISCONFIRMATION": ("取消", "撤回", "终止", "延迟", "失败", "不及预期", "下修"),
}
_HIGH_IMPACT = (
    "正式生效", "禁令", "制裁", "关税", "重大合同", "中标", "停产", "量产",
    "并购", "重组", "业绩预告", "上调", "下调", "取消", "撤回", "终止",
)
_SKILL_TO_TYPE = {
    "company-research": "company",
    "industry-research": "industry",
    "event-impact": "event",
}


def scan_news(store: Store, *, since: str = "", limit: int = 500) -> dict[str, Any]:
    """Scan recent feed rows and enqueue candidates without changing dossiers."""
    start = (since or (date.today() - timedelta(days=3)).isoformat()).strip()
    news_rows = store.query(
        """SELECT id, source, published_at, title, url, summary, tags
           FROM news_item WHERE published_at >= ?
           ORDER BY published_at DESC LIMIT ?""",
        (start, max(1, min(int(limit), 5000))),
    )
    targets = _tracked_targets(store)
    created = 0
    matched_news = 0
    new_events = 0
    for news in news_rows:
        text = _text(news)
        trigger_types, trigger_terms = _trigger_types(text)
        if not trigger_types:
            continue
        matches = []
        for target in targets:
            terms = [term for term in target["terms"] if _contains(text, term)]
            if terms:
                matches.append((target, terms))
        if matches:
            matched_news += 1
            for target, terms in matches:
                row = _candidate(news, target, terms, trigger_types, trigger_terms)
                created += _insert(store, row)
            continue
        # Unmatched feed items are only surfaced when the title itself carries
        # a material change signal.  They remain new-event candidates until a
        # user explicitly asks the agent to verify them.
        title = str(news.get("title") or "")
        high_terms = [term for term in _HIGH_IMPACT if term in title]
        if high_terms:
            target = {"type": "new_event", "session_id": "", "name": title[:80], "code": "", "terms": []}
            row = _candidate(news, target, high_terms, trigger_types, trigger_terms, importance="HIGH")
            created += _insert(store, row)
            new_events += 1
    return {
        "ok": True,
        "since": start,
        "news_scanned": len(news_rows),
        "matched_news": matched_news,
        "new_event_candidates": new_events,
        "created": created,
        "pending": pending_count(store),
    }


def list_candidates(store: Store, *, status: str = "PENDING", limit: int = 30) -> list[dict[str, Any]]:
    allowed = {"PENDING", "ACCEPTED", "DISMISSED", "VERIFIED", "APPLIED", "FAILED"}
    selected = status if status in allowed else "PENDING"
    rows = store.query(
        """SELECT * FROM research_update_candidate
           WHERE status = ?
           ORDER BY CASE importance WHEN 'HIGH' THEN 0 WHEN 'MEDIUM' THEN 1 ELSE 2 END,
                    published_at DESC, detected_at DESC
           LIMIT ?""",
        (selected, max(1, min(int(limit), 200))),
    )
    for row in rows:
        row["matched_terms"] = _loads(row.pop("matched_terms_json", "[]"), [])
        row["metadata"] = _loads(row.pop("metadata_json", "{}"), {})
    return rows


def get_candidate(store: Store, candidate_id: str) -> dict[str, Any] | None:
    rows = store.query("SELECT * FROM research_update_candidate WHERE id = ?", (candidate_id,))
    return dict(rows[0]) if rows else None


def set_status(store: Store, candidate_id: str, status: str, *, run_id: str = "", session_id: str = "") -> None:
    allowed = {"PENDING", "ACCEPTED", "DISMISSED", "VERIFIED", "APPLIED", "FAILED"}
    if status not in allowed:
        raise ValueError("invalid candidate status")
    with store.connect() as conn:
        conn.execute(
            """UPDATE research_update_candidate
               SET status = ?, verification_run_id = CASE WHEN ? <> '' THEN ? ELSE verification_run_id END,
                   target_session_id = CASE WHEN ? <> '' THEN ? ELSE target_session_id END,
                   applied_at = CASE WHEN ? IN ('VERIFIED','APPLIED') THEN ? ELSE applied_at END
               WHERE id = ?""",
            (status, run_id, run_id, session_id, session_id, status, now_iso(), candidate_id),
        )


def pending_count(store: Store) -> int:
    return int(store.scalar("SELECT COUNT(*) FROM research_update_candidate WHERE status = 'PENDING'") or 0)


def _tracked_targets(store: Store) -> list[dict[str, Any]]:
    rows = store.query(
        """SELECT id, skill, status, primary_entity_name, primary_entity_code, summary_json
           FROM research_session
           WHERE skill IN ('company-research','industry-research','event-impact')
             AND primary_entity_name <> ''
           ORDER BY updated_at DESC"""
    )
    seen = set()
    result = []
    for row in rows:
        target_type = _SKILL_TO_TYPE.get(row.get("skill") or "")
        name = str(row.get("primary_entity_name") or "").strip()
        code = str(row.get("primary_entity_code") or "").strip()
        key = (target_type, code or name)
        if not target_type or key in seen or row.get("status") == "UNAVAILABLE":
            continue
        seen.add(key)
        summary = _loads(row.get("summary_json"), {})
        terms = [name, code]
        primary = summary.get("primary_entity") or {}
        terms.extend(primary.get("aliases") or [])
        if target_type == "industry":
            for subject in [part.strip() for part in name.split("/") if part.strip()]:
                playbook = industry_playbooks.describe(subject)
                terms.extend([playbook.get("label") or "", playbook.get("matched_alias") or ""])
                terms.extend(industry_playbooks.match_terms(subject))
        result.append({
            "type": target_type, "session_id": row["id"], "name": name, "code": code,
            "terms": _clean_terms(terms),
        })
    return result


def _candidate(news: dict, target: dict, terms: list[str], trigger_types: list[str], trigger_terms: list[str], importance: str = "") -> dict:
    identity = "|".join((str(news.get("id") or ""), target["type"], target["session_id"], target["name"]))
    candidate_id = "RU-" + hashlib.sha1(identity.encode("utf-8")).hexdigest()[:18]
    level = importance or ("HIGH" if any(term in str(news.get("title") or "") for term in _HIGH_IMPACT) else "MEDIUM")
    candidate_type = trigger_types[0] if len(trigger_types) == 1 else "MULTI_SIGNAL"
    return {
        "id": candidate_id, "news_id": news.get("id") or "", "news_url": news.get("url") or "",
        "news_title": news.get("title") or "", "news_source": news.get("source") or "",
        "published_at": news.get("published_at") or "", "detected_at": now_iso(),
        "candidate_type": candidate_type, "target_type": target["type"],
        "target_session_id": target["session_id"], "target_name": target["name"],
        "target_code": target["code"],
        "match_reason": "命中研究对象：{0}；变化信号：{1}".format(
            "、".join(terms[:5]), "、".join(trigger_terms[:5]),
        ),
        "matched_terms_json": json.dumps(list(dict.fromkeys(terms + trigger_terms)), ensure_ascii=False),
        "importance": level, "metadata_json": json.dumps({"trigger_types": trigger_types}, ensure_ascii=False),
    }


def _insert(store: Store, row: dict) -> int:
    with store.connect() as conn:
        cursor = conn.execute(
            """INSERT OR IGNORE INTO research_update_candidate
               (id, news_id, news_url, news_title, news_source, published_at, detected_at,
                candidate_type, target_type, target_session_id, target_name, target_code,
                match_reason, matched_terms_json, importance, metadata_json)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            tuple(row[key] for key in (
                "id", "news_id", "news_url", "news_title", "news_source", "published_at", "detected_at",
                "candidate_type", "target_type", "target_session_id", "target_name", "target_code",
                "match_reason", "matched_terms_json", "importance", "metadata_json",
            )),
        )
        return int(cursor.rowcount or 0)


def _trigger_types(text: str) -> tuple[list[str], list[str]]:
    kinds = []
    terms = []
    for kind, values in _TRIGGERS.items():
        hits = [value for value in values if value.lower() in text.lower()]
        if hits:
            kinds.append(kind)
            terms.extend(hits)
    return kinds, list(dict.fromkeys(terms))


def _text(news: dict) -> str:
    return " ".join(str(news.get(key) or "") for key in ("title", "summary", "tags"))


def _contains(text: str, term: str) -> bool:
    value = (term or "").strip()
    if not value:
        return False
    if value.isdigit() and len(value) < 6:
        return False
    if re.fullmatch(r"[A-Za-z0-9.+-]+", value):
        return re.search(
            r"(?<![A-Za-z0-9]){0}(?![A-Za-z0-9])".format(re.escape(value)),
            text,
            flags=re.IGNORECASE,
        ) is not None
    return value.lower() in text.lower()


def _clean_terms(values: list[Any]) -> list[str]:
    rows = []
    for raw in values:
        value = re.sub(r"\s+", " ", str(raw or "")).strip()
        if len(value) < 2 or value in rows:
            continue
        rows.append(value)
    return rows


def _loads(raw: Any, fallback: Any) -> Any:
    try:
        return json.loads(raw or "")
    except (TypeError, json.JSONDecodeError):
        return fallback
