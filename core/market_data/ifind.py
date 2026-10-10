"""iFinD MCP adapter.

The vendor skill installed in Codex is useful documentation and a development
credential, but the product cannot import files from ``~/.codex/skills`` at
runtime.  This module therefore implements the small MCP HTTP boundary the app
needs and keeps credentials outside the repository.

Enable it with either ``IFIND_MCP_TOKEN`` or ``IFIND_MCP_CONFIG``.  For local
development, ``SA_ENABLE_IFIND=1`` also permits discovery of the installed
Codex skill config.  No token is ever included in errors or persisted data.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

import requests

from core.calendar import to_iso
from core.ingest.base import as_float
from core.market_data.free import FreeMarketDataGateway, MarketFetch
from core.symbols import is_valid_code, normalize_code

BASE_URL = "https://api-mcp.51ifind.com:8643/ds-mcp-servers"
SERVER_PATHS = {
    "stock": "hexin-ifind-ds-stock-mcp",
    "news": "hexin-ifind-ds-news-mcp",
    "index": "hexin-ifind-ds-index-mcp",
    "edb": "hexin-ifind-ds-edb-mcp",
}
ALLOWED_TOOLS = {
    "stock": {
        "get_stock_summary", "search_stocks", "get_stock_performance",
        "get_stock_info", "get_stock_shareholders", "get_stock_financials",
        "get_risk_indicators", "get_stock_events", "get_esg_data",
        "stock_highfreq_quotes",
    },
    "news": {"search_notice", "search_news", "search_trending_news"},
    "index": {"index_data", "sector_data", "index_highfreq_quotes"},
    "edb": {"get_edb_data", "search_edb"},
}
_BLOCKED_KEYS = {"__proto__", "prototype", "constructor"}


class IfindError(RuntimeError):
    """Sanitised provider error.  It never contains the credential."""


@dataclass(frozen=True)
class IfindConfig:
    token: str
    base_url: str = BASE_URL

    @classmethod
    def from_environment(cls) -> Optional["IfindConfig"]:
        token = (os.environ.get("IFIND_MCP_TOKEN") or "").strip()
        configured_path = (os.environ.get("IFIND_MCP_CONFIG") or "").strip()
        if configured_path:
            token = token or _read_token(Path(configured_path).expanduser())
        enabled = (os.environ.get("SA_ENABLE_IFIND") or "").strip().lower()
        if not token and enabled in {"1", "true", "yes", "on"}:
            token = _read_token(
                Path.home() / ".codex" / "skills" / "ifind-finance-data" / "mcp_config.json"
            )
        if not token:
            return None
        base = (os.environ.get("IFIND_MCP_BASE_URL") or BASE_URL).strip().rstrip("/")
        return cls(token=token, base_url=base)


def _read_token(path: Path) -> str:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return ""
    return str(payload.get("auth_token") or "").strip() if isinstance(payload, dict) else ""


class IfindMcpClient:
    """Minimal stateful MCP-over-HTTP client for the iFinD data services."""

    def __init__(
        self, config: IfindConfig, *, session: Optional[requests.Session] = None,
        timeout: int = 45,
    ) -> None:
        self.config = config
        self.session = session or requests.Session()
        self.timeout = timeout
        self._sessions: Dict[str, str] = {}
        self._request_ids: Dict[str, int] = {}

    @classmethod
    def from_environment(cls) -> Optional["IfindMcpClient"]:
        config = IfindConfig.from_environment()
        return cls(config) if config else None

    def call(self, server: str, tool: str, arguments: Mapping[str, Any]) -> Dict[str, Any]:
        self._validate(server, tool, arguments)
        self._initialize(server)
        response = self._post(server, {
            "jsonrpc": "2.0",
            "id": self._next_id(server),
            "method": "tools/call",
            "params": {"name": tool, "arguments": dict(arguments)},
        })
        body = self._json(response)
        if isinstance(body, dict) and body.get("error"):
            raise IfindError("iFinD {0} 调用失败".format(tool))
        if response.status_code >= 400:
            raise IfindError("iFinD {0} HTTP {1}".format(tool, response.status_code))
        return _unwrap_tool_content(body)

    def _initialize(self, server: str) -> None:
        if server in self._sessions:
            return
        response = self._post(server, {
            "jsonrpc": "2.0",
            "id": self._next_id(server),
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "stock-assistant", "version": "1.0.0"},
            },
        }, include_session=False, timeout=30)
        if response.status_code >= 400:
            raise IfindError("iFinD 初始化失败（HTTP {0}）".format(response.status_code))
        session_id = response.headers.get("Mcp-Session-Id") or response.headers.get("mcp-session-id")
        if not session_id:
            raise IfindError("iFinD 初始化未返回会话标识")
        self._sessions[server] = session_id
        notify = self._post(
            server, {"jsonrpc": "2.0", "method": "notifications/initialized"}, timeout=10,
        )
        if notify.status_code >= 400:
            self._sessions.pop(server, None)
            raise IfindError("iFinD 会话确认失败（HTTP {0}）".format(notify.status_code))

    def _post(
        self, server: str, payload: Mapping[str, Any], *, include_session: bool = True,
        timeout: Optional[int] = None,
    ):
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Authorization": self.config.token,
        }
        if include_session and server in self._sessions:
            headers["Mcp-Session-Id"] = self._sessions[server]
        try:
            return self.session.post(
                "{0}/{1}".format(self.config.base_url, SERVER_PATHS[server]),
                json=dict(payload), headers=headers, timeout=timeout or self.timeout,
            )
        except requests.RequestException as exc:
            raise IfindError("iFinD 网络请求失败：{0}".format(type(exc).__name__)) from exc

    @staticmethod
    def _json(response) -> Any:
        try:
            return response.json()
        except (ValueError, TypeError) as exc:
            raise IfindError("iFinD 返回了无法解析的数据") from exc

    def _next_id(self, server: str) -> int:
        value = self._request_ids.get(server, 0) + 1
        self._request_ids[server] = value
        return value

    @staticmethod
    def _validate(server: str, tool: str, arguments: Mapping[str, Any]) -> None:
        if server not in SERVER_PATHS or tool not in ALLOWED_TOOLS.get(server, set()):
            raise ValueError("unsupported iFinD tool: {0}/{1}".format(server, tool))
        if not isinstance(arguments, Mapping):
            raise TypeError("iFinD arguments must be an object")

        def walk(value: Any) -> None:
            if value is None:
                return
            if isinstance(value, Mapping):
                for key, item in value.items():
                    if key in _BLOCKED_KEYS:
                        raise TypeError("blocked iFinD argument field")
                    walk(item)
                return
            if isinstance(value, (list, tuple)):
                for item in value:
                    walk(item)
                return
            if isinstance(value, float) and not math.isfinite(value):
                raise TypeError("invalid iFinD number")
            if not isinstance(value, (str, int, float, bool)):
                raise TypeError("unsupported iFinD argument value")

        walk(arguments)


class IfindDataService:
    """Product-facing structured queries used by market and research tools."""

    def __init__(self, client: IfindMcpClient) -> None:
        self.client = client

    @classmethod
    def from_environment(cls) -> Optional["IfindDataService"]:
        client = IfindMcpClient.from_environment()
        return cls(client) if client else None

    def stock_snapshots(self, codes: Iterable[str]) -> MarketFetch:
        targets = _targets(codes)
        chosen: Dict[str, Dict[str, Any]] = {}
        errors: List[str] = []
        for start in range(0, len(targets), 10):
            batch = targets[start:start + 10]
            try:
                payload = self.client.call("stock", "stock_highfreq_quotes", {
                    "symbols": ",".join(batch),
                    "indicators": "开盘价,最高价,最低价,最新价,涨跌幅,成交量,成交额,总市值,市盈率TTM",
                    "data_mode": "real_time",
                })
                for row in _table_records(payload):
                    parsed = _snapshot_row(row)
                    if parsed and parsed["code"] in batch:
                        chosen[parsed["code"]] = parsed
            except (IfindError, ValueError, TypeError) as exc:
                errors.append(str(exc))
        return MarketFetch(
            rows=[chosen[code] for code in targets if code in chosen],
            providers=["ifind"] if chosen else [], errors=errors,
            missing=[code for code in targets if code not in chosen],
        )

    def financials(self, company: str, period: str = "") -> Dict[str, Any]:
        subject = (company or "").strip()
        if not subject:
            raise ValueError("company is required")
        time_scope = period or "最近三年年度及最新一期"
        query = (
            "{0}{1}的营业收入、营业收入同比、毛利率、归母净利润、归母净利润同比、"
            "经营活动现金流、资产负债率、ROE、应收账款和存货"
        ).format(subject, time_scope)
        return self.client.call("stock", "get_stock_financials", {"query": query})

    def notices(
        self, company: str, *, time_start: str = "", time_end: str = "", size: int = 8,
    ) -> Dict[str, Any]:
        today = date.today().isoformat()
        return self.client.call("news", "search_notice", {
            "query": "{0} 年报 季报 业绩说明会 重大事项".format(company),
            "time_start": time_start or "2023-01-01", "time_end": time_end or today,
            "size": min(max(int(size), 1), 20),
        })

    def news(
        self, query: str, *, time_start: str = "", time_end: str = "", size: int = 8,
    ) -> Dict[str, Any]:
        return self.client.call("news", "search_news", {
            "query": query, "time_start": time_start or "2023-01-01",
            "time_end": time_end or date.today().isoformat(),
            "size": min(max(int(size), 1), 20),
        })

    def risk_indicators(self, company: str, as_of: str = "") -> Dict[str, Any]:
        scope = as_of or "最新交易日"
        return self.client.call("stock", "get_risk_indicators", {
            "query": "{0}{1}的波动率、Beta、最大回撤和夏普比率".format(company, scope),
        })

    def macro_data(self, query: str) -> Dict[str, Any]:
        return self.client.call("edb", "get_edb_data", {"query": query})

    def market_overview(self) -> Dict[str, Any]:
        return self.client.call("index", "index_highfreq_quotes", {
            "symbols": "上证指数,深证成指,创业板指",
            "indicators": "最新价,涨跌幅,成交额,上涨家数,下跌家数,涨停家数,跌停家数",
            "data_mode": "real_time",
        })

    def sector_overview(self) -> Dict[str, Any]:
        sectors = (
            "农林牧渔、基础化工、钢铁、有色金属、电子、家用电器、食品饮料、纺织服饰、"
            "轻工制造、医药生物、公用事业、交通运输、房地产、商贸零售、社会服务、综合、"
            "建筑材料、建筑装饰、电力设备、国防军工、计算机、传媒、通信、银行、非银金融、"
            "汽车、机械设备、煤炭、石油石化、环保、美容护理"
        )
        return self.client.call("index", "index_data", {
            "query": "申万一级行业{0}在最新交易日的涨跌幅".format(sectors),
        })

    def market_scan(self) -> Dict[str, Any]:
        """Return presentation-ready index rows and a bounded sector summary."""
        indices = _table_records(self.market_overview())
        sector_payload = self.sector_overview()
        sector_rows = []
        for row in _markdown_records(_payload_answer(sector_payload)):
            value = as_float(row.get("涨跌幅（单位：%）") or row.get("涨跌幅"))
            name = row.get("证券简称") or row.get("行业") or ""
            if name and value is not None:
                sector_rows.append({"name": name, "pct_chg": value})
        sector_rows.sort(key=lambda row: row["pct_chg"], reverse=True)
        return {
            "provider": "同花顺 iFinD",
            "indices": indices,
            "sectors": sector_rows,
        }


class MarketDataGateway:
    """iFinD first, public quote sites as a per-symbol fallback."""

    def __init__(
        self, *, ifind: Optional[IfindDataService] = None,
        fallback: Optional[FreeMarketDataGateway] = None,
        prefer_ifind: Optional[bool] = None,
    ) -> None:
        self.ifind = ifind if ifind is not None else IfindDataService.from_environment()
        self.fallback = fallback or FreeMarketDataGateway()
        if prefer_ifind is None:
            priority = (os.environ.get("SA_IFIND_MARKET_PRIORITY") or "free").strip().lower()
            prefer_ifind = priority in {"ifind", "prefer", "primary"}
        self.prefer_ifind = bool(prefer_ifind)

    def snapshots(self, codes: Iterable[str], minimum_date: str = "") -> MarketFetch:
        targets = _targets(codes)
        chosen: Dict[str, Dict[str, Any]] = {}
        providers: List[str] = []
        errors: List[str] = []
        free_fetch = lambda codes: self.fallback.snapshots(codes, minimum_date=minimum_date)
        lanes = []
        if self.prefer_ifind and self.ifind:
            lanes.append(lambda codes: self.ifind.stock_snapshots(codes))
        lanes.append(free_fetch)
        if not self.prefer_ifind and self.ifind:
            lanes.append(lambda codes: self.ifind.stock_snapshots(codes))
        for fetch in lanes:
            missing = [code for code in targets if code not in chosen]
            if not missing:
                break
            try:
                fetched = fetch(missing)
            except Exception as exc:
                errors.append(type(exc).__name__)
                continue
            errors.extend(fetched.errors)
            accepted = False
            for row in fetched.rows:
                if minimum_date and (row.get("date") or "") < minimum_date:
                    continue
                code = row.get("code") or ""
                if code in missing:
                    chosen[code] = row
                    accepted = True
            if accepted:
                providers.extend(name for name in fetched.providers if name not in providers)
        return MarketFetch(
            rows=[chosen[code] for code in targets if code in chosen], providers=providers,
            errors=errors, missing=[code for code in targets if code not in chosen],
        )

    def daily_bars(self, code: str, limit: int = 250) -> MarketFetch:
        # The iFinD high-frequency endpoint explicitly excludes historical data.
        # Existing Tencent/Eastmoney qfq daily bars remain the history provider.
        return self.fallback.daily_bars(code, limit=limit)


def research_source(company: str, ticker: str = "", period: str = "") -> Dict[str, Any]:
    """Fetch an auditable structured-financial cross-check for company research."""
    service = IfindDataService.from_environment()
    if not service:
        return {}
    payload = service.financials(company or ticker, period=period)
    answer = _payload_answer(payload)
    if not answer:
        return {}
    import hashlib
    body = "# iFinD 结构化财务指标（交叉校验）\n\n{0}".format(answer)
    identity = ticker or company
    return {
        "ok": True,
        "url": "https://mcp.51ifind.com/#/stock/{0}".format(identity),
        "canonical_url": "https://mcp.51ifind.com/#/stock/{0}".format(identity),
        "title": "iFinD 结构化财务指标 · {0}".format(company or ticker),
        "publisher": "同花顺 iFinD", "published_at": "", "available_at": "",
        "text": body, "content_type": "text/markdown",
        "content_hash": hashlib.sha256(body.encode("utf-8")).hexdigest(),
        "source_type": "STRUCTURED_FINANCIAL_DATA", "tier": 3,
        "source_skill": "ifind-finance-data", "source_label": "iFinD 财务交叉校验",
        "evidence_role": "结构化财务数据交叉校验，不替代公告原文",
        "origin_family": "ifind:{0}".format(identity),
    }


def research_news_sources(
    queries: Iterable[str], *, time_start: str = "", time_end: str = "",
    size: int = 8, service: Optional[IfindDataService] = None,
) -> List[Dict[str, Any]]:
    """Return iFinD semantic news excerpts as auditable research sources.

    Search engines only give us URLs and many Chinese finance pages then reject
    a plain HTTP reader or require JavaScript.  iFinD already returns the
    relevant paragraph plus its original URL and date, so keep that paragraph
    as a clearly labelled *vendor excerpt*.  It is useful evidence/lead, but it
    is never presented as the complete article or as an official filing.
    """
    client = service if service is not None else IfindDataService.from_environment()
    if client is None:
        return []
    start = time_start or "2025-01-01"
    end = time_end or date.today().isoformat()
    result: List[Dict[str, Any]] = []
    seen = set()
    for query in [str(item or "").strip() for item in queries if str(item or "").strip()]:
        payload = client.news(query, time_start=start, time_end=end, size=size)
        for row in _news_records(payload):
            title = str(row.get("资讯标题") or row.get("标题") or "iFinD 资讯片段").strip()
            excerpt = str(row.get("资讯内容") or row.get("内容") or row.get("摘要") or "").strip()
            url = str(row.get("URL") or row.get("url") or "").strip()
            published = str(row.get("日期") or row.get("时间") or "").strip()
            identity = url or (title, published)
            if identity in seen or len(excerpt) < 40:
                continue
            seen.add(identity)
            body = (
                "# iFinD 新闻语义检索片段\n\n"
                "检索问题：{0}\n\n标题：{1}\n日期：{2}\n\n{3}\n\n"
                "说明：这是 iFinD 返回的相关资讯段落，不等同于网页全文或官方披露。"
            ).format(query, title, published or "未标注", excerpt)
            digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
            source_url = url or "https://mcp.51ifind.com/#/news/{0}".format(digest[:16])
            result.append({
                "ok": True,
                "url": source_url,
                "canonical_url": source_url,
                "title": title,
                "publisher": "同花顺 iFinD",
                "published_at": published,
                "available_at": published,
                "text": body,
                "content_type": "text/markdown",
                "content_hash": digest,
                "source_type": "DATA_VENDOR_NEWS_EXCERPT",
                "tier": 3,
                "source_skill": "ifind-finance-data",
                "source_label": "iFinD 行业资讯语义片段",
                "evidence_role": "变化、预期和争议线索；关键结论仍需原始披露交叉验证",
                "origin_family": "ifind-news:{0}".format(digest[:16]),
                "query": query,
            })
    return result


def _unwrap_tool_content(body: Any) -> Dict[str, Any]:
    if not isinstance(body, dict):
        raise IfindError("iFinD MCP 返回格式异常")
    result = body.get("result") or {}
    content = result.get("content") or []
    for item in content:
        if not isinstance(item, dict) or item.get("type") != "text":
            continue
        text = item.get("text") or ""
        if not text:
            continue
        try:
            decoded = json.loads(text)
        except (ValueError, TypeError):
            return {"answer": str(text)}
        if isinstance(decoded, dict):
            return decoded
    if result.get("isError"):
        raise IfindError("iFinD 工具返回错误")
    return result if isinstance(result, dict) else {}


def _table_records(payload: Mapping[str, Any]) -> List[Dict[str, Any]]:
    data = payload.get("data") if isinstance(payload, Mapping) else None
    tables = data.get("tables") if isinstance(data, Mapping) else None
    if not isinstance(tables, list):
        return []
    # iFinD currently returns a single table as ``[headers, row, ...]``.  Some
    # tools and fixtures wrap multiple tables as ``[[headers, row, ...], ...]``.
    if tables and isinstance(tables[0], list) and (
        not tables[0] or not isinstance(tables[0][0], list)
    ):
        tables = [tables]
    records: List[Dict[str, Any]] = []
    for table in tables:
        if not isinstance(table, list) or len(table) < 2 or not isinstance(table[0], list):
            continue
        headers = [str(value or "") for value in table[0]]
        for values in table[1:]:
            if isinstance(values, list):
                records.append({key: values[index] if index < len(values) else None for index, key in enumerate(headers)})
    return records


def _snapshot_row(record: Mapping[str, Any]) -> Dict[str, Any]:
    code = normalize_code(record.get("证券代码") or record.get("代码") or record.get("symbol"))
    close = as_float(record.get("最新价") or record.get("最新成交价"))
    stamp = str(record.get("time") or record.get("时间") or "")
    day = to_iso(stamp[:10]) or date.today().isoformat()
    if not is_valid_code(code) or close is None or close <= 0:
        return {}
    return {
        "code": code, "date": day,
        "open": as_float(record.get("开盘价")) or close,
        "high": as_float(record.get("最高价")) or close,
        "low": as_float(record.get("最低价")) or close,
        "close": close, "volume": as_float(record.get("成交量")),
        "pct_chg": as_float(record.get("涨跌幅")), "_provider": "ifind",
    }


def _payload_answer(payload: Mapping[str, Any]) -> str:
    data = payload.get("data") if isinstance(payload, Mapping) else None
    if isinstance(data, Mapping):
        answer = data.get("answer") or data.get("text") or data.get("data")
        if answer:
            return str(answer)
    answer = payload.get("answer") if isinstance(payload, Mapping) else ""
    return str(answer or "")


def _news_records(payload: Mapping[str, Any]) -> List[Dict[str, Any]]:
    raw = _payload_answer(payload).strip()
    if not raw:
        return []
    try:
        decoded = json.loads(raw)
    except (ValueError, TypeError):
        return []
    if not isinstance(decoded, list):
        return []
    return [row for row in decoded if isinstance(row, dict) and "备注" not in row]


def _markdown_records(text: str) -> List[Dict[str, str]]:
    rows = [line.strip() for line in (text or "").splitlines() if line.strip().startswith("|")]
    if len(rows) < 3:
        return []
    headers = [cell.strip() for cell in rows[0].strip("|").split("|")]
    result = []
    for line in rows[2:]:
        values = [cell.strip() for cell in line.strip("|").split("|")]
        if values and not all(set(value) <= {"-", ":"} for value in values if value):
            result.append({key: values[index] if index < len(values) else "" for index, key in enumerate(headers)})
    return result


def _targets(codes: Iterable[str]) -> List[str]:
    result: List[str] = []
    for value in codes:
        code = normalize_code(value)
        if is_valid_code(code) and code not in result:
            result.append(code)
    return result


__all__ = [
    "IfindConfig", "IfindDataService", "IfindError", "IfindMcpClient",
    "MarketDataGateway", "research_source",
]
