"""搜索只返回线索。摘要不是 Claim，也不是 Evidence。"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
import urllib.error
import urllib.request

from core.context.temporal import CN_TZ

HIT_KEYS = ("title", "url", "snippet", "provider", "query", "retrieved_at")


def search(query: str, provider: str = "fixture", *, seed_path: str = "", fixture_hits=None, max_results: int = 8, region: str = "cn-zh") -> dict:
    """SearchProvider。Agent 只调用这个入口，不直接依赖 DDGS。"""
    name = (provider or "fixture").strip().lower()
    if name == "fixture":
        return _ok("fixture", query, list(fixture_hits or []))
    if name == "seeded":
        return _seeded(query, seed_path)
    if name == "ddgs":
        found = _ddgs(query, max_results=max_results, region=region)
        if (not found.get("ok") or not found.get("hits")) and (os.environ.get("TAVILY_API_KEY") or "").strip():
            return _tavily(query, max_results=max_results)
        return found
    if name == "tavily":
        return _tavily(query, max_results=max_results)
    return _fail("SEARCH_PROVIDER_FAILED", "未知搜索提供方：{0}".format(name))


def _seeded(query: str, seed_path: str) -> dict:
    path = Path(seed_path)
    if not path.is_file():
        return _fail("SEARCH_PROVIDER_FAILED", "没有 seed 文件。")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return _fail("SEARCH_PROVIDER_FAILED", str(exc))
    hits = [_hit(row, "seeded", query) for row in data.get("hits") or []]
    return _ok("seeded", query, hits)


def _ddgs(query: str, max_results: int = 8, region: str = "cn-zh") -> dict:
    try:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS
    except ImportError:
        return _fail("SEARCH_PROVIDER_FAILED", "没有安装 DDGS。夹具测试不会因此失败。")
    try:
        try:
            client = DDGS(timeout=12)
        except TypeError:  # Compatibility with the older duckduckgo_search package.
            client = DDGS()
        rows = list(client.text(query, max_results=max_results, region=region))
    except Exception as exc:  # noqa: BLE001
        return _fail("SEARCH_PROVIDER_FAILED", str(exc))
    hits = [
        _hit({
            "title": row.get("title") or "",
            "url": row.get("href") or row.get("url") or "",
            "snippet": row.get("body") or row.get("snippet") or "",
        }, "ddgs", query)
        for row in rows
    ]
    return _ok("ddgs", query, [row for row in hits if row["url"]])


def _tavily(query: str, max_results: int = 8) -> dict:
    token = (os.environ.get("TAVILY_API_KEY") or "").strip()
    if not token:
        return {
            "ok": False,
            "error_code": "PROVIDER_UNAVAILABLE",
            "message": "没有 TAVILY_API_KEY。搜索提供方不可用。",
            "hits": [],
        }
    payload = json.dumps({
        "api_key": token,
        "query": query,
        "search_depth": "basic",
        "max_results": min(max(int(max_results), 1), 10),
        "include_answer": False,
        "include_raw_content": False,
    }).encode("utf-8")
    request = urllib.request.Request(
        "https://api.tavily.com/search", data=payload,
        headers={"Content-Type": "application/json", "User-Agent": "stock-assistant/1.0"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            body = json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError, TypeError, urllib.error.URLError) as exc:
        return _fail("SEARCH_PROVIDER_FAILED", "Tavily 请求失败：{0}".format(type(exc).__name__))
    rows = body.get("results") if isinstance(body, dict) else []
    hits = [
        _hit({
            "title": row.get("title") or "",
            "url": row.get("url") or "",
            "snippet": row.get("content") or "",
        }, "tavily", query)
        for row in (rows or []) if isinstance(row, dict) and row.get("url")
    ]
    return _ok("tavily", query, hits)


def _hit(row: dict, provider: str, query: str) -> dict:
    return {
        "title": row.get("title") or "",
        "url": row.get("url") or "",
        "snippet": row.get("snippet") or "",
        "provider": provider,
        "query": row.get("query") or query,
        "retrieved_at": row.get("retrieved_at") or datetime.now(CN_TZ).isoformat(timespec="seconds"),
    }


def _ok(provider: str, query: str, hits: list) -> dict:
    clean = [_hit(row, provider, query) for row in hits]
    return {"ok": True, "provider": provider, "query": query, "hits": clean, "error_code": ""}


def _fail(code: str, message: str) -> dict:
    return {"ok": False, "error_code": code, "message": message, "hits": []}
