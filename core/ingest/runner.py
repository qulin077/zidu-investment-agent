"""采集编排入口。

用法：
    python3 -m core.ingest.runner backfill     # 回灌现有文件
    python3 -m core.ingest.runner refresh      # 实时拉取池内行情
    python3 -m core.ingest.runner status       # 查看各数据集契约状态
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from typing import List

from core.contracts import inspect_all
from core import config
from core.ingest.backfill import BACKFILL_STEPS
from core.ingest.base import IngestResult
from core.ingest.live import refresh_quotes
from core.ingest.manifest import record as record_manifest
from core.store import STORE, Store
from core.symbols import universe_codes


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _report(results: List[IngestResult]) -> None:
    width = max((len(r.dataset) for r in results), default=10)
    print("\n{0:<{1}}  {2:>8}  {3:<12}  {4}".format("数据集", width, "行数", "最新", "状态"))
    print("-" * (width + 40))
    for item in results:
        mark = "OK " if item.ok else "FAIL"
        note = item.message or ("跳过 {0} 项".format(len(item.skipped)) if item.skipped else "")
        print(
            "{0:<{1}}  {2:>8}  {3:<12}  {4} {5}".format(
                item.dataset, width, item.rows, item.asof or "-", mark, note
            )
        )


def run_backfill(store: Store = STORE) -> List[IngestResult]:
    store.init_schema()
    results: List[IngestResult] = []
    for label, step in BACKFILL_STEPS:
        print("[回灌] {0} ...".format(label), flush=True)
        outcome = step(store)
        store.record_run(
            dataset=outcome.dataset,
            ran_at=_now(),
            asof=outcome.asof,
            rows=outcome.rows,
            ok=outcome.ok,
            message=outcome.message,
        )
        for source_uri, source_kind in _sources_for(outcome.dataset):
            record_manifest(
                store, dataset=outcome.dataset, source_uri=source_uri,
                source_kind=source_kind, as_of=outcome.asof,
                target_table=outcome.dataset, rows_written=outcome.rows,
                status="INGESTED" if outcome.ok else "FAILED", message=outcome.message,
            )
        results.append(outcome)
    return results


def run_refresh(store: Store = STORE, limit: int = 120) -> List[IngestResult]:
    store.init_schema()
    codes = universe_codes()
    print("[实时] 拉取 {0} 只标的日线 ...".format(len(codes)), flush=True)
    outcome = refresh_quotes(codes, limit=limit, store=store)
    store.record_run(
        dataset=outcome.dataset,
        ran_at=_now(),
        asof=outcome.asof,
        rows=outcome.rows,
        ok=outcome.ok,
        message=outcome.message,
    )
    record_manifest(
        store, dataset=outcome.dataset, source_uri="market-data-provider://quotes",
        source_kind="REMOTE", as_of=outcome.asof, target_table=outcome.dataset,
        rows_written=outcome.rows, status="INGESTED" if outcome.ok else "FAILED",
        message=outcome.message,
    )
    return [outcome]


def _sources_for(dataset: str) -> list:
    mapping = {
        "instrument": [(str(config.UNIVERSE_YAML), "FILE")],
        "quote_daily": [(str(config.QUOTES_DIR), "DIRECTORY")],
        "news_item": [
            (str(config.JIN10_DIR), "DIRECTORY"),
            (str(config.NARRATIVE_DIR), "DIRECTORY"),
            (str(config.POLICY_DIR), "DIRECTORY"),
        ],
        "position_snapshot": [(str(config.HOLDINGS_SNAPSHOT_CSV), "FILE")],
        "account_snapshot": [(str(config.ACCOUNT_SNAPSHOT_CSV), "FILE")],
        "trade": [(str(config.TRADES_CSV), "FILE")],
    }
    return mapping.get(dataset, [("pipeline://{0}".format(dataset), "PIPELINE")])


def print_status(store: Store = STORE) -> bool:
    store.init_schema()
    statuses = inspect_all(store=store, universe_size=len(universe_codes()))
    width = max((len(s.name) for s in statuses), default=10)
    print("\n{0:<{1}}  {2:>9}  {3:<12}  {4}".format("数据集", width, "行数", "最新", "状态"))
    print("-" * (width + 46))
    for item in statuses:
        mark = "OK " if item.ok else "STALE"
        issues = "；".join(item.issues)
        print(
            "{0:<{1}}  {2:>9}  {3:<12}  {4} {5}".format(
                item.name, width, item.rows, item.asof or "-", mark, issues
            )
        )
    print("\n库文件: {0}".format(store.path))
    return all(s.ok for s in statuses)


def main(argv: List[str] = None) -> int:
    parser = argparse.ArgumentParser(description="数据采集编排")
    parser.add_argument(
        "command", choices=["backfill", "refresh", "status"], help="执行的操作"
    )
    parser.add_argument("--limit", type=int, default=120, help="实时拉取的K线根数")
    args = parser.parse_args(argv)

    if args.command == "status":
        return 0 if print_status() else 1

    if args.command == "backfill":
        results = run_backfill()
    else:
        results = run_refresh(limit=args.limit)

    _report(results)
    print_status()
    return 0 if all(r.ok for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
