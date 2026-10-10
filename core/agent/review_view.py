"""复盘时并列两个 Thesis 版本。研究错误只由用户确认。"""
from __future__ import annotations

_CHANGES = {"STRENGTHENED", "WEAKENED", "INVALIDATED", "UNCHANGED"}
_QUESTION = "研究逻辑后来发生了变化。你认为这次主要是 Research Error，还是原研究仍成立、只是短期预期错了？"


def format_review(snapshot: dict) -> str:
    if not snapshot or not snapshot.get("attached"):
        return "还没有挂上 Decision-time Thesis。要复盘哪一笔？研究错误不会自动写入。"
    current = int(snapshot.get("current_version") or 0)
    previous = int(snapshot.get("decision_version") or 0)
    verdict = snapshot.get("diff_verdict") or ""
    if verdict not in _CHANGES:
        verdict = "UNCHANGED" if current == previous else (verdict or "UNCHANGED")
    return "\n".join([
        "Decision Time: Thesis v{0}".format(previous),
        "Current: Thesis v{0}".format(current),
        "Changes: {0}".format(verdict),
        _QUESTION,
        "需要你确认。系统不会自动写成 Research Error。",
    ])
