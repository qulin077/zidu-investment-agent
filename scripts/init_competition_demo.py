#!/usr/bin/env python3
"""Initialize an isolated, anonymous database for the public competition demo.

The script never reads the author's workstation database.  It imports a small
public-source fixture and one explicitly synthetic decision lifecycle so the
deployed product is useful without exposing private research or trading data.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "demo" / "dongshan_public_fixture.json"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db",
        default=str(ROOT / "data" / "competition-demo.db"),
        help="target SQLite database; use a new path, never the personal workstation DB",
    )
    return parser.parse_args()


def _seed_research(store, fixture: dict) -> None:
    from core.research import sessions, workspace_text

    spec = fixture["session"]
    if sessions.get_session(store, spec["id"]):
        return
    stamp = "2026-08-22T18:00:00+08:00"
    summary = fixture["summary"]
    with store.connect() as conn:
        conn.execute(
            """INSERT INTO research_session
               (id, title, skill, status, primary_entity_type, primary_entity_name,
                primary_entity_code, primary_entity_exchange, project_id,
                current_thesis_id, current_thesis_version, summary_json,
                created_at, updated_at, last_run_id)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                spec["id"], spec["title"], spec["skill"], spec["status"],
                spec["primary_entity_type"], spec["primary_entity_name"],
                spec["primary_entity_code"], spec["primary_entity_exchange"],
                "", "", 0, json.dumps(summary, ensure_ascii=False),
                stamp, stamp, "RR-DEMO-0001",
            ),
        )
    report, claim_refs, source_refs = workspace_text.render_company(
        summary["company_dossier"], summary.get("notice") or "",
    )
    sessions.add_message(
        store, spec["id"], "RR-DEMO-0001", "USER",
        "完整研究东山精密，并把财报事实、市场预期和风险分开。",
    )
    sessions.add_message(
        store, spec["id"], "RR-DEMO-0001", "ASSISTANT", report,
        claim_refs=claim_refs, source_refs=source_refs,
    )
    trace = [
        ("intent", "识别为公司全面研究", "completed"),
        ("plan", "拆解财报、管理层交流、卖方预期、市场叙事和反证", "completed"),
        ("search", "并行检查六份可再分发的公开来源", "completed"),
        ("read", "读取三年年报、半年报、管理层交流与卖方报告", "completed"),
        ("evidence", "把来源拆成事实、预测与推断并保留引用", "completed"),
        ("done", "覆盖检查未通过的部分保持待核对", "completed"),
    ]
    for event_type, title, status in trace:
        sessions.add_event(
            store, spec["id"], "RR-DEMO-0001", event_type, status,
            {"title": title, "detail": "公开Demo轨迹，不包含模型隐藏思维。"},
        )


def _seed_review(store) -> str:
    from core.review import lifecycle, outcome, repo

    existing = store.query(
        "SELECT id FROM decision WHERE demo = 1 AND code = '002384' ORDER BY created_at LIMIT 1"
    )
    if existing:
        return existing[0]["id"]

    decision_id = repo.create_decision(
        code="002384",
        name="东山精密（模拟）",
        thesis="观察AI相关需求是否能从叙事兑现为收入、利润率和经营现金流改善。",
        earning_type="业绩验证",
        holding_period="中线观察",
        market_context="比赛公开Demo；以下成交价格和数量均为合成数据。",
        opened_on="2026-04-30",
        source="user",
        created_by="demo_user",
        environment="demo",
        demo=1,
        store=store,
    )
    repo.add_expectation(
        decision_id,
        "截至2026年半年报，收入与归母净利润同比改善，且毛利率高于2025年；否则重新检查核心逻辑。",
        window_start="2026-05-01",
        window_end="2026-08-31",
        confidence=3,
        source="user",
        created_by="demo_user",
        store=store,
    )
    repo.add_plan(
        decision_id,
        entry_rule="只在事前Thesis和失效条件记录完整后建立模拟观察仓。",
        invalidation="收入增长未转化为利润率和现金流，或资本开支与负债持续上升且没有订单验证。",
        target_size_pct=8.0,
        holding_period="到2026年半年报验证",
        entry_window_start="2026-05-01",
        entry_window_end="2026-05-15",
        source="user",
        created_by="demo_user",
        store=store,
    )
    repo.transition(decision_id, lifecycle.PLANNED, "Demo事前字段完整", "demo_user", "user", store)

    store.upsert("quote_daily", [
        {"code": "002384", "date": "2026-05-06", "open": 99.0, "high": 103.0, "low": 97.0, "close": 100.0, "volume": 1, "pct_chg": 0.0},
        {"code": "002384", "date": "2026-06-30", "open": 104.0, "high": 109.0, "low": 101.0, "close": 107.0, "volume": 1, "pct_chg": 0.0},
        {"code": "002384", "date": "2026-08-25", "open": 111.0, "high": 114.0, "low": 109.0, "close": 112.0, "volume": 1, "pct_chg": 0.0}
    ])
    repo.add_execution(
        code="002384", name="东山精密（模拟）", executed_on="2026-05-06",
        executed_at="10:00", side="BUY", price=100.0, qty=100,
        decision_id=decision_id, planned="yes", size_pct=8.0,
        note="合成Demo成交，不对应真实账户或真实价格。",
        source="user", created_by="demo_user", store=store,
    )
    repo.advance(decision_id, changed_by="demo_user", store=store)
    repo.add_execution(
        code="002384", name="东山精密（模拟）", executed_on="2026-08-25",
        executed_at="14:30", side="SELL", price=112.0, qty=100,
        decision_id=decision_id, planned="yes",
        note="半年报发布后结束模拟验证；价格和数量均为合成数据。",
        source="user", created_by="demo_user", store=store,
    )
    outcome.close_and_compute(decision_id, changed_by="demo_user", store=store)
    review_id = repo.add_review(
        decision_id,
        reviewed_on="2026-08-26",
        lesson="不能只验证收入和利润增速；下一轮必须同时检查资本开支、负债与自由现金流。",
        user_note="半年报验证了当期增长，但不代表长期逻辑已经成立。",
        outcome_confirmed=True,
        violations_confirmed=True,
        created_by="demo_user",
        store=store,
    )
    repo.add_attribution(
        decision_id,
        review_id,
        "NONE",
        counterfactual="如果只看市场叙事而没有三年财务基线，就无法识别增长质量和资本开支压力。",
        confidence="high",
        evidence=[decision_id, "RY-DEMO-0001"],
        user_confirmed=True,
        created_by="demo_user",
        store=store,
    )
    repo.transition(decision_id, lifecycle.REVIEWED, "Demo复盘由用户确认", "demo_user", "user", store)
    return decision_id


def main() -> int:
    args = _args()
    db_path = Path(args.db).expanduser().resolve()
    personal = (ROOT / "data" / "workstation.db").resolve()
    if db_path == personal:
        raise SystemExit("拒绝写入个人 workstation.db；请给比赛Demo使用独立数据库路径。")
    os.environ["SA_DB_PATH"] = str(db_path)

    from core.store import STORE

    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    STORE.init_schema()
    _seed_research(STORE, fixture)
    decision_id = _seed_review(STORE)
    print(json.dumps({
        "ok": True,
        "db": str(STORE.path),
        "research_session": fixture["session"]["id"],
        "decision": decision_id,
        "private_data_imported": False,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
