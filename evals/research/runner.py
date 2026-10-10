"""python -m evals.research.runner"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.research.claims import derive_status  # noqa: E402
from core.research.conflicts import contains_average, detect, merged_value  # noqa: E402
from core.research.tools import search_web  # noqa: E402
from core.research.types import OUTPUT_KEYS  # noqa: E402
from core.research.validator import validate  # noqa: E402
from evals.research.cases import CASES  # noqa: E402
from evals.research.bad_cases import load_cases as load_bad_cases, score as score_bad_case  # noqa: E402
from evals.research.metrics import empty_gates, failed  # noqa: E402

DIR = Path(__file__).resolve().parent


def run_all(model: str = "fixture") -> dict:
    gates = empty_gates()
    rows = []
    for case in CASES():
        row = _run_case(case, gates)
        rows.append(row)
    for case in load_bad_cases():
        rows.append(score_bad_case(case))
    hard = failed(gates)
    case_fail = sum(1 for row in rows if not row["ok"])
    return {
        "status": "FAIL" if hard or case_fail else "PASS",
        "model": model,
        "cases": len(rows),
        "failed": case_fail,
        "gates": gates,
        "rows": rows,
    }


def _run_case(case: dict, gates: dict) -> dict:
    op = case.get("op") or "validate"
    if op == "search_web":
        result = search_web("AI电源")
        ok = (not result.get("ok")) and result.get("error_code") == "SEARCH_FAILED" and result.get("abstain")
        return {"id": case["id"], "name": case["name"], "ok": bool(ok), "detail": result.get("error_code")}
    if op == "three_themes":
        missing = []
        for draft in case["drafts"]:
            errors = validate(draft)
            if errors:
                missing.append(errors[0]["code"])
            for key in OUTPUT_KEYS:
                if key not in draft:
                    missing.append(key)
        ok = not missing
        return {"id": case["id"], "name": case["name"], "ok": ok, "detail": ",".join(missing)}

    errors = validate(case["draft"])
    codes = {item["code"] for item in errors}
    expect = case["expect"]
    ok = True
    detail = ""
    if expect == "accept":
        ok = not errors
        detail = errors[0]["message"] if errors else ""
        if ok and case.get("check") == "single":
            ok = derive_status(case["draft"]["evidence"]) == "SINGLE_SOURCE"
        if ok and case.get("check") == "corroborated":
            ok = derive_status(case["draft"]["evidence"]) == "CORROBORATED"
        if ok and case.get("check") == "conflict":
            found = detect(case["draft"]["claims"])
            ok = len(found) == 1 and merged_value(case["draft"]["claims"]) is None and not contains_average(case["draft"]["claims"])
        if ok and case.get("check") == "thematic":
            ok = case["draft"]["company_mapping"][0]["exposure_type"] == "THEMATIC"
    else:
        ok = bool(errors) and (not case.get("code") or case["code"] in codes)
        detail = ",".join(sorted(codes))
        if not ok and case.get("gate"):
            gates[case["gate"]] = gates.get(case["gate"], 0) + 1
    return {"id": case["id"], "name": case["name"], "ok": ok, "detail": detail}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="fixture", choices=("fixture", "remote"))
    parser.add_argument("--set", dest="eval_set", default="gate", choices=("gate", "shadow"))
    args = parser.parse_args(argv)
    if args.model == "remote":
        print("SKIP remote {0}: CI 不调用付费模型。正式 Thesis 仍要 fixture Gate 通过后才打开。".format(args.eval_set))
        return 2
    report = run_all(model="fixture")
    out = DIR / "reports" / "research-eval.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps({k: report[k] for k in ("status", "model", "cases", "failed", "gates")}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print("{0} model={1} cases={2} failed={3} gates={4}".format(
        report["status"], report["model"], report["cases"], report["failed"], report["gates"],
    ))
    if report["status"] != "PASS":
        for row in report["rows"]:
            if not row["ok"]:
                print("FAIL {0} {1} {2}".format(row["id"], row["name"], row["detail"]))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
