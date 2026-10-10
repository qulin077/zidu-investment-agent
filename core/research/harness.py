"""LEGACY_QUICK_BRIEF

旧的股票池简报。主入口不再走这里。
兼容入口是 GET /api/research/quick-brief。
股票池在这条旧链上仍是简报范围，不是 Research Workspace 的许可门。

行研 Multi-Agent Harness。

火山市场洞察：一句话 → 意图理解 → 调度领域 Agent → 收集（粗筛+精筛）
→ 事件脉络/观点聚类/社会影响 → 报告。那是公关舆情。

这里用同一套调度骨架，换成二级投研对象：行业、公司、新闻。
Harness 是确定性 DAG（配置里写死名单），专家只准用白名单工具，
数字来自 SQLite / chains.yaml，不让模型编涨跌。
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import yaml

from core.chain_brief import brief, company_card, load_chain_defs, resolve
from core.config import CONFIG_DIR, DAILY_DIR
from core.store import STORE, Store

HARNESS_YAML = CONFIG_DIR / "research_harness.yaml"


def load_harness_config(path: Path = HARNESS_YAML) -> Dict[str, Any]:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _step(trace: List[Dict[str, Any]], name: str, fn: Callable[[], Dict[str, Any]]) -> Dict[str, Any]:
    started = time.monotonic()
    try:
        output = fn()
        ok = True
        error = ""
    except Exception as exc:  # noqa: BLE001
        output = {}
        ok = False
        error = "{0}: {1}".format(type(exc).__name__, exc)
    trace.append(
        {
            "agent": name,
            "ok": ok,
            "ms": int((time.monotonic() - started) * 1000),
            "error": error,
            "keys": sorted(output.keys()),
        }
    )
    if not ok:
        raise RuntimeError("{0} 失败：{1}".format(name, error))
    return output


def intent_expert(query: str, store: Store = STORE) -> Dict[str, Any]:
    """意图理解：只分类、抽实体、决定调度。不写结论。"""
    resolved = resolve(query, store=store)
    kind = resolved.get("kind") or "unknown"
    topic = {"chain": "industry", "company": "company", "news": "news"}.get(kind, "unknown")
    entities: List[str] = []
    if topic == "industry":
        entities = [resolved.get("id") or "", resolved.get("name") or ""]
    elif topic == "company":
        entities = [resolved.get("code") or "", resolved.get("name") or ""]
    elif topic == "news":
        for hit in resolved.get("hits") or []:
            entities.append(hit.get("id") or "")
    cfg = load_harness_config()
    dispatch = (cfg.get("dispatch") or {}).get(topic) or []
    return {
        "query": query,
        "topic": topic,
        "kind": kind,
        "entities": [item for item in entities if item],
        "dispatch": dispatch,
        "refuse": resolved.get("refuse") or "",
        "resolved": resolved,
    }


def collect_expert(intent: Dict[str, Any], store: Store = STORE) -> Dict[str, Any]:
    """数据收集：粗筛=必须在池/链内；精筛=关键词命中的新闻。"""
    resolved = intent.get("resolved") or {}
    topic = intent.get("topic")
    payload: Dict[str, Any] = {"topic": topic, "asof": ""}
    if topic == "unknown":
        payload["refuse"] = intent.get("refuse")
        return payload
    if topic == "company":
        payload["company"] = resolved
        payload["asof"] = resolved.get("asof") or ""
        homes = resolved.get("chains") or []
        payload["chains"] = []
        for home in homes:
            cid = home.get("chain")
            if cid:
                payload["chains"].append(brief(cid, store=store))
        if payload["chains"]:
            payload["asof"] = payload["chains"][0].get("asof") or payload["asof"]
    elif topic == "industry":
        payload["chains"] = [resolved]
        payload["asof"] = resolved.get("asof") or ""
    elif topic == "news":
        payload["news_hits"] = resolved.get("hits") or []
        payload["chains"] = []
        for hit in payload["news_hits"]:
            cid = hit.get("id")
            if cid:
                payload["chains"].append(brief(cid, store=store))
        payload["asof"] = (payload["chains"][0].get("asof") if payload["chains"] else "") or ""
        payload["refuse_generic"] = resolved.get("refuse_generic") or ""
    return payload


def industry_expert(collected: Dict[str, Any]) -> Dict[str, Any]:
    chains = collected.get("chains") or []
    rows = []
    for chain in chains:
        money = chain.get("money") or {}
        rows.append(
            {
                "id": chain.get("id"),
                "name": chain.get("name"),
                "thesis": chain.get("thesis"),
                "asof": chain.get("asof"),
                "money_layer": money.get("name"),
                "money_pct": money.get("avg_pct"),
                "switched": chain.get("switched"),
                "from_layer": (chain.get("prev_money") or {}).get("name"),
                "book_verdict": (chain.get("book") or {}).get("verdict"),
                "layers": [
                    {
                        "name": layer.get("name"),
                        "side": layer.get("side"),
                        "avg_pct": layer.get("avg_pct"),
                        "logic": layer.get("logic"),
                    }
                    for layer in (chain.get("layers") or [])
                ],
            }
        )
    return {"industry": rows}


def company_expert(collected: Dict[str, Any]) -> Dict[str, Any]:
    card = collected.get("company") or {}
    if not card.get("found"):
        return {"company": card}
    return {
        "company": {
            "code": card.get("code"),
            "name": card.get("name"),
            "sector": card.get("sector"),
            "role": card.get("role"),
            "close": card.get("close"),
            "pct_chg": card.get("pct_chg"),
            "valuation_zone": card.get("valuation_zone"),
            "earning_type": card.get("earning_type"),
            "ma5": card.get("ma5"),
            "note": card.get("note"),
            "chains": card.get("chains"),
            "in_book": card.get("in_book"),
            "missing": card.get("missing") or [],
            "buy_blocked_reason": card.get("buy_blocked_reason"),
            "asof": collected.get("asof") or card.get("asof"),
        }
    }


def news_expert(collected: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "news": {
            "hits": collected.get("news_hits") or [],
            "refuse_generic": collected.get("refuse_generic") or "",
        }
    }


def analyze_expert(intent: Dict[str, Any], parts: Dict[str, Any]) -> Dict[str, Any]:
    topic = intent.get("topic")
    industry = (parts.get("industry") or {}).get("industry") or []
    company = (parts.get("company") or {}).get("company") or {}
    missing = list(company.get("missing") or [])
    leader = industry[0] if industry else {}
    if topic == "company" and company.get("name"):
        ma5 = (company.get("ma5") or {}).get("vs_ma5") or "MA5未知"
        draft = "T+1 {0} 是否仍{1}（asof {2}）".format(
            company.get("name"),
            (company.get("ma5") or {}).get("vs_ma5") or "MA5未知",
            leader.get("asof") or company.get("asof") or "",
        )
    elif topic == "news" and leader:
        draft = "T+1 {0} 资金是否仍在{1}".format(leader.get("name"), leader.get("money_layer"))
    elif leader:
        draft = "T+1 {0} 资金是否仍在{1}".format(leader.get("name"), leader.get("money_layer"))
    else:
        draft = ""
        missing.append("可证伪预测")
    return {
        "gaps": missing,
        "book_verdict": leader.get("book_verdict") or "",
        "prediction_draft": draft,
        "write_to_replay": bool(draft),
        "one_liner": _one_liner(topic, company, leader),
    }


def _one_liner(topic: str, company: Dict[str, Any], leader: Dict[str, Any]) -> str:
    if topic == "company" and company.get("name"):
        return "{0}：估值{1}，{2}，资金在{3}".format(
            company.get("name"),
            company.get("valuation_zone") or "未评",
            (company.get("ma5") or {}).get("vs_ma5") or "MA5未知",
            leader.get("money_layer") or "未知层",
        )
    if leader:
        switched = "，层级已切换" if leader.get("switched") else ""
        return "{0}今日资金在{1}{2}".format(leader.get("name"), leader.get("money_layer"), switched)
    return "无法形成观察句"


def risk_expert(intent: Dict[str, Any], collected: Dict[str, Any], analysis: Dict[str, Any]) -> Dict[str, Any]:
    flags: List[str] = []
    for chain in collected.get("chains") or []:
        book = chain.get("book") or {}
        if book.get("stale_warning"):
            flags.append("持仓快照过期 {0} 天".format(book.get("stale_days")))
        orphans = book.get("orphans") or []
        if orphans:
            flags.append("账本孤儿：" + "、".join(item.get("name") or item.get("code") for item in orphans))
    if analysis.get("gaps"):
        flags.append("缺栏：" + "、".join(analysis["gaps"]))
    if intent.get("topic") == "unknown":
        flags.append("意图无法落入股票池")
    return {
        "buy_allowed": False,
        "verdict": "观察" if intent.get("topic") != "unknown" else "拒绝",
        "flags": flags,
        "buy_blocked_reason": "行研房间不输出买入建议。缺栏或过期数据时只允许观察。",
    }


def report_expert(
    intent: Dict[str, Any],
    collected: Dict[str, Any],
    parts: Dict[str, Any],
    analysis: Dict[str, Any],
    risk: Dict[str, Any],
    write: bool = True,
) -> Dict[str, Any]:
    topic = intent.get("topic")
    asof = collected.get("asof") or ""
    title = {
        "company": (parts.get("company") or {}).get("company", {}).get("name") or intent.get("query"),
        "industry": ((parts.get("industry") or {}).get("industry") or [{}])[0].get("name") or intent.get("query"),
        "news": intent.get("query"),
        "unknown": intent.get("query"),
    }.get(topic, intent.get("query"))
    lines = [
        "# 行研简报 · {0}".format(title),
        "",
        "研究框架，非投资建议。Harness 调度：{0}。行情 asof {1}。".format(
            " → ".join(intent.get("dispatch") or []), asof or "—",
        ),
        "",
        "## 一句话",
        analysis.get("one_liner") or "",
        "",
        "## 意图",
        "- 主题：**{0}** · 实体：{1}".format(topic, "、".join(intent.get("entities") or []) or "无"),
        "",
    ]
    company = (parts.get("company") or {}).get("company") or {}
    if company.get("name"):
        lines.extend(
            [
                "## 公司六栏",
                "- 赚钱类型：{0}".format(company.get("earning_type")),
                "- 估值三区：{0}".format(company.get("valuation_zone")),
                "- 角色/叙事：{0} / {1}".format(company.get("sector"), company.get("role")),
                "- 技术：{0}".format((company.get("ma5") or {}).get("vs_ma5")),
                "- 失效：笔记未写失效则禁止当基本面仓",
                "- 账本：{0}".format("在持仓" if company.get("in_book") else "不在当前持仓"),
                "",
            ]
        )
    industry = (parts.get("industry") or {}).get("industry") or []
    if industry:
        lines.append("## 行业")
        for row in industry:
            lines.append(
                "- **{0}**：{1}。今日资金 **{2}**（{3}）。{4}".format(
                    row.get("name"),
                    row.get("thesis") or "",
                    row.get("money_layer") or "—",
                    "{0:+.2f}%".format(row["money_pct"]) if row.get("money_pct") is not None else "—",
                    "从 {0} 切来。".format(row.get("from_layer")) if row.get("switched") else "",
                )
            )
            for layer in row.get("layers") or []:
                avg = "—" if layer.get("avg_pct") is None else "{0:+.2f}%".format(layer["avg_pct"])
                lines.append("  - {0}（{1}）{2}：{3}".format(layer.get("name"), layer.get("side"), avg, layer.get("logic")))
        lines.append("")
    news = (parts.get("news") or {}).get("news") or {}
    if news.get("hits"):
        lines.append("## 新闻映射")
        lines.append(news.get("refuse_generic") or "只映射已定义链条。")
        for hit in news.get("hits") or []:
            lines.append("- {0} ← {1}".format(hit.get("name"), " / ".join(hit.get("matched") or [])))
        lines.append("")
    lines.extend(
        [
            "## 风控",
            "- 买入许可：**否**。{0}".format(risk.get("buy_blocked_reason")),
        ]
    )
    for flag in risk.get("flags") or []:
        lines.append("- {0}".format(flag))
    lines.extend(
        [
            "",
            "## 写入复盘",
            "- 写入复盘：{0}".format("是" if analysis.get("write_to_replay") else "否"),
            "- 预测草稿：{0}".format(analysis.get("prediction_draft") or "无"),
            "",
        ]
    )
    markdown = "\n".join(lines)
    path = ""
    if write and topic != "unknown":
        DAILY_DIR.mkdir(parents=True, exist_ok=True)
        slug = re.sub(r"[^\w\u4e00-\u9fff]+", "_", str(title or "research"))[:40]
        filename = "research_{0}_{1}_{2}.md".format(
            topic, asof or datetime.now().strftime("%Y-%m-%d"), slug
        )
        dest = DAILY_DIR / filename
        dest.write_text(markdown, encoding="utf-8")
        path = str(dest)
    return {"title": title, "markdown": markdown, "path": path, "asof": asof}


def run(query: str, store: Store = STORE, write: bool = True) -> Dict[str, Any]:
    """跑完整 DAG。unknown 在意图阶段停，不写假报告。"""
    trace: List[Dict[str, Any]] = []
    intent = _step(trace, "intent", lambda: intent_expert(query, store=store))
    packet: Dict[str, Any] = {
        "query": query,
        "topic": intent.get("topic"),
        "dispatch": intent.get("dispatch") or [],
        "trace": trace,
        "disclaimer": "研究框架，非投资建议。",
    }
    if intent.get("topic") == "unknown":
        packet["ok"] = False
        packet["refuse"] = intent.get("refuse")
        packet["stopped_at"] = "intent"
        return packet

    collected = _step(trace, "collect", lambda: collect_expert(intent, store=store))
    parts: Dict[str, Any] = {}
    for name in intent.get("dispatch") or []:
        if name in ("collect", "analyze", "risk", "report"):
            continue
        if name == "industry":
            parts["industry"] = _step(trace, "industry", lambda: industry_expert(collected))
        elif name == "company":
            parts["company"] = _step(trace, "company", lambda: company_expert(collected))
        elif name == "news":
            parts["news"] = _step(trace, "news", lambda: news_expert(collected))

    analysis = _step(trace, "analyze", lambda: analyze_expert(intent, parts))
    risk = _step(trace, "risk", lambda: risk_expert(intent, collected, analysis))
    report = _step(
        trace, "report", lambda: report_expert(intent, collected, parts, analysis, risk, write=write)
    )
    packet.update(
        {
            "ok": True,
            "asof": collected.get("asof"),
            "intent": {k: v for k, v in intent.items() if k != "resolved"},
            "analysis": analysis,
            "risk": risk,
            "report": report,
        }
    )
    return packet
