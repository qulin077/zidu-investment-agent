"""Playbooks for long-running research themes handled by event-impact.

An evolving theme is not a single announcement.  The playbook supplies the
vocabulary, actor map and search recipes while the generic agent still decides
which evidence gap to fill next.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import re
from typing import Any

import yaml

from core.config import CONFIG_DIR


PLAYBOOK_DIR = CONFIG_DIR / "research_topics"
REQUIRED_KEYS = {
    "id", "label", "canonical_name", "search_name", "aliases", "tracks", "actors",
    "source_domains", "query_recipes",
}


@lru_cache(maxsize=1)
def load_all() -> tuple[dict[str, Any], ...]:
    rows = []
    for path in sorted(PLAYBOOK_DIR.glob("*.yaml")):
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(payload, dict):
            raise ValueError("topic playbook must be an object: {0}".format(path))
        missing = REQUIRED_KEYS - set(payload)
        if missing:
            raise ValueError("topic playbook missing {0}: {1}".format(sorted(missing), path))
        item = dict(payload)
        item["_path"] = str(path)
        rows.append(item)
    return tuple(rows)


def route(value: str) -> dict[str, Any]:
    text = re.sub(r"\s+", "", value or "").lower()
    best = None
    for playbook in load_all():
        for alias in playbook.get("aliases") or []:
            normalized = re.sub(r"\s+", "", str(alias)).lower()
            if normalized and normalized in text:
                score = len(normalized)
                if best is None or score > best[0]:
                    best = (score, playbook, alias)
    if best is None:
        return {}
    _, playbook, alias = best
    return {
        "id": playbook.get("id") or "",
        "label": playbook.get("label") or "",
        "canonical_name": playbook.get("canonical_name") or alias,
        "search_name": playbook.get("search_name") or playbook.get("canonical_name") or alias,
        "matched_alias": alias,
        "tracks": list(playbook.get("tracks") or []),
        "actors": list(playbook.get("actors") or []),
        "source_domains": list(playbook.get("source_domains") or []),
        "query_recipes": dict(playbook.get("query_recipes") or {}),
        "path": playbook.get("_path") or "",
    }


def canonical_name(value: str) -> str:
    return route(value).get("canonical_name") or (value or "").strip()


def is_theme(value: str) -> bool:
    return bool(route(value))


def gap_queries(subject: str, category: str) -> list[str]:
    playbook = route(subject)
    target = playbook.get("canonical_name") or subject or "研究主题"
    search_target = playbook.get("search_name") or target
    rows = (playbook.get("query_recipes") or {}).get(category) or []
    result = []
    for row in rows:
        value = re.sub(r"\s+", " ", str(row).format(subject=target, search_subject=search_target)).strip()
        if value and value not in result:
            result.append(value)
    return result


def analysis_context(subject: str) -> str:
    playbook = route(subject)
    if not playbook:
        return ""
    return (
        "本轮按演化主题研究，不把它伪装成单一事件。"
        "分别跟踪定义边界、起源基线、子事件时间线、当前催化、参与主体、技术/政策分支和产业影响。"
        "重点分支：{tracks}。关键主体：{actors}。一手来源域：{domains}。"
    ).format(
        tracks="、".join(playbook.get("tracks") or []),
        actors="、".join(playbook.get("actors") or []),
        domains="、".join(playbook.get("source_domains") or []),
    )


def validate_all() -> list[str]:
    errors = []
    seen = set()
    for playbook in load_all():
        playbook_id = playbook.get("id") or ""
        if playbook_id in seen:
            errors.append("duplicate id: {0}".format(playbook_id))
        seen.add(playbook_id)
        if not playbook.get("aliases"):
            errors.append("{0}: aliases empty".format(playbook_id))
        for category, rows in (playbook.get("query_recipes") or {}).items():
            if not category or not isinstance(rows, list):
                errors.append("{0}: invalid query recipe".format(playbook_id))
                continue
            for row in rows:
                if "{subject}" not in str(row) and "{search_subject}" not in str(row):
                    errors.append("{0}: recipe missing subject placeholder".format(playbook_id))
    return errors
