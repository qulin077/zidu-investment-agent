"""文件/远端数据进入 SQLite 的可追溯清单。"""
from __future__ import annotations

import hashlib
from pathlib import Path

from core.research.store import _ids, now_iso
from core.store import Store


def record(
    store: Store,
    *,
    dataset: str,
    source_uri: str,
    source_kind: str = "FILE",
    as_of: str = "",
    target_table: str = "",
    rows_written: int = 0,
    status: str = "INGESTED",
    message: str = "",
) -> dict:
    stamp = now_iso()
    digest = content_hash(source_uri) if source_kind in ("FILE", "DIRECTORY") else ""
    existing = store.query(
        """SELECT * FROM ingest_manifest
           WHERE dataset = ? AND source_uri = ? AND content_hash = ? AND ingested_at = ?""",
        (dataset, source_uri, digest, stamp),
    )
    if existing:
        return dict(existing[0])
    with store.connect() as conn:
        manifest_id = _ids(conn, "ingest_manifest", "IM", 1)[0]
        conn.execute(
            """INSERT INTO ingest_manifest
               (id, dataset, source_uri, source_kind, content_hash, as_of,
                ingested_at, target_table, rows_written, status, message)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                manifest_id, dataset, source_uri, source_kind, digest, as_of,
                stamp, target_table, int(rows_written), status, message,
            ),
        )
    return dict(store.query("SELECT * FROM ingest_manifest WHERE id = ?", (manifest_id,))[0])


def content_hash(source_uri: str) -> str:
    path = Path(source_uri)
    if not path.exists():
        return ""
    hasher = hashlib.sha256()
    if path.is_file():
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                hasher.update(chunk)
        return hasher.hexdigest()
    for item in sorted(row for row in path.rglob("*") if row.is_file()):
        stat = item.stat()
        hasher.update(str(item.relative_to(path)).encode("utf-8"))
        hasher.update(str(stat.st_size).encode("ascii"))
        hasher.update(str(stat.st_mtime_ns).encode("ascii"))
    return hasher.hexdigest()


def latest(store: Store, dataset: str) -> list:
    return store.query(
        "SELECT * FROM ingest_manifest WHERE dataset = ? ORDER BY ingested_at DESC LIMIT 20",
        (dataset,),
    )
