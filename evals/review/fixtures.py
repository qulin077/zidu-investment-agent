"""Guided Review 夹具。把 Decision 推到 REVIEW_PENDING。"""
from __future__ import annotations

from typing import Any, Dict

from core.review import gates, lifecycle, outcome, repo
from core.store import Store


def quotes(store: Store, code: str, rows) -> None:
    store.upsert(
        "quote_daily",
        [
            {
                "code": code, "date": d, "open": o, "high": h,
                "low": lo, "close": c, "volume": 0, "pct_chg": 0,
            }
            for d, o, h, lo, c in rows
        ],
    )


def _planned(store: Store, code: str = "300308", size_pct: float = 10.0,
             thesis: str = "回踩后参与", expect: str = "三日内修复") -> str:
    did = repo.create_decision(
        code=code, name="中际旭创", thesis=thesis,
        holding_period="短期", opened_on="2026-09-18", store=store,
        origin="EX_ANTE", witnessed_at="2026-09-18T09:00:00",
        origin_status="PROVISIONAL",
    )
    repo.add_expectation(did, expect, window_start="2026-09-19", window_end="2026-09-23", store=store)
    repo.add_plan(
        did, entry_rule="回踩分批", invalidation="跌破30逻辑失效",
        target_size_pct=size_pct, stop_price=96.0,
        entry_window_start="2026-09-19", entry_window_end="2026-09-22",
        store=store,
    )
    repo.transition(did, lifecycle.PLANNED, "事前齐全", store=store)
    return did


def _close(store: Store, did: str, code: str, buy_px: float, sell_px: float,
           qty: float, size_pct: float, planned: str = "yes",
           quote_rows=None) -> str:
    rows = quote_rows or [
        ("2026-09-19", buy_px, buy_px + 2, buy_px - 1, buy_px),
        ("2026-09-23", sell_px, sell_px + 1, sell_px - 1, sell_px),
    ]
    quotes(store, code, rows)
    repo.add_execution(
        code=code, executed_on="2026-09-19", executed_at="10:00:00",
        side="BUY", price=buy_px, qty=qty, decision_id=did, planned=planned,
        size_pct=size_pct, store=store,
    )
    repo.advance(did, store=store)
    repo.add_execution(
        code=code, executed_on="2026-09-23", executed_at="14:00:00",
        side="SELL", price=sell_px, qty=qty, decision_id=did, planned=planned,
        store=store,
    )
    outcome.close_and_compute(did, store=store)
    gates.run(did, store)
    return did


def build(kind: str, store: Store) -> str:
    if kind == "good_loss":
        did = _planned(store, size_pct=10)
        return _close(store, did, "300308", 100.0, 91.8, 1000, 10.0)
    if kind == "bad_win":
        did = _planned(store, size_pct=10)
        return _close(store, did, "300308", 100.0, 108.0, 1000, 25.0)
    if kind == "research_vs_expectation":
        did = _planned(
            store, thesis="AI CAPEX持续增长",
            expect="本周A股算力上涨",
        )
        return _close(store, did, "300308", 100.0, 92.0, 1000, 10.0)
    if kind == "size_violation":
        did = _planned(store, size_pct=10)
        return _close(store, did, "300308", 100.0, 99.0, 1000, 18.0)
    if kind == "emotion_unknown":
        did = _planned(store, thesis="回踩后继续看", expect="三日内修复")
        return _close(store, did, "300308", 110.0, 108.0, 1000, 10.0)
    if kind == "external_shock":
        did = _planned(store, thesis="产业逻辑还在", expect="价格跟随")
        return _close(store, did, "300308", 100.0, 90.0, 1000, 10.0)
    if kind == "no_plan":
        did = repo.create_decision(
            code="300308", name="中际旭创", thesis="", origin="POST_HOC",
            opened_on="2026-09-19", store=store,
        )
        quotes(store, "300308", [("2026-09-19", 100, 101, 99, 100), ("2026-09-23", 98, 99, 97, 98)])
        repo.add_execution(
            code="300308", executed_on="2026-09-19", executed_at="10:00:00",
            side="BUY", price=100, qty=1000, decision_id=did, planned="unknown",
            store=store,
        )
        repo.transition(did, lifecycle.ACTIVE, "事后壳", store=store)
        repo.add_execution(
            code="300308", executed_on="2026-09-23", executed_at="14:00:00",
            side="SELL", price=98, qty=1000, decision_id=did, store=store,
        )
        outcome.close_and_compute(did, store=store)
        gates.run(did, store)
        return did
    if kind == "partial_coverage":
        did = _planned(store, code="600089")
        quotes(store, "600089", [("2026-09-20", 31, 32, 30, 31)])  # missing start/end days
        repo.add_execution(
            code="600089", executed_on="2026-09-19", executed_at="10:00:00",
            side="BUY", price=31, qty=1000, decision_id=did, planned="yes",
            size_pct=10, store=store,
        )
        repo.advance(did, store=store)
        repo.add_execution(
            code="600089", executed_on="2026-09-23", executed_at="14:00:00",
            side="SELL", price=30, qty=1000, decision_id=did, planned="yes",
            store=store,
        )
        outcome.close_and_compute(did, store=store)
        gates.run(did, store)
        return did
    if kind == "winning_violation":
        return build("bad_win", store)
    if kind == "multiple_causes":
        did = _planned(store, size_pct=10)
        return _close(store, did, "300308", 100.0, 90.0, 1000, 18.0)
    raise ValueError("未知 fixture：{0}".format(kind))
