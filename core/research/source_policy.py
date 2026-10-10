"""A 股来源层级。转载同一公告不算独立来源。"""
from __future__ import annotations

from urllib.parse import parse_qs, urlparse

TIER1_HOSTS = (
    "cninfo.com.cn", "sse.com.cn", "szse.cn", "szse.com.cn",
    # Primary sources for an organisation's own models, policies, incidents
    # and safeguards.  Tier 1 means first-hand, not independently verified.
    "openai.com", "anthropic.com", "deepmind.google",
)
TIER3_HOSTS = ("eastmoney.com", "cls.cn", "yicai.com", "stcn.com", "cs.com.cn", "wallstreetcn.com")
TIER4_HOSTS = ("xueqiu.com", "guba.", "taoguba.com")


def tier_for(url: str = "", source_type: str = "") -> int:
    host = (urlparse(url or "").hostname or "").lower()
    if any(token in host for token in TIER1_HOSTS):
        return 1
    if source_type in (
        "ANNUAL_REPORT", "EXCHANGE_FILING", "INVESTOR_RELATIONS",
        "COMPANY_FILING", "COMPANY_IR", "EARNINGS_CALL",
        "FILING", "EXCHANGE", "TRANSCRIPT", "OFFICIAL",
    ):
        return 1
    if (
        host.endswith(".gov.cn") or host == "gov.cn"
        or host.endswith(".gov") or host.endswith(".gov.uk")
        or host == "europa.eu" or host.endswith(".europa.eu")
    ):
        return 1
    if source_type in ("EXPERT", "RUMOR", "OTHER") or any(token in host for token in TIER4_HOSTS):
        return 4
    if any(token in host for token in TIER3_HOSTS):
        return 3
    if source_type in (
        "RESEARCH_NOTE", "SELL_SIDE", "BROKER", "MEDIA",
        "STRUCTURED_FINANCIAL_DATA",
    ):
        return 3
    return 3 if host or source_type else 4


def allows_critical_fact(tier: int) -> bool:
    return int(tier) < 4


def prefer(hits: list) -> list:
    return sorted(list(hits or []), key=lambda row: (tier_for(row.get("url") or ""), row.get("url") or ""))


def origin_family(url: str, title: str = "") -> str:
    parsed = urlparse(url or "")
    query = parse_qs(parsed.query)
    lowered = {key.lower(): value for key, value in query.items()}
    for key in ("announcementid", "bulletinid", "id"):
        values = lowered.get(key) or []
        if values and values[0]:
            return "announcement:{0}".format(values[0])
    if title and "公告" in title and parsed.path:
        return "path:{0}{1}".format(parsed.hostname or "", parsed.path)
    return ""


def same_announcement(url_a: str, url_b: str) -> bool:
    left = origin_family(url_a)
    right = origin_family(url_b)
    return bool(left) and left == right
