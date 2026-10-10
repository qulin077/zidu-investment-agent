"""核实过的公司名可以复用。缓存不是行情，也不是研究结论。"""
from __future__ import annotations

import json

from core.research.store import _ids, now_iso


def _alias_hit(name: str, text: str) -> bool:
    if not name or not text:
        return False
    if name in text:
        return True
    compact = "".join(text.split())
    return len(compact) >= 2 and len(name) - len(compact) <= 3 and name.startswith(compact)


def lookup(store, text: str) -> dict:
    if store is None or not text:
        return {}
    try:
        rows = store.query("SELECT * FROM research_entity")
    except Exception:
        return {}
    for row in rows:
        names = [row.get("canonical_name") or "", row.get("ticker") or ""]
        try:
            names.extend(json.loads(row.get("aliases_json") or "[]"))
        except json.JSONDecodeError:
            pass
        if any(_alias_hit(name, text) for name in names):
            return {
                "ok": True,
                "status": "RESOLVED",
                "canonical_name": row.get("canonical_name") or "",
                "ticker": row.get("ticker") or "",
                "exchange": row.get("exchange") or "",
                "aliases": [name for name in names if name],
                "verified_source": row.get("verified_source") or "",
                "verified_at": row.get("verified_at") or "",
                "universe_status": "NOT_IN_UNIVERSE",
                "path": "",
                "candidates": [],
                "chains": [],
            }
    return {}


def remember(store, found: dict) -> None:
    if store is None or found.get("status") != "RESOLVED":
        return
    name = found.get("canonical_name") or ""
    ticker = found.get("ticker") or ""
    if not name or not ticker:
        return
    try:
        existing = store.query(
            "SELECT id FROM research_entity WHERE ticker = ? OR canonical_name = ? LIMIT 1",
            (ticker, name),
        )
    except Exception:
        return
    aliases = list(found.get("aliases") or [])
    for extra in (name, ticker):
        if extra and extra not in aliases:
            aliases.append(extra)
    payload = json.dumps(aliases, ensure_ascii=False)
    stamp = found.get("verified_at") or now_iso()
    if existing:
        with store.connect() as conn:
            conn.execute(
                """UPDATE research_entity
                   SET canonical_name=?, ticker=?, exchange=?, aliases_json=?, verified_source=?, verified_at=?
                   WHERE id=?""",
                (name, ticker, found.get("exchange") or "", payload, found.get("verified_source") or "", stamp, existing[0]["id"]),
            )
        return
    with store.connect() as conn:
        entity_id = _ids(conn, "research_entity", "EN", 1)[0]
        conn.execute(
            """INSERT INTO research_entity
               (id, canonical_name, ticker, exchange, aliases_json, entity_type, verified_source, verified_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (entity_id, name, ticker, found.get("exchange") or "", payload, "company", found.get("verified_source") or "", stamp),
        )
