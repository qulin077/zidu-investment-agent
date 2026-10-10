"""Small deterministic conversation compactor for turns outside the hot window."""
from __future__ import annotations

from core.store import Store


def compact(store: Store, session_id: str, previous: dict | None = None, keep_recent: int = 12) -> dict:
    rows = store.query(
        """SELECT id, role, content, created_at FROM agent_message
           WHERE session_id = ? ORDER BY created_at DESC, id DESC LIMIT 80""",
        (session_id,),
    )
    rows = list(reversed(rows))
    if len(rows) <= keep_recent:
        return dict(previous or {})
    older = rows[:-keep_recent]
    previous = dict(previous or {})
    through = previous.get("through_message_id") or ""
    pending = [row for row in older if not through or (row.get("id") or "") > through]
    if not pending:
        return previous
    lines = [previous.get("digest") or ""]
    for row in pending:
        content = " ".join((row.get("content") or "").split())
        if not content:
            continue
        label = "用户" if row.get("role") == "user" else "助手"
        lines.append("{0}：{1}".format(label, content[:240]))
    compacted_lines = [line for line in lines if line]
    while len("\n".join(compacted_lines)) > 2400 and len(compacted_lines) > 1:
        compacted_lines.pop(0)
    digest = "\n".join(compacted_lines).strip()
    if len(digest) > 2400:
        digest = digest[:2400]
    return {
        "through_message_id": older[-1].get("id") or "",
        "digest": digest,
        "compacted_messages": int(previous.get("compacted_messages") or 0) + len(pending),
    }
