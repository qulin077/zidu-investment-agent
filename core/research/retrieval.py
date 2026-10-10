"""长文用 FTS5 按章节找。这轮不做向量检索。"""
from __future__ import annotations

from core.research.store import _ids
from core.store import Store


def index_chunks(store: Store, source_id: str, chunks: list) -> list:
    ids = []
    with store.connect() as conn:
        row_ids = _ids(conn, "research_source_chunk", "CH", len(chunks))
        for index, chunk in enumerate(chunks):
            chunk_id = row_ids[index]
            ids.append(chunk_id)
            conn.execute(
                """INSERT INTO research_source_chunk
                   (id, source_id, section, page_start, page_end, ordinal, text)
                   VALUES (?,?,?,?,?,?,?)""",
                (
                    chunk_id, source_id, chunk.get("section") or "",
                    chunk.get("page_start"), chunk.get("page_end"),
                    int(chunk.get("ordinal") or index), chunk.get("text") or "",
                ),
            )
            conn.execute(
                "INSERT INTO research_source_fts (source_id, section, body) VALUES (?,?,?)",
                (source_id, chunk.get("section") or "", chunk.get("text") or ""),
            )
    return ids


def search_chunks(store: Store, query: str, limit: int = 5) -> list:
    phrase = '"{0}"'.format((query or "").replace('"', " "))
    try:
        return store.query(
            """SELECT source_id, section, bm25(research_source_fts) AS rank
               FROM research_source_fts
               WHERE research_source_fts MATCH ?
               ORDER BY rank
               LIMIT ?""",
            (phrase, limit),
        )
    except Exception:  # noqa: BLE001
        return []
