"""python -m evals.recorder.runner --model heuristic

数据集：dev / holdout / adversarial。
--model heuristic|remote 做 bakeoff。
Holdout+Adversarial 不过 Gate 则 Remote 不得升 primary。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.config import Settings  # noqa: E402
from core.llm.client import OpenAICompatibleClient  # noqa: E402
from core.review import migrate  # noqa: E402
from core.review.recorder.heuristic import HeuristicLLM  # noqa: E402
from core.review.recorder import service as recorder  # noqa: E402
from core.store import Store  # noqa: E402
from evals.recorder.adversarial import ADVERSARIAL_CASES  # noqa: E402
from evals.recorder.gate import can_promote_remote, evaluate_gate  # noqa: E402
from evals.recorder.gold import CASES, DEV_CASES  # noqa: E402
from evals.recorder.holdout import HOLDOUT_CASES  # noqa: E402
from evals.recorder.metrics import aggregate, score_case  # noqa: E402

DIR = Path(__file__).resolve().parent
SETS = {
    "dev": DEV_CASES,
    "holdout": HOLDOUT_CASES,
    "adversarial": ADVERSARIAL_CASES,
}


def _dump_jsonl() -> None:
    mapping = {
        "cases.jsonl": DEV_CASES,
        "dev.jsonl": DEV_CASES,
        "holdout.jsonl": HOLDOUT_CASES,
        "adversarial.jsonl": ADVERSARIAL_CASES,
    }
    for name, cases in mapping.items():
        (DIR / name).write_text(
            "\n".join(json.dumps(c, ensure_ascii=False) for c in cases) + "\n",
            encoding="utf-8",
        )


def _client(model: str):
    if model in ("heuristic", "offline"):
        return HeuristicLLM()
    if model in ("remote", "remote_a", "a"):
        return OpenAICompatibleClient()
    if model in ("remote_b", "b"):
        return OpenAICompatibleClient(model=os.environ.get("LLM_MODEL_B") or os.environ.get("LLM_MODEL") or "")
    raise SystemExit("未知 --model：{0}。允许 heuristic / remote / remote_b".format(model))


def resolve_cases(name: str) -> List[Dict[str, Any]]:
    if name == "all":
        return list(DEV_CASES) + list(HOLDOUT_CASES) + list(ADVERSARIAL_CASES)
    if name == "gate":
        return list(HOLDOUT_CASES) + list(ADVERSARIAL_CASES)
    if name not in SETS:
        raise SystemExit("未知 --set：{0}".format(name))
    return list(SETS[name])


def run_cases(
    cases: List[Dict[str, Any]] = None,
    live: bool = False,
    model: str = "heuristic",
    llm=None,
) -> Dict[str, Any]:
    tmp = tempfile.TemporaryDirectory()
    root = Path(tmp.name)
    store = Store(Settings(db_path=root / "e.db", http_cache_dir=root / "c"))
    store.init_schema()
    migrate.apply_all(store)
    if llm is not None:
        client = llm
    elif live or model not in ("heuristic", "offline"):
        client = _client(model)
    else:
        client = HeuristicLLM()
    rows = []
    for case in cases or CASES:
        env = case.get("envelope") or {}
        result = recorder.parse(
            case["raw_text"],
            known_symbol=env.get("known_symbol") or "",
            known_company=env.get("known_company") or "",
            mode=env.get("mode") or "premarket",
            draft_id=env.get("draft_id") or "",
            source="eval",
            llm=client,
            store=store,
        )
        draft = result.get("draft") or {
            "intent": "UNSUPPORTED", "plan": {}, "symbol": {}, "thesis": {},
            "expectations": [], "missing_fields": [],
        }
        row = score_case(case, draft, bool(result.get("grounding_ok", True)))
        row["status"] = result.get("status")
        rows.append(row)
    summary = aggregate(rows)
    summary["prompt_version"] = recorder.PROMPT_VERSION
    summary["model"] = getattr(client, "name", model)
    summary["rows"] = rows
    ok, reasons = evaluate_gate(summary)
    summary["gate_pass"] = ok
    summary["gate_reasons"] = reasons
    summary["remote_primary_allowed"] = bool(ok and model != "heuristic")
    tmp.cleanup()
    return summary


def render(summary: Dict[str, Any]) -> str:
    lines = [
        "Recorder Eval {0}  model={1}".format(
            summary.get("prompt_version"), summary.get("model"),
        ),
        "",
        "Cases                    {0}".format(summary["cases"]),
        "Critical Field Recall    {0}%".format(summary["critical_field_recall"]),
        "Unsupported Field Rate    {0}%".format(summary["unsupported_field_rate"]),
        "Critical Hallucination    {0}%  (count={1})".format(
            summary["critical_hallucination_rate"], summary["critical_hallucination_count"],
        ),
        "Missing Detection Recall {0}%".format(summary["missing_detection_recall"]),
        "Abstention Accuracy      {0}%".format(summary["abstention_accuracy"]),
        "Negation Error Rate      {0}%  (count={1})".format(
            summary.get("negation_error_rate"), summary.get("negation_error_count"),
        ),
        "Correction Error Rate    {0}%  (count={1})".format(
            summary.get("correction_error_rate"), summary.get("correction_error_count"),
        ),
        "Wrong Number Binding     {0}%  (count={1})".format(
            summary.get("wrong_number_binding_rate"), summary.get("wrong_number_binding_count"),
        ),
        "Wrong Symbol Critical    {0}".format(summary.get("wrong_symbol_critical_count")),
        "Gate                     {0}".format("PASS" if summary.get("gate_pass") else "FAIL"),
    ]
    if summary.get("gate_reasons"):
        for item in summary["gate_reasons"]:
            lines.append("  - {0}".format(item))
    if summary.get("failures"):
        lines.append("")
        lines.append("Failures:")
        for item in summary["failures"][:40]:
            lines.append(
                "  {0}  {1}  {2}  got={3!r} gold={4!r}".format(
                    item["id"], item["type"], item["field"], item["got"], item["gold"],
                )
            )
    return "\n".join(lines)


def bakeoff(cases: List[Dict[str, Any]], models: List[str]) -> Dict[str, Any]:
    table = {}
    for name in models:
        try:
            table[name] = run_cases(cases, model=name)
        except Exception as exc:  # noqa: BLE001
            table[name] = {"error": str(exc), "gate_pass": False, "model": name}
    keys = (
        "critical_field_recall", "unsupported_field_rate", "critical_hallucination_count",
        "missing_detection_recall", "abstention_accuracy", "negation_error_rate",
        "correction_error_rate", "wrong_number_binding_rate", "gate_pass",
    )
    comparison = {k: {m: (table[m] or {}).get(k) for m in models} for k in keys}
    promote = {
        m: can_promote_remote(table[m]) if "error" not in table[m] else False
        for m in models
    }
    return {"models": table, "comparison": comparison, "can_promote_remote": promote}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--live", action="store_true", help="调用远程 LLM（需 API key）")
    p.add_argument("--model", default="heuristic", help="heuristic | remote | remote_b")
    p.add_argument("--set", default="dev", help="dev | holdout | adversarial | gate | all")
    p.add_argument("--bakeoff", action="store_true")
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)
    _dump_jsonl()
    cases = resolve_cases(args.set)
    model = "remote" if args.live and args.model == "heuristic" else args.model
    if args.bakeoff:
        models = ["heuristic", "remote"]
        if os.environ.get("LLM_MODEL_B"):
            models.append("remote_b")
        payload = bakeoff(cases, models)
        (DIR / "reports").mkdir(exist_ok=True)
        out = DIR / "reports" / "bakeoff.json"
        slim = {
            "comparison": payload["comparison"],
            "can_promote_remote": payload["can_promote_remote"],
            "gate": {
                m: {
                    "gate_pass": (payload["models"][m] or {}).get("gate_pass"),
                    "gate_reasons": (payload["models"][m] or {}).get("gate_reasons"),
                    "error": (payload["models"][m] or {}).get("error"),
                }
                for m in models
            },
        }
        out.write_text(json.dumps(slim, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(slim, ensure_ascii=False, indent=2))
        heuristic_ok = payload["models"]["heuristic"].get("gate_pass")
        return 0 if heuristic_ok else 1

    summary = run_cases(cases, live=args.live, model=model)
    (DIR / "reports").mkdir(exist_ok=True)
    report = dict(summary)
    report.pop("rows", None)
    (DIR / "reports" / "{0}-{1}.json".format(args.set, summary.get("model") or model)).write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    else:
        print(render(summary))
    if args.set in ("holdout", "adversarial", "gate", "all"):
        return 0 if summary.get("gate_pass") else 1
    if summary["critical_hallucination_count"] > 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
