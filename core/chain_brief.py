"""持仓语境产业链简报。

市面上的「相关股」和飞书新闻机器人缺三件事：链条是你自己画的、
资金落在哪一层、这件事改不改你现在的账本。本模块把这三件事算出来，
供 API、看板和 Cursor skill 共用。不做买入建议。
"""
from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import yaml

from core.config import CONFIG_DIR, RAW_DIR, ROOT
from core.store import STORE, Store
from core.symbols import normalize_code, universe_index

CHAINS_YAML = CONFIG_DIR / "chains.yaml"
_ZONE_RE = re.compile(r"(低估|合理|高估)")
_EARNING_RE = re.compile(r"E[0-7]")


def load_chain_defs(path: Path = CHAINS_YAML) -> Dict[str, Any]:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data.get("chains") or {}


def list_chain_meta(path: Path = CHAINS_YAML) -> List[Dict[str, Any]]:
    out = []
    for cid, spec in load_chain_defs(path).items():
        out.append(
            {
                "id": cid,
                "name": spec.get("name") or cid,
                "thesis": spec.get("thesis") or "",
                "aliases": list(spec.get("aliases") or []),
                "layers": [layer["id"] for layer in spec.get("layers") or []],
                "n_members": len(spec.get("members") or []),
            }
        )
    return out


def _mean(values: Sequence[float]) -> Optional[float]:
    if not values:
        return None
    return round(sum(values) / len(values), 2)


def _latest_quote_day(store: Store) -> str:
    return store.max_date("quote_daily") or ""


def _positions(store: Store) -> Dict[str, Any]:
    """持仓查询放在 core，避免 chain_brief 依赖 app.api。"""
    from core.calendar import age_days

    snapshot_day = store.max_date("position_snapshot") or ""
    if not snapshot_day:
        return {"asof": "", "stale_days": None, "rows": []}
    quote_day = _latest_quote_day(store)
    rows = store.query(
        """
        SELECT p.code, p.name, p.qty, p.cost,
               q.close AS current_price, q.date AS quote_date
        FROM position_snapshot p
        LEFT JOIN quote_daily q ON q.code = p.code AND q.date = ?
        WHERE p.date = ? AND p.qty > 0
        """,
        (quote_day, snapshot_day),
    )
    for row in rows:
        price = row.get("current_price")
        cost = row.get("cost")
        row["current_pnl_pct"] = (
            round((price - cost) / cost * 100, 2) if price and cost else None
        )
    return {
        "asof": snapshot_day,
        "quote_date": quote_day,
        "stale_days": age_days(snapshot_day),
        "rows": rows,
    }


def _us_last(symbol: str) -> Optional[Dict[str, Any]]:
    path = RAW_DIR / "quotes_us" / "{0}.csv".format(symbol)
    if not path.exists():
        return None
    rows: List[Dict[str, str]] = []
    with path.open("r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            rows.append({(k or "").lstrip("\ufeff"): v for k, v in row.items()})
    if len(rows) < 2:
        return None
    prev = rows[-2]
    last = rows[-1]
    try:
        close = float(last.get("收盘") or last.get("close") or 0)
        prev_close = float(prev.get("收盘") or prev.get("close") or 0)
    except (TypeError, ValueError):
        return None
    pct = round((close / prev_close - 1) * 100, 2) if prev_close else None
    return {
        "symbol": symbol,
        "date": last.get("日期") or last.get("date") or "",
        "close": close,
        "pct_chg": pct,
    }


def _quotes_on(day: str, codes: Sequence[str], store: Store) -> Dict[str, Dict[str, Any]]:
    if not codes or not day:
        return {}
    placeholders = ",".join("?" for _ in codes)
    rows = store.query(
        "SELECT code, close, volume, pct_chg FROM quote_daily WHERE date = ? AND code IN ({0})".format(
            placeholders
        ),
        (day, *codes),
    )
    return {row["code"]: row for row in rows}


def _closes(code: str, limit: int, store: Store) -> List[float]:
    rows = store.query(
        "SELECT close FROM quote_daily WHERE code = ? AND close IS NOT NULL ORDER BY date DESC LIMIT ?",
        (code, limit),
    )
    return [float(row["close"]) for row in rows]


def _ma5_state(code: str, store: Store) -> Dict[str, Any]:
    closes = _closes(code, 5, store)
    if len(closes) < 5:
        return {"ma5": None, "vs_ma5": "数据不足", "above": None}
    ma5 = round(sum(closes) / 5, 3)
    last = closes[0]
    above = last >= ma5
    return {
        "ma5": ma5,
        "close": last,
        "above": above,
        "vs_ma5": "站上 MA5" if above else "跌破 MA5",
    }


def _find_note(name: str) -> Optional[str]:
    base = ROOT / "02-公司基本面"
    if not name or not base.is_dir():
        return None
    for path in base.rglob("笔记.md"):
        if name in path.parts:
            return str(path.relative_to(ROOT))
    return None


def _scan_note(rel: Optional[str]) -> Dict[str, str]:
    zone, earning = "未评", "未填"
    if not rel:
        return {"valuation_zone": zone, "earning_type": earning, "note": ""}
    path = ROOT / rel
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {"valuation_zone": zone, "earning_type": earning, "note": rel}
    found_zone = _ZONE_RE.findall(text)
    found_e = _EARNING_RE.findall(text)
    if found_zone:
        # 笔记里最后一次出现的三区更接近当前判断
        zone = found_zone[-1]
    if found_e:
        earning = found_e[0]
    return {"valuation_zone": zone, "earning_type": earning, "note": rel}


def _layer_stats(
    members: List[Dict[str, Any]],
    quotes: Dict[str, Dict[str, Any]],
    index: Dict[str, Any],
    held: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    by_layer: Dict[str, List[Dict[str, Any]]] = {}
    for member in members:
        layer = member["layer"]
        code = normalize_code(member["code"])
        inst = index.get(code)
        q = quotes.get(code) or {}
        row = {
            "code": code,
            "name": inst.name if inst else code,
            "role": inst.role if inst else "",
            "priority": inst.priority if inst else 99,
            "close": q.get("close"),
            "pct_chg": round(q["pct_chg"], 2) if q.get("pct_chg") is not None else None,
            "volume": q.get("volume"),
            "in_book": code in held,
        }
        by_layer.setdefault(layer, []).append(row)

    layers = []
    for layer_id, rows in by_layer.items():
        pcts = [r["pct_chg"] for r in rows if r["pct_chg"] is not None]
        up = sum(1 for p in pcts if p > 0)
        turnover = 0.0
        for row in rows:
            if row.get("close") and row.get("volume"):
                turnover += float(row["close"]) * float(row["volume"])
        rows.sort(key=lambda item: (item["pct_chg"] is None, -(item["pct_chg"] or 0)))
        layers.append(
            {
                "id": layer_id,
                "members": rows,
                "avg_pct": _mean(pcts),
                "breadth": round(up / len(pcts), 2) if pcts else None,
                "quoted": len(pcts),
                "turnover_proxy": round(turnover, 0),
                "held": sum(1 for r in rows if r["in_book"]),
            }
        )
    return layers


def _annotate_layers(spec: Dict[str, Any], stats: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    meta = {layer["id"]: layer for layer in spec.get("layers") or []}
    out = []
    for item in stats:
        info = meta.get(item["id"]) or {}
        merged = dict(item)
        merged["name"] = info.get("name") or item["id"]
        merged["side"] = info.get("side") or ""
        merged["logic"] = info.get("logic") or ""
        out.append(merged)
    order = [layer["id"] for layer in spec.get("layers") or []]
    out.sort(key=lambda row: order.index(row["id"]) if row["id"] in order else 99)
    return out


def _pick_money(layers: List[Dict[str, Any]]) -> Dict[str, Any]:
    scored = [row for row in layers if row.get("avg_pct") is not None and row.get("quoted", 0) > 0]
    if not scored:
        return {"layer": "", "name": "", "avg_pct": None, "why": "当日无行情"}
    leader = max(scored, key=lambda row: (row["avg_pct"], row.get("turnover_proxy") or 0))
    laggard = min(scored, key=lambda row: row["avg_pct"])
    why = "当日涨跌幅最高的层级是{0}（{1:+.2f}%），成交额代理亦用于同分打破。这是池内相对强弱，不是北向/主力资金真值。".format(
        leader["name"], leader["avg_pct"]
    )
    return {
        "layer": leader["id"],
        "name": leader["name"],
        "avg_pct": leader["avg_pct"],
        "laggard": laggard["name"],
        "laggard_pct": laggard["avg_pct"],
        "why": why,
    }


def _book_overlay(
    chain_codes: Sequence[str],
    positions: List[Dict[str, Any]],
    index: Dict[str, Any],
) -> Dict[str, Any]:
    chain_set = set(chain_codes)
    in_chain, in_universe, orphans = [], [], []
    for pos in positions:
        code = normalize_code(pos.get("code"))
        item = {
            "code": code,
            "name": pos.get("name") or (index[code].name if code in index else code),
            "qty": pos.get("qty"),
            "cost": pos.get("cost"),
            "current_price": pos.get("current_price"),
            "current_pnl_pct": pos.get("current_pnl_pct"),
        }
        if code in chain_set:
            in_chain.append(item)
        elif code in index:
            in_universe.append(item)
        else:
            orphans.append(item)
    if in_chain:
        verdict = "链条今天会打到你的持仓层"
    elif in_universe:
        verdict = "你有持仓，但不在这条链上——今天这条链的涨跌不自动等于你的盈亏"
    else:
        verdict = "账本与这条链没有交集；问答只允许观察，不允许把链条涨跌说成你的机会"
    return {
        "in_chain": in_chain,
        "in_universe_other_chain": in_universe,
        "orphans": orphans,
        "verdict": verdict,
        "stale_warning": True,
    }


def _related_news(keywords: Sequence[str], store: Store, limit: int = 8) -> List[Dict[str, Any]]:
    if not keywords:
        return []
    rows = store.query(
        "SELECT title, source, published_at, url FROM news_item ORDER BY published_at DESC LIMIT 80"
    )
    hits = []
    for row in rows:
        title = row.get("title") or ""
        matched = [kw for kw in keywords if kw and kw.lower() in title.lower()]
        if matched:
            hits.append({**row, "matched": matched})
        if len(hits) >= limit:
            break
    return hits


def brief(chain_id: str, store: Store = STORE, path: Path = CHAINS_YAML) -> Dict[str, Any]:
    specs = load_chain_defs(path)
    spec = specs.get(chain_id)
    if spec is None:
        raise KeyError("未知产业链：{0}".format(chain_id))

    day = _latest_quote_day(store)
    prev_rows = store.query(
        "SELECT DISTINCT date FROM quote_daily WHERE date < ? ORDER BY date DESC LIMIT 1",
        (day,),
    )
    prev_day = prev_rows[0]["date"] if prev_rows else ""
    members = spec.get("members") or []
    codes = [normalize_code(m["code"]) for m in members]
    quotes = _quotes_on(day, codes, store)
    prev_quotes = _quotes_on(prev_day, codes, store) if prev_day else {}
    index = universe_index()
    pos_payload = _positions(store)
    held = {normalize_code(r["code"]): r for r in pos_payload.get("rows") or []}

    layers = _annotate_layers(spec, _layer_stats(members, quotes, index, held))
    prev_layers = _annotate_layers(spec, _layer_stats(members, prev_quotes, index, held)) if prev_day else []
    money = _pick_money(layers)
    prev_money = _pick_money(prev_layers) if prev_layers else {}
    switched = bool(
        money.get("layer")
        and prev_money.get("layer")
        and money["layer"] != prev_money["layer"]
    )

    overseas = []
    for item in spec.get("overseas") or []:
        last = _us_last(item["symbol"])
        if last:
            last["name"] = item.get("name") or item["symbol"]
            last["layer"] = item.get("layer") or "demand"
            overseas.append(last)

    book = _book_overlay(codes, pos_payload.get("rows") or [], index)
    book["asof"] = pos_payload.get("asof") or ""
    book["stale_days"] = pos_payload.get("stale_days")
    book["stale_warning"] = bool(pos_payload.get("stale_days") and pos_payload["stale_days"] > 7)

    return {
        "id": chain_id,
        "name": spec.get("name") or chain_id,
        "thesis": spec.get("thesis") or "",
        "note": spec.get("note") or "",
        "asof": day,
        "prev_asof": prev_day,
        "layers": layers,
        "overseas": overseas,
        "money": money,
        "prev_money": prev_money,
        "switched": switched,
        "book": book,
        "news": _related_news(spec.get("news_keywords") or spec.get("aliases") or [], store),
        "disclaimer": "研究框架，非投资建议。资金位置是池内层级相对强弱，不是交易所资金流向。",
    }


def company_card(code_or_name: str, store: Store = STORE, path: Path = CHAINS_YAML) -> Dict[str, Any]:
    index = universe_index()
    target = None
    raw = (code_or_name or "").strip()
    norm = normalize_code(raw)
    if norm in index:
        target = index[norm]
    else:
        for inst in index.values():
            if inst.name == raw or inst.name in raw or raw in inst.name:
                target = inst
                break
    if target is None:
        return {
            "found": False,
            "query": raw,
            "refuse": "不在你的股票池里。禁止用全市场相关股凑答案；要先写入 universe.yaml 和某条产业链。",
        }

    specs = load_chain_defs(path)
    homes = []
    for cid, spec in specs.items():
        for member in spec.get("members") or []:
            if normalize_code(member["code"]) == target.code:
                homes.append({"chain": cid, "name": spec.get("name"), "layer": member["layer"]})
    note = _find_note(target.name)
    scanned = _scan_note(note)
    ma5 = _ma5_state(target.code, store)
    day = _latest_quote_day(store)
    q = _quotes_on(day, [target.code], store).get(target.code) or {}
    held = {normalize_code(r["code"]): r for r in (_positions(store).get("rows") or [])}
    pos = held.get(target.code)
    missing = []
    if scanned["valuation_zone"] == "未评":
        missing.append("估值三区")
    if scanned["earning_type"] == "未填":
        missing.append("赚钱类型")
    if not homes:
        missing.append("产业链归属")
    return {
        "found": True,
        "code": target.code,
        "name": target.name,
        "sector": target.sector,
        "role": target.role,
        "asof": day,
        "close": q.get("close"),
        "pct_chg": round(q["pct_chg"], 2) if q.get("pct_chg") is not None else None,
        "ma5": ma5,
        "valuation_zone": scanned["valuation_zone"],
        "earning_type": scanned["earning_type"],
        "note": scanned["note"],
        "chains": homes,
        "in_book": bool(pos),
        "position": pos,
        "missing": missing,
        "buy_allowed": False,
        "buy_blocked_reason": "缺 {0}，禁止给出买入语句。只允许观察。".format("、".join(missing))
        if missing
        else "即使框架齐全，本阶段也不输出买入建议，只给观察与账本影响。",
    }


def resolve(query: str, store: Store = STORE, path: Path = CHAINS_YAML) -> Dict[str, Any]:
    """把「英伟达链 / 某公司怎么样 / 一段新闻」收成同一种结构。"""
    q = (query or "").strip()
    specs = load_chain_defs(path)
    q_lower = q.lower()
    for cid, spec in specs.items():
        aliases = [cid, spec.get("name") or ""] + list(spec.get("aliases") or [])
        if any(str(alias).lower() in q_lower or q_lower == str(alias).lower() for alias in aliases if alias):
            payload = brief(cid, store=store, path=path)
            payload["kind"] = "chain"
            payload["query"] = q
            return payload

    card = company_card(q, store=store, path=path)
    if card.get("found"):
        card["kind"] = "company"
        card["query"] = q
        if card.get("chains"):
            briefs = {}
            card["chain_briefs"] = []
            for home in card["chains"]:
                if home["chain"] not in briefs:
                    briefs[home["chain"]] = brief(home["chain"], store=store, path=path)
                payload = briefs[home["chain"]]
                card["chain_briefs"].append(
                    {
                        "id": home["chain"],
                        "money": payload.get("money"),
                        "book_verdict": (payload.get("book") or {}).get("verdict"),
                    }
                )
        return card

    hits = []
    for cid, spec in specs.items():
        kws = list(spec.get("news_keywords") or []) + list(spec.get("aliases") or [])
        matched = [kw for kw in kws if kw and kw.lower() in q_lower]
        if matched:
            payload = brief(cid, store=store, path=path)
            hits.append(
                {
                    "id": cid,
                    "name": spec.get("name"),
                    "matched": matched,
                    "money": payload.get("money"),
                    "book": payload.get("book"),
                    "layers": [
                        {
                            "id": layer["id"],
                            "name": layer["name"],
                            "avg_pct": layer["avg_pct"],
                        }
                        for layer in payload.get("layers") or []
                    ],
                }
            )
    if hits:
        return {
            "kind": "news",
            "query": q,
            "hits": hits,
            "refuse_generic": "只映射到你已经画过的产业链层级，不提供全市场相关股名单。",
            "disclaimer": "研究框架，非投资建议。",
        }
    return {
        "kind": "unknown",
        "query": q,
        "refuse": "无法落入你的股票池或已定义产业链。先补 universe / chains，再问。禁止临场选股。",
    }


def render_markdown(payload: Dict[str, Any]) -> str:
    kind = payload.get("kind") or ("chain" if "layers" in payload else "company")
    lines = ["# {0}".format(payload.get("name") or payload.get("query") or "简报"), ""]
    lines.append("研究框架，非投资建议。")
    lines.append("")
    if kind == "chain":
        lines.append("**逻辑**：{0}".format(payload.get("thesis") or ""))
        money = payload.get("money") or {}
        lines.append(
            "**今日资金位置**：{0}（{1}）".format(
                money.get("name") or "未知",
                "{0:+.2f}%".format(money["avg_pct"]) if money.get("avg_pct") is not None else "—",
            )
        )
        if payload.get("switched"):
            prev = (payload.get("prev_money") or {}).get("name") or ""
            lines.append("相对前一交易日，层级从 {0} 切到 {1}。".format(prev, money.get("name")))
        lines.append("")
        lines.append("| 层级 | 位置 | 均涨跌 | 上涨占比 | 持仓数 |")
        lines.append("|---|---|---:|---:|---:|")
        for layer in payload.get("layers") or []:
            avg = "—" if layer.get("avg_pct") is None else "{0:+.2f}%".format(layer["avg_pct"])
            br = "—" if layer.get("breadth") is None else "{0:.0%}".format(layer["breadth"])
            lines.append(
                "| {0} | {1} | {2} | {3} | {4} |".format(
                    layer.get("name"), layer.get("side"), avg, br, layer.get("held") or 0
                )
            )
        lines.append("")
        book = payload.get("book") or {}
        lines.append("**账本**：{0}".format(book.get("verdict") or ""))
        if book.get("stale_warning"):
            lines.append("持仓快照已过期 {0} 天，数量可能不准。".format(book.get("stale_days")))
        if book.get("orphans"):
            names = "、".join(item["name"] for item in book["orphans"])
            lines.append("账本孤儿（持有但无研究框架）：{0}".format(names))
        lines.append("")
        lines.append("禁止把链条领涨说成买入建议。缺估值三区或赚钱类型的个股只允许观察。")
    elif kind == "company":
        lines.append("- 代码 {0} · {1} · {2}".format(payload.get("code"), payload.get("sector"), payload.get("role")))
        lines.append("- 估值三区：**{0}** · 赚钱类型：**{1}** · {2}".format(
            payload.get("valuation_zone"), payload.get("earning_type"), (payload.get("ma5") or {}).get("vs_ma5")
        ))
        lines.append("- 买入许可：否。{0}".format(payload.get("buy_blocked_reason") or ""))
        if payload.get("chains"):
            lines.append("- 产业链：" + "、".join("{0}/{1}".format(c["name"], c["layer"]) for c in payload["chains"]))
        if payload.get("in_book"):
            lines.append("- 在账本中。")
        else:
            lines.append("- 不在当前持仓。")
    elif kind == "news":
        lines.append(payload.get("refuse_generic") or "")
        for hit in payload.get("hits") or []:
            money = hit.get("money") or {}
            lines.append("- {0}：资金在 {1}。{2}".format(
                hit.get("name"), money.get("name"), (hit.get("book") or {}).get("verdict") or ""
            ))
    else:
        lines.append(payload.get("refuse") or "")
    return "\n".join(lines) + "\n"
