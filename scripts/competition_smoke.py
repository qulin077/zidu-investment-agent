#!/usr/bin/env python3
"""Deterministic smoke check for the isolated competition demo database."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True)
    args = parser.parse_args()
    os.environ["SA_DB_PATH"] = str(Path(args.db).expanduser().resolve())

    from core.research import sessions
    from core.store import STORE

    rows = sessions.research_library(STORE, "company")
    assert len(rows) == 1, rows
    assert rows[0]["code"] == "002384", rows[0]
    assert rows[0]["source_count"] == 6, rows[0]
    bundle = sessions.bundle(STORE, rows[0]["primary_session_id"])
    assert bundle and bundle["ok"]
    assert "# 公司档案" in bundle["current_thesis"]["text"]
    assert "PARTIAL" in bundle["current_thesis"]["text"]
    assert all(str(row.get("url") or "").startswith("https://") for row in bundle["sources"])

    decisions = STORE.query("SELECT * FROM decision")
    assert len(decisions) == 1, decisions
    assert decisions[0]["status"] == "REVIEWED", decisions[0]
    assert int(decisions[0]["demo"]) == 1, decisions[0]
    assert decisions[0]["environment"] == "demo", decisions[0]
    assert not STORE.query("SELECT id FROM decision WHERE demo = 0")
    result = STORE.query("SELECT * FROM outcome WHERE decision_id = ?", (decisions[0]["id"],))
    assert len(result) == 1 and result[0]["computed_from"] == "execution+quote_daily", result

    print(json.dumps({
        "ok": True,
        "research": {"company": rows[0]["name"], "sources": rows[0]["source_count"], "coverage": "PARTIAL"},
        "review": {"decision": decisions[0]["id"], "status": decisions[0]["status"], "synthetic": True},
        "private_rows": 0,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
