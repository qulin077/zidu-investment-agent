# Recorder Eval V0

```bash
python -m evals.recorder.runner
```

- 默认 `HeuristicLLM`（受限抽取，不编造关键字段）。
- `--model heuristic|remote`；`--set dev|holdout|adversarial|gate`。
- `--live` 才打远程模型（需要 `OPENAI_API_KEY` 或 `LLM_API_KEY`）。
- **DEV**：30 条（`gold.py` / `dev.jsonl` / `cases.jsonl`）。
- **HOLDOUT + ADVERSARIAL**：≥40 条，prompt 调试期间不逐条针对优化。
- Holdout/Adversarial **Critical Hallucination / Negation / Wrong Symbol / Wrong Number > 0 → 非零退出。**
- 不过 Gate 不得把 Remote 设为 primary。

离线 r1 基线：

```
Cases                    30
Critical Field Recall    100.0%
Unsupported Field Rate    0.0%
Critical Hallucination    0.0%
Missing Detection Recall 100.0%
Abstention Accuracy      100.0%
```

这组分数锁定 Harness，不证明远程模型已经完美。改 prompt 必须升 `RECORDER_PROMPT_VERSION` 并重跑。
