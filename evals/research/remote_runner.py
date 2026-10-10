"""python -m evals.research.remote_runner --model remote --set gate

不调用模型，也不写 PASS 报告。回归案例必须被抓住。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.research.remote_gate import regression_cases, score_regression  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="remote")
    parser.add_argument("--set", dest="case_set", default="gate")
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args(argv)
    if args.model != "remote" or args.case_set != "gate":
        print("SKIP 只接受 --model remote --set gate")
        return 2
    rows = [score_regression(case) for case in regression_cases()]
    if not rows or not all(row["caught"] for row in rows):
        print("FAIL remote regression")
        return 1
    print("regression PASS direct_exposure_overclaim caught={0}".format(
        ", ".join(row["id"] for row in rows)
    ))
    print("SKIP 没有跑远程模型，不写 research-remote-gate.json")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
