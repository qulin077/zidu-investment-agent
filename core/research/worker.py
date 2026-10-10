"""本地单用户后台。不上 Celery、Redis 或 Temporal。"""
from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

from core.research import workspace
from core.store import STORE

_POOL = None
_LOCK = threading.Lock()


def executor() -> ThreadPoolExecutor:
    global _POOL
    with _LOCK:
        if _POOL is None:
            _POOL = ThreadPoolExecutor(max_workers=1, thread_name_prefix="research-run")
        return _POOL


def submit(session_id: str, run_id: str, **kwargs):
    return executor().submit(_run, session_id, run_id, kwargs)


def _run(session_id: str, run_id: str, kwargs=None) -> None:
    try:
        workspace.execute(STORE, session_id, run_id, use_llm=True, **dict(kwargs or {}))
    except Exception:
        workspace.sessions.mark_interrupted(STORE, session_id, run_id, "worker")
