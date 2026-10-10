"""Runtime loader and router for industry research playbooks.

The agent workflow stays generic.  YAML playbooks describe what changes by
industry: taxonomy, monitoring metrics, financial checks and search recipes.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import re
from typing import Any

import yaml

from core.config import CONFIG_DIR


PLAYBOOK_DIR = CONFIG_DIR / "research_playbooks"
REQUIRED_KEYS = {
    "id", "label", "domain", "aliases", "segments", "monitoring_metrics",
    "financial_validation", "source_priorities", "query_recipes", "vendor_queries",
}


@lru_cache(maxsize=1)
def load_all() -> tuple[dict[str, Any], ...]:
    rows = []
    for path in sorted(PLAYBOOK_DIR.glob("*.yaml")):
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(payload, dict):
            raise ValueError("industry playbook must be an object: {0}".format(path))
        missing = REQUIRED_KEYS - set(payload)
        if missing:
            raise ValueError("industry playbook missing {0}: {1}".format(sorted(missing), path))
        item = dict(payload)
        item["_path"] = str(path)
        item["priority"] = int(item.get("priority") or 100)
        rows.append(item)
    return tuple(sorted(rows, key=lambda row: (row["priority"], row["id"])))


def route(value: str) -> dict[str, Any]:
    """Resolve a subject to a playbook and the narrowest matching segment."""
    # A multi-subject dossier keeps the first subject as its primary playbook;
    # later subjects are comparison/context rather than silently taking over
    # because one alias happens to be classified as a narrower segment.
    text = (value or "").split("/")[0].strip()
    best = None
    for playbook in load_all():
        for alias in _aliases(playbook):
            position = text.lower().find(alias.lower())
            if position < 0:
                continue
            segment = _segment_for_alias(playbook, alias)
            score = (len(alias), 1 if segment else 0, -playbook["priority"])
            if best is None or score > best[0]:
                best = (score, playbook, alias, segment, position)
    if best is None:
        return {
            "id": "generic", "label": "通用行业", "domain": "未分类行业",
            "subject": text or "行业主题", "matched_alias": "", "focus_segment": {},
            "monitoring_metrics": [], "financial_validation": [],
            "source_priorities": [], "query_recipes": {}, "vendor_queries": [],
            "path": "",
        }
    _, playbook, alias, segment, _ = best
    return _public(playbook, subject=alias, matched_alias=alias, segment=segment)


def subjects_from_question(question: str) -> list[str]:
    """Return non-overlapping named subjects, preserving playbook priority."""
    value = (question or "").strip()
    matches = []
    for playbook in load_all():
        candidates = []
        for alias in _aliases(playbook):
            pos = value.lower().find(alias.lower())
            if pos >= 0:
                candidates.append((len(alias), pos, alias))
        if candidates:
            _, pos, alias = max(candidates, key=lambda row: (row[0], -row[1]))
            matches.append((playbook["priority"], pos, alias))
    # Priority is stable product ordering; it also preserves the existing
    # "光模块 / PCB" canonical name used by saved research objects.
    return [alias for _, _, alias in sorted(matches, key=lambda row: (row[0], row[1]))]


def describe(subject: str) -> dict[str, Any]:
    return route(subject)


def catalog() -> list[dict[str, Any]]:
    """Return the user-facing playbook catalog without planner internals."""
    rows = []
    for playbook in load_all():
        rows.append({
            "id": playbook.get("id") or "",
            "label": playbook.get("label") or "",
            "domain": playbook.get("domain") or "",
            "segments": [
                {
                    "id": segment.get("id") or "",
                    "label": segment.get("label") or "",
                    "aliases": list(segment.get("aliases") or []),
                }
                for segment in (playbook.get("segments") or [])
            ],
            "monitoring_metrics": list(playbook.get("monitoring_metrics") or []),
            "financial_validation": list(playbook.get("financial_validation") or []),
            "source_priorities": list(playbook.get("source_priorities") or []),
        })
    return rows


def monitoring_metrics(subject: str) -> list[str]:
    return list(route(subject).get("monitoring_metrics") or [])


def match_terms(subject: str) -> list[str]:
    """Aliases used by the daily candidate detector, never as evidence."""
    routed = route(subject)
    playbook_id = routed.get("id") or ""
    for playbook in load_all():
        if playbook.get("id") == playbook_id:
            return _aliases(playbook)
    return [subject] if subject else []


def vendor_queries(subject: str) -> list[str]:
    playbook = route(subject)
    target = (subject or playbook.get("subject") or playbook.get("label") or "行业").split("/")[0].strip()
    return _format_rows(playbook.get("vendor_queries") or [], target)


def gap_queries(subject: str, category: str) -> list[str]:
    playbook = route(subject)
    target = (subject or playbook.get("subject") or playbook.get("label") or "行业").split("/")[0].strip()
    recipes = playbook.get("query_recipes") or {}
    return _format_rows(recipes.get(category) or [], target)


def analysis_context(subject: str) -> str:
    playbook = route(subject)
    if playbook.get("id") == "generic":
        return ""
    focus = (playbook.get("focus_segment") or {}).get("label") or "全产业链"
    return (
        "本轮使用 {label} Playbook（产业域：{domain}；聚焦环节：{focus}）。"
        "优先监控：{metrics}。财务验证重点：{financials}。优先来源：{sources}。"
    ).format(
        label=playbook.get("label") or "行业",
        domain=playbook.get("domain") or "",
        focus=focus,
        metrics="、".join((playbook.get("monitoring_metrics") or [])[:6]),
        financials="、".join((playbook.get("financial_validation") or [])[:4]),
        sources="、".join((playbook.get("source_priorities") or [])[:5]),
    )


def validate_all() -> list[str]:
    errors = []
    seen = set()
    for playbook in load_all():
        if playbook["id"] in seen:
            errors.append("duplicate id: {0}".format(playbook["id"]))
        seen.add(playbook["id"])
        if not playbook.get("monitoring_metrics"):
            errors.append("{0}: monitoring_metrics empty".format(playbook["id"]))
        if not playbook.get("vendor_queries"):
            errors.append("{0}: vendor_queries empty".format(playbook["id"]))
        for category, rows in (playbook.get("query_recipes") or {}).items():
            if not category or not isinstance(rows, list):
                errors.append("{0}: invalid query recipe".format(playbook["id"]))
            for row in rows or []:
                if "{subject}" not in str(row):
                    errors.append("{0}: recipe missing subject placeholder".format(playbook["id"]))
    return errors


def _aliases(playbook: dict[str, Any]) -> list[str]:
    rows = list(playbook.get("aliases") or [])
    for segment in playbook.get("segments") or []:
        rows.extend(segment.get("aliases") or [])
    return list(dict.fromkeys(str(row).strip() for row in rows if str(row).strip()))


def _segment_for_alias(playbook: dict[str, Any], alias: str) -> dict[str, Any]:
    for segment in playbook.get("segments") or []:
        if alias in (segment.get("aliases") or []):
            return dict(segment)
    return {}


def _public(playbook: dict[str, Any], *, subject: str, matched_alias: str, segment: dict) -> dict[str, Any]:
    return {
        "id": playbook.get("id") or "", "label": playbook.get("label") or "",
        "domain": playbook.get("domain") or "", "subject": subject,
        "matched_alias": matched_alias, "focus_segment": dict(segment or {}),
        "monitoring_metrics": list(playbook.get("monitoring_metrics") or []),
        "financial_validation": list(playbook.get("financial_validation") or []),
        "source_priorities": list(playbook.get("source_priorities") or []),
        "query_recipes": dict(playbook.get("query_recipes") or {}),
        "vendor_queries": list(playbook.get("vendor_queries") or []),
        "path": playbook.get("_path") or "",
    }


def _format_rows(rows: list, subject: str) -> list[str]:
    result = []
    for row in rows or []:
        value = re.sub(r"\s+", " ", str(row).format(subject=subject)).strip()
        if value and value not in result:
            result.append(value)
    return result
