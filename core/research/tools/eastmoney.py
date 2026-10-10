"""Public Eastmoney research-report discovery.

This adapter uses AKShare's maintained public-data wrapper to discover report
metadata and PDF links.  It is a free fallback, not a licensed broker research
feed; callers must keep the publisher, date and rating visible and must not
describe an empty result as proof that no coverage exists.
"""
from __future__ import annotations

from datetime import date, datetime
import re
from urllib.parse import urlparse


def research_report_hits(ticker: str, fetcher=None) -> dict:
    code = re.sub(r"\D", "", ticker or "")[:6]
    if len(code) != 6:
        return {"ok": False, "hits": [], "error_code": "EASTMONEY_INVALID_INPUT"}
    try:
        if fetcher is None:
            import akshare as ak
            frame = ak.stock_research_report_em(symbol=code)
            rows = frame.to_dict(orient="records")
        else:
            payload = fetcher(code)
            rows = payload.to_dict(orient="records") if hasattr(payload, "to_dict") else list(payload or [])
    except Exception as exc:
        return {"ok": False, "hits": [], "error_code": type(exc).__name__}

    hits = []
    for row in rows:
        url = str(row.get("报告PDF链接") or row.get("报告链接") or "").strip()
        host = (urlparse(url).hostname or "").lower()
        if not url.startswith("https://") or not host.endswith("dfcfw.com"):
            continue
        report_date = _date_text(row.get("日期"))
        broker = str(row.get("机构") or "").strip()
        rating = str(row.get("东财评级") or "").strip()
        name = str(row.get("股票简称") or code).strip()
        report_name = str(row.get("报告名称") or "券商研报").strip()
        labels = [value for value in (broker, rating, report_date) if value and value.lower() != "nan"]
        hits.append({
            "title": "{0}：{1}".format(name, report_name),
            "url": url,
            "snippet": "东方财富公开研报目录 · {0}".format(" · ".join(labels)),
            "published_at": report_date,
            "publisher": broker,
            "rating": rating,
            "source_type": "SELL_SIDE",
            "official": False,
            "provider": "eastmoney-akshare",
        })
    hits.sort(key=lambda item: item.get("published_at") or "", reverse=True)
    return {
        "ok": bool(hits), "hits": hits,
        "error_code": "" if hits else "EASTMONEY_RESEARCH_NOT_FOUND",
    }


def _date_text(value) -> str:
    if isinstance(value, (datetime, date)):
        return value.date().isoformat() if isinstance(value, datetime) else value.isoformat()
    text = str(value or "").strip()
    match = re.search(r"20\d{2}-\d{2}-\d{2}", text)
    return match.group(0) if match else ""
