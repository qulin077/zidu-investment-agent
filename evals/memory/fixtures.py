"""Memory Eval 夹具：把 Guided fixture 推到 REVIEWED 并摄入 Memory。"""
from __future__ import annotations

from core.review.guided import service as guided
from core.store import Store
from evals.review.fixtures import build


def reviewed(kind: str, store: Store, primary: str, lesson: str = "",
             thesis_extra: str = "", market: str = "") -> str:
    did = build(kind, store)
    if thesis_extra or market:
        from core.review import repo

        if thesis_extra:
            repo.amend("decision", did, "thesis", thesis_extra, "eval 注入自述", "eval", store=store)
        if market:
            repo.amend("decision", did, "market_context", market, "eval context", "eval", store=store)
    guided.confirm_outcome(did, store=store)
    guided.confirm_violations(did, store=store)
    guided.confirm_attribution(did, primary, store=store)
    guided.complete(did, lesson=lesson, store=store)
    return did
