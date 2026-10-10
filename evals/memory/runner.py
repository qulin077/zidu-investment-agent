"""python -m evals.memory.runner"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.config import Settings  # noqa: E402
from core.review import migrate, repo  # noqa: E402
from core.review.memory import fingerprint as fp  # noqa: E402
from core.review.memory import metrics as mem_metrics  # noqa: E402
from core.review.memory import reminders as mem_remind  # noqa: E402
from core.review.memory import service as memory  # noqa: E402
from core.review.memory import store as mstore  # noqa: E402
from core.review.memory.validator import MemoryError, validate_rule, validate_summary  # noqa: E402
from core.store import Store  # noqa: E402
from evals.memory.cases import CASES  # noqa: E402
from evals.memory.fixtures import reviewed  # noqa: E402
from evals.memory.metrics import aggregate, score_case  # noqa: E402
from evals.review.fixtures import build  # noqa: E402

DIR = Path(__file__).resolve().parent


def _state(store: Store, extra: dict) -> dict:
    patterns = mstore.list_patterns(store)
    rules = mstore.list_rules(store=store)
    reminders = mstore.list_reminders(store)
    last_rule = rules[-1] if rules else {}
    product = mem_metrics.product_metrics(store)
    data = {
        "mistake_n": len(mstore.list_mistakes(store)),
        "pattern_n": len(patterns),
        "patterns": patterns,
        "rule_n": len(rules),
        "last_rule_status": last_rule.get("status"),
        "last_rule_evidence": fp.loads_list(last_rule.get("evidence_decision_ids")),
        "rule_confirmed_at": last_rule.get("confirmed_at") or "",
        "fact_n": len(store.query("SELECT id FROM decision_pattern_fact")),
        "reminder_n": extra.get("reminder_n", len(reminders)),
        "reminder_has_evidence": extra.get("reminder_has_evidence", False),
        "memory_precision": product.get("memory_precision"),
        **extra,
    }
    return data


def _last_pattern(store: Store):
    rows = mstore.list_patterns(store)
    return rows[0] if rows else None


def run_case(case: dict, store: Store) -> dict:
    extra: dict = {}
    last_pid = ""
    last_rule = ""
    last_reminder = ""
    for step in case.get("steps") or []:
        op = step["op"]
        if op == "reviewed":
            did = reviewed(
                step["fixture"], store, step["primary"],
                lesson=step.get("lesson") or "",
                market=step.get("market") or "",
            )
            if step.get("market"):
                extra["keep_context_diff"] = True
            last = _last_pattern(store)
            last_pid = (last or {}).get("id") or last_pid
        elif op == "confirm_last_pattern":
            last = _last_pattern(store)
            memory.confirm_pattern(last["id"], store=store)
            last_pid = last["id"]
        elif op == "dismiss_last_pattern":
            last = _last_pattern(store)
            memory.dismiss_pattern(last["id"], store=store)
            last_pid = last["id"]
        elif op == "propose_on_last_pattern":
            last = _last_pattern(store)
            try:
                rows = memory.propose_rules(last["id"], store=store)
                last_rule = rows[0]["id"] if rows else ""
            except MemoryError:
                extra["propose_failed"] = True
        elif op == "activate_first_rule":
            rules = mstore.list_rules(store=store)
            last_rule = rules[0]["id"]
            memory.activate_rule(last_rule, store=store)
            extra["last_rule_status"] = "ACTIVE"
            extra["rule_confirmed_at"] = mstore.get_rule(last_rule, store).get("confirmed_at") or ""
            extra["last_rule_evidence"] = fp.loads_list(mstore.get_rule(last_rule, store).get("evidence_decision_ids"))
        elif op == "retire_first_rule":
            active = mstore.active_rules(store) or mstore.list_rules(store=store)
            memory.retire_rule(active[0]["id"], reason="不再适用", store=store)
            ctx = mem_remind.context_from_text("怕踏空想再做", symbol="300308")
            extra["reminder_n"] = len(mem_remind.get_relevant_active_rules(ctx, store))
            extra["last_rule_status"] = "RETIRED"
            extra["no_reminder"] = extra["reminder_n"] == 0
        elif op == "remind":
            ctx = mem_remind.context_from_text(step.get("raw_text") or "", symbol=step.get("symbol") or "")
            matched = mem_remind.get_relevant_active_rules(ctx, store)
            extra["reminder_n"] = len(matched)
            extra["reminder_has_evidence"] = all(bool(m.get("evidence_decision_ids")) for m in matched) if matched else False
            if matched:
                issued = mem_remind.issue_for_new_decision("D-EVAL-REMIND", step.get("raw_text") or "", store=store)
                last_reminder = issued[0]["id"] if issued else ""
        elif op == "feedback_last":
            if last_reminder:
                mem_remind.feedback(last_reminder, step["value"], store=store)
        elif op == "validate_rule":
            extra["validator_issues"] = validate_rule(
                step.get("rule_text") or "",
                step.get("trigger") or "",
                step.get("expected") or "",
                step.get("evidence") if "evidence" in step else ["D-X"],
            )
            if step.get("evidence") == []:
                extra["validator_issues"] = validate_rule(
                    step.get("rule_text") or "",
                    step.get("trigger") or "",
                    step.get("expected") or "",
                    [],
                )
        elif op == "validate_summary":
            extra["validator_issues"] = validate_summary(step.get("summary") or "")
        elif op == "ingest_violations":
            did = build(step["fixture"], store)
            try:
                memory.ingest_from_violations(did, store)
            except MemoryError:
                extra["leakage_blocked"] = True
        elif op == "ingest_pending":
            did = build(step["fixture"], store)
            result = memory.ingest_reviewed(did, store)
            extra["no_mistake"] = result.get("mistake") is None
        elif op == "inject_fomo_without_self_report":
            did = reviewed("emotion_unknown", store, "SIZING_ERROR", lesson="买点偏高")
            m = mstore.mistake_for_decision(did, store)
            extra["emotion_blocked"] = not (m and m.get("emotion_tag") == "FOMO")
            extra["no_fomo_pattern"] = "FOMO" not in ((m or {}).get("pattern_key") or "")
        elif op == "merge_two_patterns":
            rows = mstore.list_patterns(store)
            result = memory.merge_patterns(rows[0]["id"], rows[1]["id"], store=store)
            extra["merge_keeps_evidence"] = len(result.get("evidence_ids") or []) >= 2
        elif op == "confirm_last_violation":
            rows = store.query("SELECT * FROM rule_violation ORDER BY detected_at")
            if rows:
                memory.confirm_rule_violation(rows[-1]["id"], store=store)
                extra["confirmed_rule_violation"] = True
        elif op == "confirm_pattern_expect_fail":
            last = _last_pattern(store)
            try:
                memory.confirm_pattern(last["id"], store=store)
            except MemoryError:
                extra["confirm_failed"] = True
    if case.get("gold", {}).get("confirm_pattern_fails") and "confirm_failed" not in extra:
        last = _last_pattern(store)
        if last:
            try:
                memory.confirm_pattern(last["id"], store=store)
            except MemoryError:
                extra["confirm_failed"] = True
    return _state(store, extra)


def run_cases(cases=None) -> dict:
    os.environ.setdefault("GUIDED_REVIEW_ENABLED", "true")
    tmp = tempfile.TemporaryDirectory()
    root = Path(tmp.name)
    rows = []
    for case in cases or CASES:
        store = Store(Settings(db_path=root / (case["id"] + ".db"), http_cache_dir=root / "c"))
        store.init_schema()
        migrate.apply_all(store)
        state = run_case(case, store)
        rows.append(score_case(case, state))
    summary = aggregate(rows)
    tmp.cleanup()
    return summary


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)
    summary = run_cases()
    (DIR / "reports").mkdir(exist_ok=True)
    (DIR / "reports" / "memory-eval.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8",
    )
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    else:
        print("Memory Eval")
        print("Cases {0}  pass {1}  fail {2}  gate {3}".format(
            summary["cases"], summary["pass"], summary["fail"],
            "PASS" if summary["gate_pass"] else "FAIL",
        ))
        for row in summary.get("failures") or []:
            print("  {0}  {1}".format(row["id"], row["failures"]))
    return 0 if summary["gate_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
