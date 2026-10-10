"""Durable, human-readable company research memory.

SQLite remains the structured truth store.  These Markdown files make the
same research inspectable, portable and reusable by future agent turns.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from core.research import sessions
from core.research.netread import canonical_url
from core.research.store import now_iso
from core.store import Store


def research_delta(previous_claims: list, claims: list, previous_sources: list, sources: list) -> dict:
    old_claims = {_claim_key(row): row for row in previous_claims if _claim_key(row)}
    old_sources = {_source_key(row): row for row in previous_sources if _source_key(row)}
    added_sources = [row for row in sources if _source_key(row) not in old_sources]
    old_urls = {row.get("url") or "": row for row in previous_sources if row.get("url")}
    updated_sources = [
        row for row in added_sources
        if row.get("url") in old_urls
        and row.get("content_hash")
        and row.get("content_hash") != old_urls[row.get("url")].get("content_hash")
    ]
    new_source_ids = {row.get("local_id") for row in added_sources if row.get("local_id")}
    changed_source_ids = new_source_ids | {row.get("local_id") for row in updated_sources if row.get("local_id")}
    novel_claims = [row for row in claims if _claim_key(row) not in old_claims]
    # Re-extracting another sentence from an unchanged old document is useful
    # reclassification, but it is not a new fact and must not drive the change log.
    added_claims = [row for row in novel_claims if row.get("source_id") in changed_source_ids]
    reclassified_claims = [row for row in novel_claims if row.get("source_id") not in changed_source_ids]
    return {
        "first_research": not bool(previous_claims or previous_sources),
        "added_claim_count": len(added_claims),
        "added_source_count": len(added_sources),
        "updated_source_count": len(updated_sources),
        "reclassified_claim_count": len(reclassified_claims),
        "retained_claim_count": sum(1 for row in claims if _claim_key(row) in old_claims),
        "added_claims": [
            {"id": row.get("local_id") or "", "text": row.get("text") or row.get("evidence_text") or ""}
            for row in added_claims[:8]
        ],
        "added_sources": [
            {
                "id": row.get("local_id") or "", "title": row.get("title") or "",
                "url": row.get("url") or "", "published_at": row.get("published_at") or "",
            }
            for row in added_sources[:8]
        ],
        "reclassified_claims": [
            {"id": row.get("local_id") or "", "text": row.get("text") or row.get("evidence_text") or ""}
            for row in reclassified_claims[:8]
        ],
    }


def company_directory(store: Store, name: str, ticker: str = "") -> Path:
    label = _safe("{0}_{1}".format(ticker or "UNKNOWN", name or "company"))
    return store.path.parent / "research" / "companies" / label


def company_memory_path(store: Store, name: str, ticker: str = "") -> Path:
    return company_directory(store, name, ticker) / "research.md"


def save_company_memory(
    store: Store, *, name: str, ticker: str, summary: dict, delta: dict,
    search_calls: int = 0, reader_calls: int = 0,
) -> dict:
    directory = company_directory(store, name, ticker)
    source_paths = _save_source_snapshots(store, directory, summary.get("sources") or [])
    target = directory / "research.md"
    body = _render(
        name=name, ticker=ticker, summary=summary, delta=delta,
        search_calls=search_calls, reader_calls=reader_calls, source_paths=source_paths,
    )
    _atomic_write(target, body)
    return {"path": str(target), "source_paths": source_paths, "saved_at": now_iso()}


def lifecycle_message(name: str, memory: dict, delta: dict, search_calls: int, reader_calls: int, network: str) -> str:
    if delta.get("first_research"):
        opening = "我先为{0}建立了长期研究档案。".format(name or "这家公司")
    else:
        since = (memory.get("previous_live_checked_at") or memory.get("previous_checked_at") or "上次研究")[:10]
        opening = "我先加载了{0}的已有研究，并检查了 {1} 之后的新资料。".format(name or "这家公司", since)
    if network != "live":
        checked = "这轮没有开启联网，只复用了已有证据和本地资料。"
    else:
        checked = "本轮搜索 {0} 次、尝试打开 {1} 份来源。".format(search_calls, reader_calls)
    added = "新增 {0} 份来源、{1} 条可引用证据。".format(
        delta.get("added_source_count") or 0, delta.get("added_claim_count") or 0,
    )
    if not delta.get("first_research") and not delta.get("added_source_count") and not delta.get("added_claim_count"):
        added = "暂未发现足以写入研究档案的新证据，原判断保持不变。"
    return opening + checked + added + "研究正文和已读来源已经保存到本地。"


def _save_source_snapshots(store: Store, directory: Path, sources: list) -> list:
    saved = []
    source_dir = directory / "sources"
    for row in sources:
        url = row.get("url") or ""
        if not url.startswith(("http://", "https://")):
            continue
        cached = sessions.cache_get(store, canonical_url(url))
        body = (cached or {}).get("text") or ""
        if not body:
            continue
        digest = (row.get("content_hash") or hashlib.sha256(body.encode("utf-8")).hexdigest())[:12]
        title = _safe((row.get("title") or row.get("local_id") or "source")[:48])
        target = source_dir / "{0}_{1}.md".format(digest, title)
        header = "\n".join([
            "# {0}".format(row.get("title") or "Research source"),
            "",
            "- URL: {0}".format(url),
            "- Published: {0}".format(row.get("published_at") or "UNKNOWN"),
            "- Captured: {0}".format((cached or {}).get("retrieved_at") or now_iso()),
            "- Content hash: {0}".format(row.get("content_hash") or digest),
            "",
            "## 正文快照",
            "",
            body,
            "",
        ])
        if not target.exists():
            _atomic_write(target, header)
        saved.append(str(target))
    return saved


def _render(name, ticker, summary, delta, search_calls, reader_calls, source_paths) -> str:
    memory = summary.get("research_memory") or {}
    claims = summary.get("claims") or []
    sources = summary.get("sources") or []
    questions = summary.get("open_questions") or []
    lines = [
        "# {0}{1}研究档案".format(name or "公司", "（{0}）".format(ticker) if ticker else ""),
        "",
        "> 由 Investment Agent 自动维护。事实必须能回到来源；观点会随新证据更新。",
        "",
        "- 最后研究：{0}".format(memory.get("last_checked_at") or now_iso()),
        "- 最后联网检查：{0}".format(memory.get("last_live_checked_at") or "未联网"),
        "- 最近来源日期：{0}".format(memory.get("latest_source_date") or "UNKNOWN"),
        "- 累计研究轮次：{0}".format(memory.get("run_count") or 1),
        "- 本轮工具：搜索 {0} 次，阅读尝试 {1} 次".format(search_calls, reader_calls),
        "",
        "## 当前研究结论",
        "",
        summary.get("draft_thesis") or "尚未形成可引用结论。",
        "",
        "## 本轮相对上次变化",
        "",
    ]
    if delta.get("first_research"):
        lines.append("- 首次建立研究基线。")
    elif delta.get("added_claims") or delta.get("added_sources"):
        lines.append("- 新增来源：{0}".format(delta.get("added_source_count") or 0))
        lines.append("- 新增证据：{0}".format(delta.get("added_claim_count") or 0))
        for row in delta.get("added_claims") or []:
            lines.append("  - {0}".format(row.get("text") or ""))
    else:
        lines.append("- 没有发现足以改变研究档案的新证据。")
    dossier = summary.get("company_dossier") or {}
    if dossier:
        lines.extend(_render_dossier_sections(dossier))
    else:
        lines.extend(["", "## 已核对事实", ""])
        for row in claims:
            lines.append("- {0}".format(row.get("text") or row.get("evidence_text") or ""))
    lines.extend(["", "## 来源", ""])
    for row in sources:
        title = row.get("title") or row.get("url") or "来源"
        url = row.get("url") or ""
        published = row.get("published_at") or "UNKNOWN"
        lines.append("- [{0}] [{1}]({2}) · {3}".format(row.get("local_id") or "S?", title, url, published))
    lines.extend(["", "## 未决问题", ""])
    lines.extend("- {0}".format(item) for item in questions) if questions else lines.append("- 暂无。")
    lines.extend(["", "## 已保存来源正文", ""])
    lines.extend("- `{0}`".format(path) for path in source_paths) if source_paths else lines.append("- 本轮没有可保存的网页正文。")
    lines.append("")
    return "\n".join(lines)


def _render_dossier_sections(dossier: dict) -> list:
    basics = dossier.get("company_basics") or {}
    thesis = dossier.get("core_thesis") or {}
    expectations = dossier.get("expectations") or {}
    market = dossier.get("price_and_expectations") or {}
    changes = dossier.get("changes") or {}
    risk = dossier.get("risks_and_invalidation") or {}
    lines = ["", "## 公司基本盘", ""]
    lines.extend(_items("卖什么、卖给谁", basics.get("products_and_customers")))
    lines.extend(_items("业务分部", basics.get("segments")))
    lines.extend(_items("收入与利润来源", basics.get("revenue_and_profit_sources")))
    lines.extend(["", "## 财务质量", ""])
    lines.append("- {0}".format((dossier.get("financial_quality") or {}).get("assessment") or "UNKNOWN"))
    lines.extend(["", "## 核心壁垒", ""])
    lines.extend(_bullet_items((dossier.get("moat") or {}).get("evidence")) or ["- " + (dossier.get("moat") or {}).get("assessment", "UNKNOWN")])
    lines.extend(["", "## 行业位置与上下游暴露", ""])
    lines.extend(_bullet_items((dossier.get("industry_position") or {}).get("evidence")) or ["- UNKNOWN"])
    lines.extend(_items("客户与供应商暴露", dossier.get("customer_supplier_exposure")))
    lines.extend(_items("资本配置", dossier.get("capital_allocation")))
    lines.extend(["", "## 当前核心判断", ""])
    lines.extend(_items("核心增长变量", thesis.get("growth_drivers")))
    lines.extend(_items("利润驱动", thesis.get("profit_drivers")))
    lines.extend(_items("判断成立的条件", thesis.get("conditions")))
    lines.extend(["", "## 市场预期", ""])
    lines.extend(_items("公司指引", expectations.get("management_guidance")))
    lines.extend(_items("一致预期", expectations.get("consensus")))
    lines.extend(_items("卖方预测", expectations.get("sell_side")))
    lines.extend(_items("市场叙事", expectations.get("market_narrative")))
    timeline = expectations.get("revision_timeline") or []
    if timeline:
        lines.extend(["", "### 预期修订时间线", ""])
        for row in timeline:
            state = "当前可见最新" if row.get("latest_for_institution") else "历史版本"
            lines.append("- {0} · {1} · {2}：{3}".format(
                row.get("date") or "日期待确认",
                row.get("institution") or "机构待确认",
                state,
                row.get("statement") or "",
            ))
    lines.extend(["", "## 股价与预期", ""])
    lines.append("- 行情：{0}（{1}）".format(market.get("last_price", "UNKNOWN"), market.get("price_date") or "UNKNOWN"))
    lines.append("- 股价隐含预期：{0}".format(market.get("price_implied_expectation") or "UNKNOWN"))
    lines.append("- 预期差：{0}".format(market.get("expectation_gap") or "UNKNOWN"))
    lines.extend(["", "## 变化日志", ""])
    lines.append("- {0}".format(changes.get("summary") or "UNKNOWN"))
    lines.extend(_bullet_items(changes.get("new_facts")))
    lines.extend(["", "## 风险与失效条件", ""])
    lines.extend(_bullet_items(risk.get("risks")) or ["- UNKNOWN"])
    lines.extend("- 失效：{0}".format(item) for item in (risk.get("invalidation") or []))
    lines.extend(["", "## 下一步监控指标", ""])
    lines.extend("- {0}".format(item) for item in (dossier.get("monitoring") or []))
    return lines


def _items(label: str, rows) -> list:
    values = _bullet_items(rows)
    return ["", "### {0}".format(label), ""] + (values or ["- UNKNOWN（尚无已核对证据）"])


def _bullet_items(rows) -> list:
    result = []
    for row in rows or []:
        value = row.get("text") if isinstance(row, dict) else str(row)
        number = row.get("source_number") if isinstance(row, dict) else None
        result.append("- {0}{1}".format(value, " [{0}]".format(number) if number else ""))
    return result


def _claim_key(row: dict) -> str:
    return re.sub(r"\s+", "", row.get("evidence_text") or row.get("text") or "")


def _source_key(row: dict) -> str:
    return "|".join([row.get("url") or "", row.get("content_hash") or ""])


def _safe(value: str) -> str:
    clean = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff._-]+", "_", value or "")
    return clean.strip("._-") or "research"


def _atomic_write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(body, encoding="utf-8")
    temporary.replace(path)
