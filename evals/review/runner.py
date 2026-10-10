"""python -m evals.review.runner"""
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
from core.review import migrate  # noqa: E402
from core.review.guided import questions, service as guided, validator  # noqa: E402
from core.review.guided.facts import build_context  # noqa: E402
from core.store import Store  # noqa: E402
from evals.review.cases import CASES  # noqa: E402
from evals.review.fixtures import build  # noqa: E402
from evals.review.metrics import aggregate, score_case  # noqa: E402

DIR = Path(__file__).resolve().parent


def run_cases(cases=None) -> dict:
    os.environ["GUIDED_REVIEW_ENABLED"] = "true"
    tmp = tempfile.TemporaryDirectory()
    root = Path(tmp.name)
    store = Store(Settings(db_path=root / "e.db", http_cache_dir=root / "c"))
    store.init_schema()
    migrate.apply_all(store)
    rows = []
    for case in cases or CASES:
        did = build(case["fixture"], store)
        if case.get("inject"):
            facts = build_context(did, store)
            payload = dict(case["inject"])
            payload.setdefault("decision_id", did)
            issues = validator.validate(payload, facts)
            scored = score_case(case, payload, facts, issues)
        else:
            started = guided.start(did, store=store)
            facts = started["facts"]
            turn = started["turn"]
            for step in case.get("gold", {}).get("after") or []:
                if step == "outcome":
                    started = guided.confirm_outcome(did, store=store)
                elif step == "violations":
                    started = guided.confirm_violations(did, store=store)
                facts = started["facts"]
                turn = started["turn"]
            issues = validator.validate(turn, facts)
            scored = score_case(case, turn, facts, issues)
        rows.append(scored)
    summary = aggregate(rows)
    summary["prompt_version"] = guided.PROMPT_VERSION
    tmp.cleanup()
    return summary


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)
    summary = run_cases()
    (DIR / "reports").mkdir(exist_ok=True)
    (DIR / "reports" / "review-eval.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8",
    )
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    else:
        print("Guided Review Eval {0}".format(summary.get("prompt_version")))
        print("Cases {0}  pass {1}  fail {2}  gate {3}".format(
            summary["cases"], summary["pass"], summary["fail"],
            "PASS" if summary["gate_pass"] else "FAIL",
        ))
        for row in summary.get("failures") or []:
            print("  {0}  {1}".format(row["id"], row["failures"]))
    return 0 if summary["gate_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
