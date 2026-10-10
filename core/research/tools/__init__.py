"""研究 Tool。没有接上的外部源就停，不用模型记忆填空。"""
from __future__ import annotations

from pathlib import Path

from core.config import ROOT
from core.research.tools.contract import to_tool_result
from core.research.tools.fixture_search import FixtureSearchTool
from core.research.tools.protocol import WebSearchTool

_SKIP = {".git", "node_modules", ".next", "web", "__pycache__"}


def search_repo(query: str, limit: int = 8) -> list:
    needles = [part for part in (query or "").replace("，", " ").split() if len(part) >= 2]
    if not needles:
        return []
    hits = []
    for path in ROOT.rglob("*.md"):
        if any(part in _SKIP for part in path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if not any(token in text for token in needles):
            continue
        hits.append({
            "path": str(path.relative_to(ROOT)),
            "excerpt": text[:1500],
        })
        if len(hits) >= limit:
            break
    return hits


def search_local_research(query: str, limit: int = 8) -> list:
    return search_repo(query, limit)


def read_research_note(path: str) -> dict:
    target = Path(path)
    if not target.is_absolute():
        target = ROOT / path
    if not target.is_file():
        return {"ok": False, "error_code": "SOURCE_READ_FAILED", "message": "笔记不存在：{0}".format(path)}
    try:
        text = target.read_text(encoding="utf-8")
    except OSError as exc:
        return {"ok": False, "error_code": "SOURCE_READ_FAILED", "message": str(exc)}
    return {
        "ok": True,
        "path": str(target.relative_to(ROOT)) if target.is_relative_to(ROOT) else str(target),
        "body": text,
    }


def search_web(_query: str) -> dict:
    return {
        "ok": False,
        "abstain": True,
        "error_code": "SEARCH_FAILED",
        "message": "未接搜索引擎。不能用模型记忆充当最新事实。",
    }


def open_webpage(_url: str) -> dict:
    return {
        "ok": False,
        "abstain": True,
        "error_code": "SOURCE_READ_FAILED",
        "message": "未接网页读取。",
    }


def read_webpage(url: str) -> dict:
    return open_webpage(url)


def read_pdf(path: str) -> dict:
    from core.research.tools.reader import read_pdf as _read
    return _read(path)


def read_company_filing(code: str) -> dict:
    return {
        "ok": False,
        "abstain": True,
        "error_code": "SOURCE_READ_FAILED",
        "message": "{0} 的公告原文这轮没有打开。".format(code or "公司"),
    }


def get_market_data(code: str = "", store=None) -> dict:
    if not code or store is None:
        return {"ok": False, "abstain": True, "error_code": "SOURCE_UNAVAILABLE", "message": "没有指定代码，不报价。"}
    rows = store.query(
        """SELECT date, open, high, low, close, volume, pct_chg
           FROM quote_daily WHERE code = ? ORDER BY date DESC LIMIT 260""",
        (code,),
    )
    if not rows:
        return {"ok": False, "abstain": True, "error_code": "SOURCE_UNAVAILABLE", "message": "库里没有 {0} 的行情。".format(code)}
    latest = dict(rows[0])
    history = list(reversed(rows))
    from core.market_data.technical import technical_snapshot
    return {
        "ok": True,
        "row": latest,
        "technical": technical_snapshot(history),
        "history_count": len(history),
        "source": "本地行情库（iFinD 实时优先，新浪/腾讯/东方财富自动降级）",
    }


__all__ = [
    "FixtureSearchTool",
    "WebSearchTool",
    "get_market_data",
    "open_webpage",
    "read_company_filing",
    "read_pdf",
    "read_research_note",
    "read_webpage",
    "search_local_research",
    "search_repo",
    "search_web",
    "to_tool_result",
]
