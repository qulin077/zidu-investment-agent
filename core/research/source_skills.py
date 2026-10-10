"""Parallel evidence skills for company research.

These are bounded child skills owned by ``company-research``.  They do not
write conclusions and they are not independently user-callable tools.  Each
skill searches one evidence lane, labels what that lane is allowed to prove,
and returns leads for the shared reader / claim pipeline.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
import re
from urllib.parse import urlparse


@dataclass(frozen=True)
class SourceSkill:
    name: str
    label: str
    source_type: str
    evidence_role: str
    query: str
    max_sources: int = 2
    queries: tuple[str, ...] = ()
    ticker: str = ""
    annual_years: tuple[int, ...] = ()
    as_of: str = ""


_OFFICIAL_HOSTS = (
    "cninfo.com.cn", "sse.com.cn", "szse.cn", "szse.com.cn",
)


def plan(
    name: str, ticker: str = "", question: str = "", kind: str = "new",
    since: str = "", as_of: str = "", research_mode: str = "",
) -> list:
    """Build independent source lanes without asserting company facts."""
    subject = " ".join(value for value in (name, ticker) if value).strip()
    if not subject:
        return []
    year = (since or "")[:4]
    freshness = (" " + year + "之后") if kind == "followup" and year else " 最新"
    annual_years = _completed_fiscal_years(as_of)
    annual_queries = tuple(
        f"{subject} {fiscal_year} 年年度报告 官方 PDF 巨潮资讯"
        for fiscal_year in annual_years
    )
    filing_queries = annual_queries + (
        f"{subject}{freshness} 最新公告 财报 季报 半年报 业绩预告 官方 巨潮资讯 上交所 深交所",
    )
    management_queries = (
        f"{subject} 投资者关系活动记录表 site:static.cninfo.com.cn",
        f"{subject}{freshness} 业绩说明会 交流问答 官方",
        f"{subject}{freshness} 特定对象调研 路演 分析师会议 电话会议",
    )
    rows = [
        SourceSkill(
            "filing-analysis", "最近三年财报与最新公告", "COMPANY_FILING", "一手事实",
            f"{subject} 最近三年官方财报 年报 季报 公告",
            max_sources=8,
            queries=filing_queries,
            ticker=ticker,
            annual_years=tuple(annual_years),
            as_of=as_of,
        ),
        SourceSkill(
            "management-communication", "电话会与业绩会", "COMPANY_IR", "管理层解释与指引",
            f"{subject}{freshness} 业绩说明会 投资者关系活动记录 电话会议 管理层 指引",
            max_sources=8,
            queries=management_queries,
            ticker=ticker,
            as_of=as_of,
        ),
        SourceSkill(
            "sell-side-expectations", "券商研报", "SELL_SIDE", "预测与假设",
            f"{subject}{freshness} 券商研报 盈利预测 一致预期 分析师",
            max_sources=8,
            queries=(
                f"{subject}{freshness} 券商研报 盈利预测 一致预期 分析师",
                f"{subject}{freshness} 花旗 高盛 瑞银 摩根 目标价 评级 上调 下调",
                f"{subject}{freshness} 分析师评级 目标价 盈利预测 预期修订",
            ),
            ticker=ticker,
            as_of=as_of,
        ),
        SourceSkill(
            "market-narrative", "市场观点", "EXPERT", "叙事与争议线索",
            f"{subject}{freshness} 雪球 市场观点 预期差 争议",
        ),
        SourceSkill(
            "risk-disconfirmation", "反方证据", "OTHER", "风险与证伪",
            f"{subject}{freshness} 监管问询 业绩下修 减值 诉讼 风险",
        ),
    ]
    focus = question or ""
    if research_mode in ("FULL_DOSSIER", "INCREMENTAL_UPDATE"):
        keep = {row.name for row in rows}
    elif any(token in focus for token in ("财报", "收入", "利润", "现金流", "毛利", "基本盘")):
        keep = {"filing-analysis", "management-communication", "risk-disconfirmation"}
    elif any(token in focus for token in ("预期", "估值", "股价", "研报", "一致预期")):
        keep = {
            "filing-analysis", "management-communication", "sell-side-expectations",
            "market-narrative", "risk-disconfirmation",
        }
    elif any(token in focus for token in ("风险", "失效", "证伪")):
        keep = {"filing-analysis", "management-communication", "market-narrative", "risk-disconfirmation"}
    else:
        keep = {row.name for row in rows}
    return [asdict(row) for row in rows if row.name in keep]


def vendor_news_plan(name: str, ticker: str = "") -> list[dict]:
    """Bounded iFinD news lanes for company expectations and catalysts.

    Public report catalogues are useful for domestic broker PDFs but routinely
    miss foreign houses and pages that cannot be fetched without JavaScript.
    iFinD excerpts are leads/secondary evidence, never a substitute for the
    original report, so their provenance remains explicit.
    """
    subject = " ".join(value for value in (name, ticker) if value).strip()
    if not subject:
        return []
    return [
        {
            "name": "sell-side-expectations",
            "label": "券商研报",
            "evidence_role": "卖方预测、目标价和预期修订线索；继续追溯原始研报",
            "query": f"{subject} 最新 券商 外资研报 目标价 评级 盈利预测 上调 下调",
        },
        {
            "name": "market-narrative",
            "label": "市场观点",
            "evidence_role": "催化、市场叙事和争议线索；关键事实需一手来源交叉验证",
            "query": f"{subject} 最新 催化 市场预期 争议 估值 风险",
        },
    ]


def vendor_window_start(as_of: str = "", since: str = "") -> str:
    """Keep enough overlap to compare revisions instead of only seeing today."""
    end = _parse_date(as_of) or date.today()
    floor = end - timedelta(days=550)
    previous = _parse_date(since)
    if previous:
        floor = min(previous - timedelta(days=45), floor)
    return floor.isoformat()


def classify_vendor_excerpt(row: dict, lane: dict) -> dict:
    result = dict(row)
    result.update({
        "source_skill": lane.get("name") or "",
        "source_label": lane.get("label") or lane.get("name") or "",
        "evidence_role": lane.get("evidence_role") or "",
        "source_grade": "VENDOR_EXCERPT",
    })
    return result


def rank_hits(hits: list, skill: dict | None = None) -> list:
    """Prefer recent, expectation-bearing material in fast-changing lanes."""
    lane = (skill or {}).get("name") or ""
    if lane not in ("sell-side-expectations", "market-narrative"):
        from core.research.source_policy import prefer
        return prefer(hits)

    def key(row: dict):
        blob = " ".join((row.get("title") or "", row.get("snippet") or ""))
        signal = 0 if any(token in blob for token in (
            "目标价", "盈利预测", "评级", "上调", "下调", "研报", "预期", "催化",
        )) else 1
        parsed = _parse_date(row.get("published_at") or "")
        ordinal = parsed.toordinal() if parsed else 0
        from core.research.source_policy import tier_for
        return (signal, -ordinal, tier_for(row.get("url") or "", row.get("source_type") or ""), row.get("url") or "")

    return sorted(list(hits or []), key=key)


def _parse_date(value: str) -> date | None:
    match = re.search(r"20\d{2}[-/]\d{1,2}[-/]\d{1,2}", str(value or ""))
    if not match:
        return None
    try:
        return datetime.strptime(match.group(0).replace("/", "-"), "%Y-%m-%d").date()
    except ValueError:
        return None


def search_parallel(skills: list, provider: str, search=None, progress=None) -> list:
    """Run independent searches concurrently and return stable plan order."""
    if not skills:
        return []

    def run(row: dict) -> dict:
        if progress is not None:
            progress("source_skill_started", "running", {
                "name": row.get("name") or "",
                "label": row.get("label") or "",
                "evidence_role": row.get("evidence_role") or "",
                "query": row.get("query") or "",
            })
        hits = []
        errors = []
        direct_calls = 0
        official_complete = False
        if search is None and row.get("name") == "filing-analysis" and row.get("ticker"):
            direct_calls = 2
            try:
                from core.research.tools.cninfo import annual_report_hits, periodic_report_hits
                official = annual_report_hits(row["ticker"], list(row.get("annual_years") or ()))
                periodic = periodic_report_hits(row["ticker"], row.get("as_of") or "")
            except Exception as exc:
                official = {"ok": False, "hits": [], "error_code": type(exc).__name__}
                periodic = {"ok": False, "hits": [], "error_code": type(exc).__name__}
            if official.get("ok"):
                hits.extend(official.get("hits") or [])
                found_years = {item.get("report_year") for item in official.get("hits") or []}
                official_complete = all(year in found_years for year in (row.get("annual_years") or ()))
            elif official.get("error_code"):
                errors.append(official.get("error_code"))
            if periodic.get("ok"):
                hits.extend(periodic.get("hits") or [])
            elif periodic.get("error_code") and periodic.get("error_code") != "CNINFO_PERIODIC_REPORT_NOT_FOUND":
                errors.append(periodic.get("error_code"))
        if search is None and row.get("name") == "management-communication" and row.get("ticker"):
            direct_calls += 1
            try:
                from core.research.tools.cninfo import ir_activity_hits
                official_ir = ir_activity_hits(row["ticker"], row.get("as_of") or "")
            except Exception as exc:
                official_ir = {"ok": False, "hits": [], "error_code": type(exc).__name__}
            if official_ir.get("ok"):
                hits.extend(official_ir.get("hits") or [])
            elif official_ir.get("error_code") and official_ir.get("error_code") != "CNINFO_IR_ACTIVITY_NOT_FOUND":
                errors.append(official_ir.get("error_code"))
        if row.get("name") == "sell-side-expectations" and row.get("ticker"):
            if search is None:
                direct_calls += 1
                try:
                    from core.research.tools.eastmoney import research_report_hits
                    public_reports = research_report_hits(row["ticker"])
                except Exception as exc:
                    public_reports = {"ok": False, "hits": [], "error_code": type(exc).__name__}
                if public_reports.get("ok"):
                    hits.extend(public_reports.get("hits") or [])
                elif public_reports.get("error_code") and public_reports.get("error_code") != "EASTMONEY_RESEARCH_NOT_FOUND":
                    errors.append(public_reports.get("error_code"))
        queries = list(row.get("queries") or ()) or [row["query"]]
        if official_complete and queries:
            # The official catalogue is authoritative for annual reports.  Keep
            # only the latest-periodic-report query instead of asking a generic
            # search engine for the same three PDFs again.
            queries = [queries[-1]]
        for query in queries:
            try:
                if search is not None:
                    result = search(query, max_results=8, region="cn-zh")
                else:
                    from core.research.tools import providers
                    result = providers.search(query, provider, max_results=8, region="cn-zh")
            except Exception as exc:  # One source lane must not cancel the others.
                result = {"ok": False, "hits": [], "error_code": type(exc).__name__}
            if result and result.get("ok"):
                hits.extend(result.get("hits") or [])
            elif result and result.get("error_code"):
                errors.append(result.get("error_code"))
        packed = dict(row)
        packed.update({
            "ok": bool(hits),
            "hits": _unique_hits(hits),
            "error_code": errors[-1] if errors and not hits else "",
            "query_count": len(queries) + direct_calls,
            "official_annual_reports_complete": official_complete,
        })
        if progress is not None:
            progress("source_skill_search_completed", "ok" if hits else "gap", {
                "name": row.get("name") or "",
                "label": row.get("label") or "",
                "evidence_role": row.get("evidence_role") or "",
                "query": row.get("query") or "",
                "count": len(packed["hits"]),
                "query_count": packed["query_count"],
                "official_annual_reports_complete": official_complete,
                "error_code": packed.get("error_code") or "",
            })
        return packed

    workers = min(5, len(skills))
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="research-source") as pool:
        # executor.map preserves input order even though the work is concurrent.
        return list(pool.map(run, skills))


def classify_opened(row: dict, skill: dict) -> dict:
    """Apply a conservative source type after the page body has been opened."""
    result = dict(row)
    host = (urlparse(result.get("canonical_url") or result.get("url") or "").hostname or "").lower()
    official = any(token in host for token in _OFFICIAL_HOSTS)
    lane = skill.get("name") or ""
    if lane == "filing-analysis":
        source_type = "COMPANY_FILING" if official else "MEDIA"
    elif lane == "management-communication":
        source_type = "COMPANY_IR" if official else "MEDIA"
    elif lane == "sell-side-expectations":
        source_type = "SELL_SIDE"
    elif lane == "market-narrative":
        source_type = "EXPERT"
    elif lane == "risk-disconfirmation":
        source_type = "EXCHANGE" if official else "MEDIA"
    else:
        source_type = result.get("source_type") or "OTHER"
    result.update({
        "source_type": source_type,
        "source_skill": lane,
        "source_label": skill.get("label") or lane,
        "evidence_role": skill.get("evidence_role") or "",
        "source_grade": "OPENED_REPORT" if lane == "sell-side-expectations" else result.get("source_grade") or "",
    })
    return result

def public_view(skills: list) -> list:
    return [
        {
            "name": row.get("name") or "",
            "label": row.get("label") or "",
            "evidence_role": row.get("evidence_role") or "",
            "query": row.get("query") or "",
            "queries": list(row.get("queries") or ()),
            "max_sources": int(row.get("max_sources") or 2),
            "ticker": row.get("ticker") or "",
            "annual_years": list(row.get("annual_years") or ()),
            "as_of": row.get("as_of") or "",
            "status": row.get("status") or "pending",
            "source_count": int(row.get("source_count") or 0),
            "error_code": row.get("error_code") or "",
            "official_annual_reports_complete": bool(row.get("official_annual_reports_complete")),
        }
        for row in skills
    ]


def _completed_fiscal_years(as_of: str = "") -> list[int]:
    try:
        current = date.fromisoformat((as_of or "")[:10])
    except ValueError:
        current = date.today()
    latest = current.year - (1 if current.month >= 5 else 2)
    return [latest, latest - 1, latest - 2]


def _unique_hits(hits: list) -> list:
    result = []
    seen = set()
    for row in hits:
        key = row.get("url") or (row.get("title"), row.get("snippet"))
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(row)
    return result
