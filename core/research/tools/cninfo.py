"""Read-only client for official CNInfo disclosure listings.

Generic search engines frequently miss or mis-rank disclosure PDFs.  This
module resolves the issuer's CNInfo orgId from the official stock list and
queries the official announcement catalogue directly.  It returns leads only;
the shared reader still downloads, parses, grounds, and stores the document.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
import json
import re
import urllib.parse
import urllib.request


_BASE = "https://www.cninfo.com.cn"
_QUERY = _BASE + "/new/hisAnnouncement/query"
_PDF_BASE = "https://static.cninfo.com.cn/"
_REFERER = _BASE + "/new/commonUrl/pageOfSearch?url=disclosure/list/search"
_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0 Safari/537.36"
_CN_TZ = timezone(timedelta(hours=8))


def annual_report_hits(code: str, years: list[int], timeout: int = 15, transport=None) -> dict:
    """Return one official full annual-report PDF for each requested year."""
    code = re.sub(r"\D", "", code or "")[:6]
    wanted = sorted({int(year) for year in years or []}, reverse=True)
    if len(code) != 6 or not wanted:
        return {"ok": False, "hits": [], "error_code": "CNINFO_INVALID_INPUT"}
    market = _market(code)
    try:
        if transport is not None:
            stock_payload, announcement_payload = transport(code, wanted, market)
        else:
            stock_payload = _get_json(_stock_list_url(market), timeout)
            stock = next((row for row in stock_payload.get("stockList") or [] if row.get("code") == code), None)
            if not stock or not stock.get("orgId"):
                return {"ok": False, "hits": [], "error_code": "CNINFO_ORG_NOT_FOUND"}
            announcement_payload = _post_query(code, stock["orgId"], wanted, market, timeout)
    except Exception as exc:  # Network failure is a source gap, not a turn failure.
        return {"ok": False, "hits": [], "error_code": type(exc).__name__}

    stock = next((row for row in stock_payload.get("stockList") or [] if row.get("code") == code), {})
    issuer = stock.get("zwjc") or ""
    by_year = {}
    for row in announcement_payload.get("announcements") or []:
        title = _clean_title(row.get("announcementTitle") or "")
        year = _annual_year(title)
        if year not in wanted or "摘要" in title or "英文" in title:
            continue
        url = urllib.parse.urljoin(_PDF_BASE, row.get("adjunctUrl") or "")
        if not url.startswith(_PDF_BASE):
            continue
        candidate = {
            "title": "{0}：{1}".format(row.get("secName") or issuer or code, title),
            "url": url,
            "snippet": "巨潮资讯官方披露 · {0} · {1}".format(code, title),
            "published_at": _published_at(row.get("announcementTime")),
            "source_type": "COMPANY_FILING",
            "official": True,
            "report_year": year,
            "announcement_id": row.get("announcementId") or "",
        }
        current = by_year.get(year)
        if current is None or _title_rank(title, row) < _title_rank(_title_from_hit(current), current):
            by_year[year] = candidate
    hits = [by_year[year] for year in wanted if year in by_year]
    return {
        "ok": bool(hits), "hits": hits,
        "error_code": "" if hits else "CNINFO_ANNUAL_REPORT_NOT_FOUND",
        "org_id": stock.get("orgId") or "", "issuer": issuer,
    }


def periodic_report_hits(code: str, as_of: str = "", timeout: int = 15, transport=None) -> dict:
    """Return full quarterly/half-year reports after the annual baseline."""
    code = re.sub(r"\D", "", code or "")[:6]
    try:
        cutoff = datetime.strptime((as_of or "")[:10], "%Y-%m-%d").date()
    except ValueError:
        cutoff = datetime.now(tz=_CN_TZ).date()
    if len(code) != 6:
        return {"ok": False, "hits": [], "error_code": "CNINFO_INVALID_INPUT"}
    latest_annual_year = cutoff.year - (1 if cutoff.month >= 5 else 2)
    market = _market(code)
    try:
        if transport is not None:
            stock_payload, announcement_payload = transport(code, cutoff.isoformat(), market)
        else:
            stock_payload = _get_json(_stock_list_url(market), timeout)
            stock = next((row for row in stock_payload.get("stockList") or [] if row.get("code") == code), None)
            if not stock or not stock.get("orgId"):
                return {"ok": False, "hits": [], "error_code": "CNINFO_ORG_NOT_FOUND"}
            announcement_payload = _post_periodic_query(
                code, stock["orgId"], latest_annual_year + 1, cutoff.isoformat(), market, timeout,
            )
    except Exception as exc:
        return {"ok": False, "hits": [], "error_code": type(exc).__name__}

    stock = next((row for row in stock_payload.get("stockList") or [] if row.get("code") == code), {})
    issuer = stock.get("zwjc") or ""
    by_period = {}
    for row in announcement_payload.get("announcements") or []:
        title = _clean_title(row.get("announcementTitle") or "")
        period = _period_label(title)
        if not period or "摘要" in title or "英文" in title:
            continue
        year = int(period[:4])
        if year <= latest_annual_year:
            continue
        published_at = _published_at(row.get("announcementTime"))
        if published_at and published_at > cutoff.isoformat():
            continue
        url = urllib.parse.urljoin(_PDF_BASE, row.get("adjunctUrl") or "")
        if not url.startswith(_PDF_BASE):
            continue
        candidate = {
            "title": "{0}：{1}".format(row.get("secName") or issuer or code, title),
            "url": url,
            "snippet": "巨潮资讯官方披露 · {0} · {1}".format(code, title),
            "published_at": published_at,
            "source_type": "COMPANY_FILING",
            "official": True,
            "report_year": year,
            "report_period": period,
            "announcement_id": row.get("announcementId") or "",
        }
        current = by_period.get(period)
        if current is None or _title_rank(title, row) < _title_rank(_title_from_hit(current), current):
            by_period[period] = candidate
    hits = sorted(by_period.values(), key=lambda item: _period_sort(item["report_period"]), reverse=True)
    return {
        "ok": bool(hits), "hits": hits,
        "error_code": "" if hits else "CNINFO_PERIODIC_REPORT_NOT_FOUND",
        "org_id": stock.get("orgId") or "", "issuer": issuer,
    }


def ir_activity_hits(
    code: str, as_of: str = "", *, lookback_years: int = 5,
    timeout: int = 15, transport=None,
) -> dict:
    """Return official investor-relations records without a search provider.

    Performance briefings, roadshows, analyst meetings and telephone/online
    exchanges are normally disclosed as ``投资者关系活动记录表``. Generic web
    search is an unreliable discovery mechanism for these PDFs, so company
    research queries the CNInfo catalogue directly.
    """
    code = re.sub(r"\D", "", code or "")[:6]
    try:
        cutoff = datetime.strptime((as_of or "")[:10], "%Y-%m-%d").date()
    except ValueError:
        cutoff = datetime.now(tz=_CN_TZ).date()
    if len(code) != 6:
        return {"ok": False, "hits": [], "error_code": "CNINFO_INVALID_INPUT"}
    start_year = cutoff.year - max(1, int(lookback_years))
    market = _market(code)
    try:
        if transport is not None:
            stock_payload, announcement_payload = transport(
                code, "{0}-01-01".format(start_year), cutoff.isoformat(), market,
            )
        else:
            stock_payload = _get_json(_stock_list_url(market), timeout)
            stock = next(
                (row for row in stock_payload.get("stockList") or [] if row.get("code") == code),
                None,
            )
            if not stock or not stock.get("orgId"):
                return {"ok": False, "hits": [], "error_code": "CNINFO_ORG_NOT_FOUND"}
            # CNInfo's ``searchkey`` does not consistently match these records.
            # Page through this issuer's official catalogue, then filter titles.
            announcements = []
            page_num = 1
            total = None
            while total is None or len(announcements) < total:
                page = _post_keyword_query(
                    code, stock["orgId"], "",
                    "{0}-01-01".format(start_year), cutoff.isoformat(), market, timeout,
                    page_num=page_num,
                )
                rows = page.get("announcements") or []
                if not rows:
                    break
                announcements.extend(rows)
                try:
                    total = int(page.get("totalAnnouncement"))
                except (TypeError, ValueError):
                    total = None
                page_num += 1
            announcement_payload = {"announcements": announcements}
    except Exception as exc:
        return {"ok": False, "hits": [], "error_code": type(exc).__name__}

    stock = next((row for row in stock_payload.get("stockList") or [] if row.get("code") == code), {})
    issuer = stock.get("zwjc") or ""
    hits = []
    for row in announcement_payload.get("announcements") or []:
        title = _clean_title(row.get("announcementTitle") or "")
        if not any(token in title for token in (
            "投资者关系活动记录表", "业绩说明会", "分析师会议", "路演", "电话会议",
        )):
            continue
        published_at = _published_at(row.get("announcementTime"))
        if published_at and published_at > cutoff.isoformat():
            continue
        url = urllib.parse.urljoin(_PDF_BASE, row.get("adjunctUrl") or "")
        if not url.startswith(_PDF_BASE):
            continue
        hits.append({
            "title": "{0}：{1}".format(row.get("secName") or issuer or code, title),
            "url": url,
            "snippet": "巨潮资讯官方投资者关系披露 · {0} · {1}".format(code, title),
            "published_at": published_at,
            "source_type": "COMPANY_IR",
            "official": True,
            "announcement_id": row.get("announcementId") or "",
        })
    hits.sort(key=lambda item: item.get("published_at") or "", reverse=True)
    return {
        "ok": bool(hits), "hits": hits,
        "error_code": "" if hits else "CNINFO_IR_ACTIVITY_NOT_FOUND",
        "org_id": stock.get("orgId") or "", "issuer": issuer,
    }


def _market(code: str) -> dict:
    if code.startswith("6"):
        return {"column": "sse", "plate": "sh", "stock_list": "sse_stock.json"}
    if code.startswith(("4", "8")):
        return {"column": "third", "plate": "bj", "stock_list": "third_stock.json"}
    return {
        "column": "szse", "plate": "szcy" if code.startswith("3") else "sz",
        "stock_list": "szse_stock.json",
    }


def _stock_list_url(market: dict) -> str:
    return _BASE + "/new/data/" + market["stock_list"]


def _get_json(url: str, timeout: int) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": _UA, "Referer": _REFERER})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _post_query(code: str, org_id: str, years: list[int], market: dict, timeout: int) -> dict:
    data = urllib.parse.urlencode({
        "pageNum": "1", "pageSize": "30", "column": market["column"],
        "tabName": "fulltext", "plate": market["plate"],
        "stock": "{0},{1}".format(code, org_id), "searchkey": "", "secid": "",
        "category": "category_ndbg_szsh;", "trade": "",
        "seDate": "{0}-01-01~{1}-06-30".format(min(years) + 1, max(years) + 1),
        "sortName": "", "sortType": "", "isHLtitle": "true",
    }).encode("utf-8")
    request = urllib.request.Request(_QUERY, data=data, headers={
        "User-Agent": _UA, "Referer": _REFERER, "Origin": _BASE,
        "X-Requested-With": "XMLHttpRequest",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    })
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _post_periodic_query(code: str, org_id: str, start_year: int, as_of: str, market: dict, timeout: int) -> dict:
    data = urllib.parse.urlencode({
        "pageNum": "1", "pageSize": "50", "column": market["column"],
        "tabName": "fulltext", "plate": market["plate"],
        "stock": "{0},{1}".format(code, org_id), "searchkey": "", "secid": "",
        "category": "category_yjdbg_szsh;category_bndbg_szsh;category_sjdbg_szsh;",
        "trade": "", "seDate": "{0}-01-01~{1}".format(start_year, as_of),
        "sortName": "", "sortType": "", "isHLtitle": "true",
    }).encode("utf-8")
    request = urllib.request.Request(_QUERY, data=data, headers={
        "User-Agent": _UA, "Referer": _REFERER, "Origin": _BASE,
        "X-Requested-With": "XMLHttpRequest",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    })
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _post_keyword_query(
    code: str, org_id: str, keyword: str, start_date: str, end_date: str,
    market: dict, timeout: int, *, page_num: int = 1,
) -> dict:
    data = urllib.parse.urlencode({
        "pageNum": str(max(1, int(page_num))), "pageSize": "30", "column": market["column"],
        "tabName": "fulltext", "plate": market["plate"],
        "stock": "{0},{1}".format(code, org_id), "searchkey": keyword,
        "secid": "", "category": "", "trade": "",
        "seDate": "{0}~{1}".format(start_date, end_date),
        "sortName": "time", "sortType": "desc", "isHLtitle": "true",
    }).encode("utf-8")
    request = urllib.request.Request(_QUERY, data=data, headers={
        "User-Agent": _UA, "Referer": _REFERER, "Origin": _BASE,
        "X-Requested-With": "XMLHttpRequest",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    })
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _clean_title(value: str) -> str:
    return re.sub(r"<[^>]+>", "", value or "").strip()


def _annual_year(title: str) -> int | None:
    match = re.search(r"(20\d{2})\s*年\s*年度报告", title or "")
    return int(match.group(1)) if match else None


def _period_label(title: str) -> str:
    match = re.search(r"(20\d{2})\s*年\s*(第一季度|半年度|第三季度)报告", title or "")
    if not match:
        return ""
    suffix = {"第一季度": "Q1", "半年度": "H1", "第三季度": "Q3"}[match.group(2)]
    return match.group(1) + suffix


def _period_sort(value: str) -> tuple:
    match = re.match(r"(20\d{2})(Q1|H1|Q3)", value or "")
    if not match:
        return 0, 0
    return int(match.group(1)), {"Q1": 1, "H1": 2, "Q3": 3}[match.group(2)]


def _published_at(value) -> str:
    try:
        return datetime.fromtimestamp(int(value) / 1000, tz=_CN_TZ).date().isoformat()
    except (TypeError, ValueError, OSError):
        return ""


def _title_rank(title: str, row: dict) -> tuple:
    # Prefer a later corrected/restated full report when one exists.
    corrected = 0 if any(token in title for token in ("修订", "更正", "补充后")) else 1
    timestamp = int(row.get("announcementTime") or 0)
    return corrected, -timestamp


def _title_from_hit(hit: dict) -> str:
    return (hit.get("title") or "").split("：", 1)[-1]
