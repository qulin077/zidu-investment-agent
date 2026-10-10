"""看板环境脉冲：指数、VIX 恐慌指数、A股情绪、宏观快照。

VIX 来自 Yahoo ^VIX（CBOE 恐慌指数）；失败则退回 data/raw/macro。
A 股指数走新浪；涨停/炸板走 emotion_daily.csv。
"""
from __future__ import annotations

import csv
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.config import DATA_DIR, RAW_DIR
from core.http import HttpClient
from core.store import STORE, Store

_SINA = HttpClient(referer="https://finance.sina.com.cn/")
_YAHOO = HttpClient(referer="")
_CACHE = DATA_DIR / "cache"
_VIX_CACHE = _CACHE / "vix_live.json"
_IDX_CACHE = _CACHE / "index_live.json"

_INDEX_LIST = "s_sh000001,s_sz399001,s_sz399006,s_sh000300"


def _vix_band(value: Optional[float]) -> str:
    if value is None:
        return "—"
    if value < 15:
        return "偏低（偏贪婪）"
    if value < 20:
        return "正常"
    if value < 30:
        return "升温"
    if value < 40:
        return "恐慌"
    return "极端恐慌"


def _read_cache(path: Path, ttl: int) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    ts = payload.get("_ts") or 0
    if time.time() - ts > ttl:
        return None
    return payload


def _write_cache(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(payload)
    payload["_ts"] = time.time()
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def live_vix() -> Dict[str, Any]:
    cached = _read_cache(_VIX_CACHE, ttl=300)
    if cached:
        cached.pop("_ts", None)
        return cached
    try:
        data = None
        last_err: Optional[Exception] = None
        for host in ("query1.finance.yahoo.com", "query2.finance.yahoo.com"):
            try:
                data = _YAHOO.get_json(
                    "https://{0}/v8/finance/chart/%5EVIX?range=10d&interval=1d".format(host),
                    timeout=8,
                    attempts=1,
                )
                break
            except Exception as exc:  # noqa: BLE001
                last_err = exc
                data = None
        if data is None:
            raise last_err or RuntimeError("yahoo vix empty")
        result = ((data.get("chart") or {}).get("result") or [{}])[0]
        meta = result.get("meta") or {}
        quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
        closes = [c for c in (quote.get("close") or []) if c is not None]
        value = meta.get("regularMarketPrice")
        if value is None and closes:
            value = closes[-1]
        prev = meta.get("chartPreviousClose")
        chg = None
        if value is not None and prev:
            chg = round((float(value) - float(prev)) / float(prev) * 100, 2)
        series = [round(float(c), 2) for c in closes[-10:]]
        payload = {
            "name": "VIX 恐慌指数",
            "value": round(float(value), 2) if value is not None else None,
            "chg_1d_pct": chg,
            "band": _vix_band(float(value) if value is not None else None),
            "date": datetime.utcnow().strftime("%Y-%m-%d"),
            "source": "yahoo ^VIX",
            "series": series,
        }
        _write_cache(_VIX_CACHE, payload)
        payload.pop("_ts", None)
        return payload
    except Exception:  # noqa: BLE001
        path = RAW_DIR / "macro" / "macro_latest.json"
        fallback: Dict[str, Any] = {
            "name": "VIX 恐慌指数",
            "value": None,
            "chg_1d_pct": None,
            "band": "—",
            "date": "",
            "source": "macro_latest.json",
            "series": [],
        }
        if path.exists():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                node = ((raw.get("rates") or {}).get("vix")) or {}
                fallback.update(
                    {
                        "value": node.get("value"),
                        "chg_1d_pct": node.get("chg_1d_pct"),
                        "band": _vix_band(node.get("value")),
                        "date": node.get("date") or "",
                        "source": "macro_latest.json",
                    }
                )
            except (json.JSONDecodeError, OSError):
                pass
        return fallback


def live_indices() -> List[Dict[str, Any]]:
    cached = _read_cache(_IDX_CACHE, ttl=60)
    if cached:
        return cached.get("rows") or []
    try:
        text = _SINA.get(
            "https://hq.sinajs.cn/list={0}".format(_INDEX_LIST),
            encoding="gbk",
            timeout=8,
            attempts=1,
        )
    except Exception:  # noqa: BLE001
        return []
    rows = []
    for line in text.splitlines():
        if '="' not in line:
            continue
        left, _, rest = line.partition('="')
        code = left.rsplit("_", 1)[-1]
        parts = rest.rstrip('";').split(",")
        if len(parts) < 4:
            continue
        try:
            last = float(parts[1])
            chg = float(parts[3])
        except (TypeError, ValueError):
            continue
        rows.append(
            {
                "code": code,
                "name": parts[0],
                "close": last,
                "pct_chg": chg,
            }
        )
    _write_cache(_IDX_CACHE, {"rows": rows})
    return rows


def emotion_latest() -> Dict[str, Any]:
    path = RAW_DIR / "movers" / "emotion_daily.csv"
    empty = {"asof": "", "stage": "", "why": "", "action": "", "limit_up": None, "zhaban": None, "height": None, "zhaban_rate": None}
    if not path.exists():
        return empty
    with path.open("r", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        return empty
    last = rows[-1]
    try:
        zrate = float(last.get("zhaban_rate") or 0)
    except (TypeError, ValueError):
        zrate = None
    return {
        "asof": last.get("date") or "",
        "stage": last.get("mkt_stage") or "",
        "why": last.get("mkt_stage_why") or "",
        "action": last.get("mkt_stage_action") or "",
        "limit_up": _to_int(last.get("limit_up_count")),
        "zhaban": _to_int(last.get("zhaban_count")),
        "height": _to_int(last.get("max_board_height")),
        "zhaban_rate": round(zrate * 100, 1) if zrate is not None else None,
        "recent": [
            {
                "date": row.get("date"),
                "stage": row.get("mkt_stage"),
                "limit_up": _to_int(row.get("limit_up_count")),
            }
            for row in rows[-8:]
        ],
    }


def _to_int(value: Any) -> Optional[int]:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def limit_themes() -> Dict[str, Any]:
    movers = RAW_DIR / "movers"
    files = sorted(movers.glob("limit_up_drive_*.json"))
    if not files:
        return {"asof": "", "themes": []}
    path = files[-1]
    asof = path.stem.replace("limit_up_drive_", "")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"asof": asof, "themes": []}
    themes = (data.get("themes") or [])[:8]
    return {"asof": asof, "themes": themes}


def breadth(store: Store = STORE) -> Dict[str, Any]:
    day = store.max_date("quote_daily") or ""
    if not day:
        return {"asof": "", "up": 0, "down": 0, "flat": 0, "n": 0}
    rows = store.query(
        "SELECT pct_chg FROM quote_daily WHERE date = ? AND pct_chg IS NOT NULL",
        (day,),
    )
    up = sum(1 for r in rows if (r.get("pct_chg") or 0) > 0)
    down = sum(1 for r in rows if (r.get("pct_chg") or 0) < 0)
    flat = len(rows) - up - down
    return {"asof": day, "up": up, "down": down, "flat": flat, "n": len(rows)}


def macro_strip() -> Dict[str, Any]:
    path = RAW_DIR / "macro" / "macro_latest.json"
    if not path.exists():
        return {"asof": "", "items": []}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"asof": "", "items": []}
    items = []
    for group in ("commodities", "fx", "rates"):
        for key, node in (raw.get(group) or {}).items():
            if key in ("lpr_1y", "lpr_5y"):
                continue
            items.append(
                {
                    "id": key,
                    "name": node.get("name") or key,
                    "value": node.get("value"),
                    "chg_1d_pct": node.get("chg_1d_pct"),
                    "unit": node.get("unit") or "",
                    "date": node.get("date") or "",
                }
            )
    china = raw.get("china_latest") or {}
    if china.get("mfg_pmi") is not None:
        items.append(
            {
                "id": "pmi",
                "name": "制造业PMI",
                "value": china.get("mfg_pmi"),
                "chg_1d_pct": None,
                "unit": "",
                "date": china.get("asof_month") or "",
            }
        )
    return {"asof": raw.get("asof") or "", "items": items}


def pulse(store: Store = STORE) -> Dict[str, Any]:
    return {
        "indices": live_indices(),
        "vix": live_vix(),
        "emotion": emotion_latest(),
        "themes": limit_themes(),
        "breadth": breadth(store),
        "macro": macro_strip(),
    }
