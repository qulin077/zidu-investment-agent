#!/usr/bin/env python3
"""Decision Capture CLI —— P0 的唯一入口。

不接 LLM。所有内容都是用户手打，系统只负责结构化、校验状态机、算确定性结果。

一条决策的完整走法：

    review_cli.py new    --code 300308 --name 中际旭创 --thesis "..." --earning-type E2
    review_cli.py expect D-... --text "..." --window 2026-09-19:2026-09-23 --confidence 3
    review_cli.py plan   D-... --entry "..." --size-pct 10 --stop 96 --invalidation "..."
    review_cli.py promote D-...                      # DRAFT → PLANNED
    review_cli.py exec   D-... --date 2026-09-19 --side BUY  --price 100 --qty 1000 --planned yes
    review_cli.py close  D-...                       # → CLOSED → outcome → REVIEW_PENDING
    review_cli.py gates  D-...
    review_cli.py review D-... --primary-error TIMING_ERROR --lesson "..." --confirm
    review_cli.py show   D-...
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.review import card, gates, legacy, lifecycle, metrics, migrate, outcome, repo  # noqa: E402
from core.review.defs import error_types  # noqa: E402
from core.store import STORE  # noqa: E402


def _out(payload) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


def _window(raw: str):
    if not raw:
        return "", ""
    if ":" in raw:
        start, _, end = raw.partition(":")
        return start.strip(), end.strip()
    return raw.strip(), raw.strip()


# ------------------------------------------------------------------ commands


def cmd_migrate(args) -> int:
    if args.status:
        _out(migrate.status())
        return 0
    applied = migrate.apply_all()
    _out({"applied": applied or "（无待执行迁移）", "db": str(STORE.path)})
    return 0


def cmd_new(args) -> int:
    did = repo.create_decision(
        code=args.code,
        name=args.name,
        thesis=args.thesis,
        earning_type=args.earning_type,
        holding_period=args.holding_period,
        market_context=args.market_context,
        direction=args.direction,
        opened_on=args.date,
        account=args.account,
    )
    _out({"decision_id": did, "status": lifecycle.DRAFT, "origin": "EX_ANTE",
          "next": "补 expect 和 plan，然后 promote"})
    return 0


def cmd_expect(args) -> int:
    start, end = _window(args.window)
    eid = repo.add_expectation(
        args.decision_id, args.text, window_start=start, window_end=end,
        confidence=args.confidence,
    )
    _out({"expectation_id": eid, "predicate": "P0 不编译，字段已占位",
          "counts_toward_prediction_accuracy": False})
    return 0


def cmd_plan(args) -> int:
    pid = repo.add_plan(
        args.decision_id,
        entry_rule=args.entry,
        invalidation=args.invalidation,
        target_size_pct=args.size_pct,
        target_size_amount=args.size_amount,
        stop_price=args.stop,
        stop_rule=args.stop_rule,
        add_rule=args.add_rule,
        reduce_rule=args.reduce_rule,
        holding_period=args.holding_period,
        entry_window_start=_window(args.entry_window)[0],
        entry_window_end=_window(args.entry_window)[1],
        reason_for_revision=args.reason,
    )
    _out({"plan_id": pid})
    return 0


def cmd_promote(args) -> int:
    _out(repo.transition(args.decision_id, lifecycle.PLANNED, args.reason or "事前记录齐全"))
    return 0


def cmd_exec(args) -> int:
    did = None if args.orphan else args.decision_id
    row = repo.require_decision(did, STORE) if did else {}
    if did:
        subj = "available" if repo.has_recorded_context(did, STORE) else "not_recorded"
        source = "trade_import"
    else:
        subj = "not_recorded"
        source = "trade_import"
    xid = repo.add_execution(
        code=args.code or row.get("code", ""),
        executed_on=args.date,
        side=args.side.upper(),
        price=args.price,
        qty=args.qty,
        decision_id=did,
        name=row.get("name", ""),
        executed_at=args.time,
        amount=args.amount,
        size_pct=args.size_pct,
        planned=args.planned,
        note=args.note,
        source=source,
        subjective_context=subj,
    )
    moved = repo.advance(did) if did else []
    _out({"execution_id": xid, "transitions": moved})
    return 0


def cmd_attach(args) -> int:
    from core.review import matching

    result = matching.confirm(
        args.execution_id, args.decision_id, operator="user",
        note="CLI attach",
    )
    if args.planned:
        repo.amend(
            "execution", args.execution_id, "planned", args.planned,
            reason="复盘时补记是否计划内",
        )
    result["transitions"] = repo.advance(args.decision_id)
    _out(result)
    return 0


def cmd_orphans(args) -> int:
    _out({"orphans": repo.orphan_executions(code=args.code, limit=args.limit),
          "stats": legacy.stats()})
    return 0


def cmd_close(args) -> int:
    result = outcome.close_and_compute(args.decision_id)
    gates.run(args.decision_id)
    _out({"outcome": result, "violations": repo.violations(args.decision_id)})
    return 0


def cmd_gates(args) -> int:
    found = gates.run(args.decision_id)
    _out({
        "violations": found,
        "layer": "A / process compliance（事实）",
        "suggested_error_types": gates.suggestions([v["code"] for v in found]),
        "warning": "候选仅供人选。Process Violation 不等于 Error Attribution。",
    })
    return 0


def cmd_review(args) -> int:
    did = args.decision_id
    rid = repo.add_review(
        did, lesson=args.lesson, user_note=args.note,
        outcome_confirmed=args.confirm, violations_confirmed=args.confirm,
    )
    if args.confirm:
        repo.acknowledge_violations(did)
    aid = repo.add_attribution(
        did, rid,
        primary_error=args.primary_error,
        contributing=args.contributing or [],
        counterfactual=args.counterfactual,
        confidence=args.confidence,
        evidence=args.evidence or [],
        user_confirmed=args.confirm,
    )
    moved = None
    if args.confirm:
        moved = repo.transition(did, lifecycle.REVIEWED, "复盘完成")
    _out({"review_id": rid, "attribution_id": aid, "transition": moved,
          "status": repo.require_decision(did)["status"]})
    return 0


def cmd_amend(args) -> int:
    _out(repo.amend(args.table, args.row_id, args.field, args.value, reason=args.reason))
    return 0


def cmd_show(args) -> int:
    if args.json:
        _out(card.build(args.decision_id))
    else:
        print(card.render(args.decision_id))
    return 0


def cmd_list(args) -> int:
    rows = repo.list_decisions(status=args.status, code=args.code, limit=args.limit)
    _out([{k: r[k] for k in ("id", "opened_on", "code", "name", "status", "thesis")} for r in rows])
    return 0


def cmd_metrics(args) -> int:
    _out(metrics.summary(args.start, args.end))
    return 0


def cmd_import_legacy(args) -> int:
    _out(legacy.import_trades(limit=args.limit))
    return 0


def cmd_errors(_args) -> int:
    from core.review.defs import load

    _out({"error_types": load().get("error_types"),
          "process_violations": load().get("process_violations")})
    return 0


# -------------------------------------------------------------------- parser


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="review_cli.py", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    m = sub.add_parser("migrate", help="建表 / 查看迁移状态")
    m.add_argument("--status", action="store_true")
    m.set_defaults(fn=cmd_migrate)

    n = sub.add_parser("new", help="新建 Decision（DRAFT）")
    n.add_argument("--code", required=True)
    n.add_argument("--name", default="")
    n.add_argument("--thesis", default="")
    n.add_argument("--earning-type", default="")
    n.add_argument("--holding-period", default="")
    n.add_argument("--market-context", default="")
    n.add_argument("--direction", default="long", choices=["long", "short"])
    n.add_argument("--date", default="")
    n.add_argument("--account", default="")
    n.set_defaults(fn=cmd_new)

    e = sub.add_parser("expect", help="追加一条可证伪预期")
    e.add_argument("decision_id")
    e.add_argument("--text", required=True)
    e.add_argument("--window", default="", help="YYYY-MM-DD:YYYY-MM-DD")
    e.add_argument("--confidence", type=int, default=None, help="1–5 用户自评")
    e.set_defaults(fn=cmd_expect)

    pl = sub.add_parser("plan", help="追加一版计划（改计划必须写 --reason）")
    pl.add_argument("decision_id")
    pl.add_argument("--entry", default="")
    pl.add_argument("--invalidation", default="")
    pl.add_argument("--size-pct", type=float, default=None)
    pl.add_argument("--size-amount", type=float, default=None)
    pl.add_argument("--stop", type=float, default=None)
    pl.add_argument("--stop-rule", default="")
    pl.add_argument("--add-rule", default="")
    pl.add_argument("--reduce-rule", default="")
    pl.add_argument("--holding-period", default="")
    pl.add_argument("--entry-window", default="", help="YYYY-MM-DD:YYYY-MM-DD")
    pl.add_argument("--reason", default="", help="改计划的理由（v2 起必填）")
    pl.set_defaults(fn=cmd_plan)

    pr = sub.add_parser("promote", help="DRAFT → PLANNED")
    pr.add_argument("decision_id")
    pr.add_argument("--reason", default="")
    pr.set_defaults(fn=cmd_promote)

    x = sub.add_parser("exec", help="登记一笔成交")
    x.add_argument("decision_id", nargs="?", default="")
    x.add_argument("--orphan", action="store_true", help="不挂 Decision（decision_id=NULL）")
    x.add_argument("--code", default="")
    x.add_argument("--date", required=True)
    x.add_argument("--time", default="")
    x.add_argument("--side", required=True, choices=["BUY", "SELL", "buy", "sell"])
    x.add_argument("--price", type=float, required=True)
    x.add_argument("--qty", type=float, required=True)
    x.add_argument("--amount", type=float, default=None)
    x.add_argument("--size-pct", type=float, default=None)
    x.add_argument("--planned", default="unknown", choices=["yes", "no", "unknown"])
    x.add_argument("--note", default="")
    x.set_defaults(fn=cmd_exec)

    at = sub.add_parser("attach", help="把孤儿 execution 挂到 Decision")
    at.add_argument("execution_id")
    at.add_argument("decision_id")
    at.add_argument("--planned", default="", choices=["", "yes", "no", "unknown"])
    at.set_defaults(fn=cmd_attach)

    orp = sub.add_parser("orphans", help="列出未关联 Decision 的 execution")
    orp.add_argument("--code", default="")
    orp.add_argument("--limit", type=int, default=20)
    orp.set_defaults(fn=cmd_orphans)

    cl = sub.add_parser("close", help="了结 → 算 outcome → REVIEW_PENDING")
    cl.add_argument("decision_id")
    cl.set_defaults(fn=cmd_close)

    g = sub.add_parser("gates", help="跑 Process Gate（Layer A）")
    g.add_argument("decision_id")
    g.set_defaults(fn=cmd_gates)

    rv = sub.add_parser("review", help="复盘并归因（Layer B）→ REVIEWED")
    rv.add_argument("decision_id")
    rv.add_argument("--primary-error", required=True, choices=error_types())
    rv.add_argument("--contributing", nargs="*", default=[], choices=error_types())
    rv.add_argument("--counterfactual", default="")
    rv.add_argument("--confidence", default="medium", choices=["high", "medium", "low"])
    rv.add_argument("--evidence", nargs="*", default=[])
    rv.add_argument("--lesson", default="")
    rv.add_argument("--note", default="")
    rv.add_argument("--confirm", action="store_true", help="确认 outcome/违规/归因，落 REVIEWED")
    rv.set_defaults(fn=cmd_review)

    am = sub.add_parser("amend", help="改字段（原值进 revision，不丢）")
    am.add_argument("table")
    am.add_argument("row_id")
    am.add_argument("field")
    am.add_argument("value")
    am.add_argument("--reason", required=True)
    am.set_defaults(fn=cmd_amend)

    sh = sub.add_parser("show", help="Decision Card")
    sh.add_argument("decision_id")
    sh.add_argument("--json", action="store_true")
    sh.set_defaults(fn=cmd_show)

    ls = sub.add_parser("list", help="列出 Decision")
    ls.add_argument("--status", default="")
    ls.add_argument("--code", default="")
    ls.add_argument("--limit", type=int, default=20)
    ls.set_defaults(fn=cmd_list)

    mt = sub.add_parser("metrics", help="确定性指标（带分母）")
    mt.add_argument("--start", default="")
    mt.add_argument("--end", default="")
    mt.set_defaults(fn=cmd_metrics)

    il = sub.add_parser("import-legacy", help="历史流水 → execution（decision_id=NULL）")
    il.add_argument("--limit", type=int, default=0)
    il.set_defaults(fn=cmd_import_legacy)

    er = sub.add_parser("errors", help="查看冻结的错误类型与违规类型")
    er.set_defaults(fn=cmd_errors)

    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.fn(args)
    except (repo.ReviewError, lifecycle.IllegalTransition, lifecycle.GuardFailed) as exc:
        print("拒绝：{0}".format(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
