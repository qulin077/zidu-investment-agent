"""Tool 返回的来源形状。只有 URL 不够。"""
from __future__ import annotations

TOOL_RESULT_KEYS = (
    "source_id",
    "title",
    "publisher",
    "url",
    "source_type",
    "published_at",
    "available_at",
    "captured_at",
    "content",
    "content_type",
)


def to_tool_result(row: dict) -> dict:
    return {
        "source_id": row.get("source_id") or row.get("local_id") or "",
        "title": row.get("title") or "",
        "publisher": row.get("publisher") or "",
        "url": row.get("url") or "",
        "source_type": row.get("source_type") or "",
        "published_at": row.get("published_at") or "",
        "available_at": row.get("available_at") or "",
        "captured_at": row.get("captured_at") or "",
        "content": row.get("content") if row.get("content") is not None else (row.get("body") or ""),
        "content_type": row.get("content_type") or "html",
    }
