"""公司实体从本地索引、代码和官方检索来，不靠股票池放行。"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import yaml

from core.config import ROOT

_HEAD = re.compile(r"^#\s*(.+?)[（(](\d{6}|[A-Z]{1,5})[）)]")
_FILE = re.compile(r"^(\d{6})_(.+)\.md$")
_TICKER = re.compile(r"(?<!\d)(\d{6})(?!\d)")
_COMPARE = re.compile(r"(?:和|跟|与)(.{2,16}?)(?:比呢|相比|对比|比较|比一比|比)")
_CODE_IN_TITLE = re.compile(r"[（(](\d{6})[）)]|(\d{6})")


def comparison_target(text: str) -> str:
    match = _COMPARE.search(text or "")
    if not match:
        return ""
    return match.group(1).strip(" ，,。")


def exchange_for(code: str) -> str:
    raw = (code or "").upper()
    if raw.startswith(("60", "68", "90")):
        return "SSE"
    if raw.startswith(("00", "30", "20")):
        return "SZSE"
    if raw == "NVDA":
        return "NASDAQ"
    if raw.isalpha():
        return "US"
    return ""


@lru_cache(maxsize=1)
def _index() -> tuple:
    rows = {}
    roots = [ROOT / "02-公司基本面", ROOT / "11-节奏看板"]
    for base in roots:
        if not base.is_dir():
            continue
        for path in base.rglob("*.md"):
            if path.stat().st_size > 500_000:
                continue
            name = ""
            code = ""
            file_match = _FILE.match(path.name)
            if file_match:
                code = file_match.group(1)
                name = file_match.group(2).strip()
            else:
                handle = None
                try:
                    handle = path.open(encoding="utf-8")
                    first = handle.readline().strip()
                except OSError:
                    continue
                finally:
                    if handle is not None:
                        handle.close()
                head = _HEAD.match(first)
                if not head:
                    continue
                name = head.group(1).strip()
                code = head.group(2).strip()
            if not name or not code:
                continue
            current = rows.get(code)
            if current is None or _prefer(path, Path(current[2])):
                rows[code] = (name, code, str(path))
    return tuple(rows.values())


def _prefer(path: Path, other: Path) -> bool:
    named = bool(_FILE.match(path.name))
    other_named = bool(_FILE.match(other.name))
    if named != other_named:
        return named
    return path.stat().st_size > other.stat().st_size


def names_in(text: str) -> list:
    raw = text or ""
    found = []
    used = []
    for name, code, _path in sorted(_index(), key=lambda row: len(row[0]), reverse=True):
        if len(name) < 2 or name not in raw:
            continue
        if any(name in longer for longer in used):
            continue
        found.append({"name": name, "code": code})
        used.append(name)
    return found


@lru_cache(maxsize=1)
def _universe() -> tuple:
    path = ROOT / "config" / "universe.yaml"
    if not path.is_file():
        return tuple(), tuple()
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    names = []
    codes = []
    for row in data.get("stocks") or []:
        if row.get("name"):
            names.append(str(row["name"]))
        if row.get("code"):
            codes.append(str(row["code"]))
    return tuple(names), tuple(codes)


@lru_cache(maxsize=1)
def _chains() -> tuple:
    path = ROOT / "config" / "chains.yaml"
    if not path.is_file():
        return tuple()
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    rows = []
    for chain_id, spec in (data.get("chains") or {}).items():
        for member in spec.get("members") or []:
            code = str(member.get("code") or "")
            if code:
                rows.append((code, chain_id, spec.get("name") or chain_id, member.get("layer") or ""))
    return tuple(rows)


def chain_context(code: str) -> list:
    return [
        {"chain": chain_id, "chain_name": chain_name, "layer": layer}
        for member, chain_id, chain_name, layer in _chains()
        if member == code
    ]


def resolve(question: str, *, universe_names=None, search_hits=None, llm=None) -> dict:
    text = (question or "").strip()
    names, codes = _universe()
    allowed_names = set(universe_names) if universe_names is not None else set(names)
    allowed_codes = set() if universe_names is not None else set(codes)
    matches = names_in(text)
    if len(matches) >= 2 and not comparison_target(text):
        return _clarify(matches)
    if len(matches) == 1:
        return _from_index(matches[0]["code"], allowed_names, allowed_codes)
    target = comparison_target(text)
    if target:
        targeted = [row for row in names_in(target) if row["name"] in target or target in row["name"]]
        if len(targeted) == 1:
            return _from_index(targeted[0]["code"], allowed_names, allowed_codes)
        if len(targeted) >= 2:
            return _clarify(targeted)
    for code in _TICKER.findall(text):
        row = _by_code(code)
        if row:
            return _from_index(code, allowed_names, allowed_codes)
    official = _from_official_hits(text, search_hits or [])
    if official:
        return _pack(official, allowed_names, allowed_codes, verified_source=official.get("url") or "")
    parsed = _parse_name(text, llm)
    return {
        "ok": False,
        "status": "NOT_FOUND",
        "canonical_name": parsed,
        "ticker": "",
        "exchange": "",
        "aliases": [],
        "verified_source": "",
        "verified_at": "",
        "universe_status": "NOT_IN_UNIVERSE",
        "path": "",
        "candidates": [],
        "chains": [],
    }


def _from_index(code: str, names: set, codes: set) -> dict:
    row = _by_code(code)
    if row is None:
        return {
            "ok": False,
            "status": "NOT_FOUND",
            "canonical_name": "",
            "ticker": code,
            "exchange": exchange_for(code),
            "aliases": [],
            "verified_source": "",
            "verified_at": "",
            "universe_status": "NOT_IN_UNIVERSE",
            "path": "",
            "candidates": [],
            "chains": chain_context(code),
        }
    name, ticker, path = row
    return _pack(
        {"name": name, "code": ticker, "path": path, "url": ""},
        names,
        codes,
        verified_source=str(Path(path).relative_to(ROOT)) if Path(path).is_relative_to(ROOT) else path,
    )


def _pack(row: dict, names: set, codes: set, verified_source: str) -> dict:
    name = row.get("name") or ""
    code = row.get("code") or ""
    status = "IN_UNIVERSE" if name in names or code in codes else "NOT_IN_UNIVERSE"
    return {
        "ok": True,
        "status": "RESOLVED",
        "canonical_name": name,
        "ticker": code,
        "exchange": exchange_for(code),
        "aliases": [item for item in (name, code) if item],
        "verified_source": verified_source,
        "verified_at": "",
        "universe_status": status,
        "path": row.get("path") or "",
        "candidates": [],
        "chains": chain_context(code),
    }


def _by_code(code: str):
    for name, ticker, path in _index():
        if ticker == code:
            return name, ticker, path
    return None


def _clarify(matches: list) -> dict:
    return {
        "ok": False,
        "status": "NEEDS_CLARIFICATION",
        "canonical_name": "",
        "ticker": "",
        "exchange": "",
        "aliases": [],
        "verified_source": "",
        "verified_at": "",
        "universe_status": "NOT_IN_UNIVERSE",
        "path": "",
        "candidates": matches,
        "chains": [],
    }


def _from_official_hits(text: str, hits: list):
    name = ""
    for row in names_in(text):
        name = row["name"]
        break
    if not name:
        name = _loose_name(text)
    if not name:
        return None
    codes = []
    chosen = None
    for hit in hits:
        url = hit.get("url") or ""
        blob = "{0} {1}".format(hit.get("title") or "", hit.get("snippet") or "")
        if "cninfo.com.cn" not in url and "sse.com.cn" not in url and "szse.cn" not in url:
            continue
        if name not in blob and name not in url:
            continue
        found = [item for item in _CODE_IN_TITLE.findall(blob) for item in item if item]
        if len(set(found)) == 1:
            codes.append(found[0])
            chosen = {"name": name, "code": found[0], "path": "", "url": url}
    if len(set(codes)) != 1 or chosen is None:
        return None
    return chosen


def _loose_name(text: str) -> str:
    cleaned = re.sub(r"(怎么样|怎么看|如何|算吗|吗|呢|？|\?)", " ", text or "")
    cleaned = re.sub(r"\s+", "", cleaned).strip()
    if 2 <= len(cleaned) <= 12:
        return cleaned
    return ""


def resolve_with_network(question: str, *, network: str = "replay", search=None, llm=None, store=None, universe_names=None) -> dict:
    """本地没有这家公司时，联网检索官方页面，再写入实体缓存。"""
    from core.research.entity_cache import lookup, remember

    found = resolve(question, universe_names=universe_names, search_hits=[], llm=None)
    if found.get("status") == "RESOLVED":
        remember(store, found)
        return found
    cached = lookup(store, question) or lookup(store, _loose_name(question))
    if cached.get("status") == "RESOLVED":
        return cached
    if network == "live":
        name = found.get("canonical_name") or _loose_name(question) or (question or "")
        hits = []
        for query in (
            "{0} 股票代码".format(name),
            "site:cninfo.com.cn {0}".format(name),
            "site:szse.cn {0}".format(name),
        ):
            try:
                if search is not None:
                    result = search(query, max_results=8, region="cn-zh")
                else:
                    from core.research.tools import providers
                    result = providers.search(query, "ddgs", max_results=8, region="cn-zh")
            except Exception:
                result = None
            if result and result.get("ok"):
                hits.extend(result.get("hits") or [])
        found = resolve(question, universe_names=universe_names, search_hits=hits, llm=llm)
        if found.get("status") == "RESOLVED":
            remember(store, found)
            return found
    loose = _loose_name(question)
    if found.get("status") != "RESOLVED" and loose:
        found = dict(found)
        found["canonical_name"] = found.get("canonical_name") or loose
        found["status"] = "UNVERIFIED"
        found["ok"] = False
    return found


def _parse_name(text: str, llm) -> str:
    """模型只解析名字。没有官方来源就不算已核实。"""
    if llm is None:
        return ""
    try:
        raw = llm.generate_structured(
            "只输出 JSON：name。不要给代码，不要回答问题。",
            text,
            {"type": "object"},
            temperature=0,
        )
    except Exception:  # noqa: BLE001
        return ""
    import json
    try:
        data = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return ""
    return str(data.get("name") or "")
