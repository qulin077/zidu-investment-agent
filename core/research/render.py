"""给人读的 Markdown。数据库才是底稿。"""
from __future__ import annotations

import json


def render(view: dict) -> str:
    project = view.get("project") or {}
    thesis = view.get("thesis") or {}
    lines = [
        "# {0}".format(project.get("title") or "研究"),
        "",
        "研究框架，非投资建议。这一页是阅读稿，正式记录在研究库。",
        "",
        "- 问题：{0}".format(project.get("question") or ""),
        "- as_of：{0}".format(thesis.get("as_of") or ""),
        "- Thesis：{0} v{1}".format(thesis.get("id") or "", thesis.get("version") or ""),
        "",
        "## 行业边界",
        "",
        project.get("industry_definition") or "",
        "",
        "## 价值链",
        "",
    ]
    for node in view.get("value_chain") or []:
        lines.append("- {0}（{1}）← {2}".format(
            node.get("node_name") or "",
            node.get("role") or "",
            node.get("upstream_node") or "起点",
        ))
    lines.extend(["", "## Claims", ""])
    for kind in ("FACT", "ESTIMATE", "INFERENCE", "OPINION"):
        rows = (view.get("claims") or {}).get(kind) or []
        if not rows:
            continue
        lines.append("### {0}".format(kind))
        lines.append("")
        for row in rows:
            lines.append("- `{0}` {1} · {2}".format(
                row.get("id") or "",
                row.get("claim_text") or "",
                row.get("status") or "",
            ))
        lines.append("")
    lines.extend(["## 冲突", ""])
    conflicts = view.get("conflicts") or []
    if not conflicts:
        lines.append("无。")
    for row in conflicts:
        lines.append("- {0}：{1}（{2}）与 {3}（{4}）。{5}".format(
            row.get("metric") or "",
            row.get("value_a") or "",
            row.get("definition_a") or "口径未写",
            row.get("value_b") or "",
            row.get("definition_b") or "口径未写",
            row.get("possible_reason") or "",
        ))
    lines.extend(["", "## 公司暴露", "", "| 公司 | 环节 | 暴露 | 收入 | 证据水平 |", "|---|---|---|---|---|"])
    for row in view.get("company_mapping") or []:
        lines.append("| {0} | {1} | {2} | {3} | {4} |".format(
            row.get("company") or "",
            row.get("value_chain_node") or "",
            row.get("exposure_type") or "",
            row.get("revenue_exposure") or "UNKNOWN",
            row.get("evidence_level") or "",
        ))
    lines.extend(["", "## Thesis v{0}".format(thesis.get("version") or ""), "", thesis.get("summary") or ""])
    lines.extend(["", "## 未知", ""])
    for item in view.get("open_questions") or []:
        text = item.get("question") if isinstance(item, dict) else str(item)
        lines.append("- {0}".format(text))
    lines.append("")
    return "\n".join(lines)


def loads(text, default):
    if not text:
        return default
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return default
