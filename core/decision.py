"""Decision 一等公民：Expectation / Plan / Execution / Outcome。

产品中心不是股票也不是行情，是这一条决策记录。
流水与预测台账是输入；本模块把它们收成可复盘的对象。
"""
from __future__ import annotations

import csv
import re
from dataclasses import asdict, dataclass, fields
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import yaml

from core.config import CONFIG_DIR, TRADING_DIR
from core.symbols import normalize_code

DECISION_YAML = CONFIG_DIR / "decision.yaml"
DECISIONS_CSV = TRADING_DIR / "交易记录" / "决策台账.csv"
TRADES_CSV = TRADING_DIR / "交易记录" / "交易流水.csv"
PREDICTIONS_CSV = TRADING_DIR / "预测台账.csv"

_E_TYPE = re.compile(r"^E[1-7](?:\+E[1-7])?$", re.I)


@dataclass
class Decision:
    id: str = ""
    date: str = ""
    code: str = ""
    name: str = ""
    side: str = ""
    thesis: str = ""
    expectation: str = ""
    plan_entry: str = ""
    plan_stop: str = ""
    plan_size: str = ""
    planned: str = ""
    earning_type: str = ""
    invalidation: str = ""
    holding_period: str = ""
    market_context: str = ""
    evidence: str = ""
    trade_ids: str = ""
    prediction_ids: str = ""
    actual_summary: str = ""
    outcome: str = ""
    error_type: str = ""
    tags: str = ""
    emotion: str = ""
    status: str = "draft"
    reviewed_at: str = ""
    note: str = ""

    def as_dict(self) -> Dict[str, str]:
        return {key: "" if value is None else str(value) for key, value in asdict(self).items()}


def load_config(path: Path = DECISION_YAML) -> Dict[str, Any]:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def columns(cfg: Optional[Dict[str, Any]] = None) -> List[str]:
    data = cfg if cfg is not None else load_config()
    cols = data.get("columns") or [f.name for f in fields(Decision)]
    return list(cols)


def make_id(day: str, code: str, seq: int = 1) -> str:
    """D-YYYYMMDD-代码-序号。"""
    compact = (day or "").replace("-", "")[:8]
    norm = normalize_code(code) or "000000"
    return "D-{0}-{1}-{2:02d}".format(compact, norm, max(1, seq))


def _blank(value: Any) -> bool:
    text = str(value or "").strip()
    return text == "" or text in {"待复盘", "nan", "None", "-"}


def missing_required(decision: Decision, cfg: Optional[Dict[str, Any]] = None) -> List[str]:
    data = cfg if cfg is not None else load_config()
    required = data.get("required_for_reviewed") or []
    payload = decision.as_dict()
    return [key for key in required if _blank(payload.get(key))]


def completeness(decision: Decision, cfg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    data = cfg if cfg is not None else load_config()
    required = list(data.get("required_for_reviewed") or [])
    miss = missing_required(decision, data)
    filled = len(required) - len(miss)
    rate = round(filled / len(required) * 100, 1) if required else 100.0
    return {
        "required": required,
        "missing": miss,
        "filled": filled,
        "total": len(required),
        "rate": rate,
        "ready_for_reviewed": len(miss) == 0,
    }


def infer_status(decision: Decision, cfg: Optional[Dict[str, Any]] = None) -> str:
    if decision.status == "reviewed" and completeness(decision, cfg)["ready_for_reviewed"]:
        return "reviewed"
    if not _blank(decision.expectation) or not _blank(decision.thesis):
        if completeness(decision, cfg)["ready_for_reviewed"]:
            return "reviewed"
        return "open"
    return "draft"


def _read_csv_dicts(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [{k: (v or "").strip() for k, v in row.items()} for row in csv.DictReader(handle)]


def load_decisions(path: Path = DECISIONS_CSV) -> List[Decision]:
    cols = set(columns())
    out: List[Decision] = []
    for row in _read_csv_dicts(path):
        payload = {key: row.get(key, "") for key in cols}
        out.append(Decision(**payload))  # type: ignore[arg-type]
    return out


def write_decisions(rows: Sequence[Decision], path: Path = DECISIONS_CSV) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    cols = columns()
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=cols, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.as_dict().get(key, "") for key in cols})
    return path


def write_template(path: Path = DECISIONS_CSV) -> Path:
    """只写表头，便于空仓安装。"""
    return write_decisions([], path)


def _trade_id(row: Dict[str, str], index: int) -> str:
    day = (row.get("日期") or "")[:10]
    code = normalize_code(row.get("代码"))
    time = row.get("时间") or ""
    side = row.get("方向") or ""
    return "T-{0}-{1}-{2}-{3}".format(day.replace("-", ""), code, time.replace(":", ""), index)


def _is_buy(side: str) -> bool:
    return "买" in (side or "")


def draft_from_trades(
    trades_path: Path = TRADES_CSV,
    existing: Optional[Sequence[Decision]] = None,
) -> List[Decision]:
    """从买入/加仓流水投影 draft Decision；不覆盖已有同 trade_ids 的人工字段。"""
    trades = _read_csv_dicts(trades_path)
    by_trade: Dict[str, Decision] = {}
    for item in existing or []:
        for tid in (item.trade_ids or "").split(","):
            tid = tid.strip()
            if tid:
                by_trade[tid] = item

    seq_by_day_code: Dict[Tuple[str, str], int] = {}
    drafts: List[Decision] = []
    seen_ids = {item.id for item in (existing or []) if item.id}

    for index, row in enumerate(trades, start=1):
        side = row.get("方向") or ""
        if not _is_buy(side):
            continue
        day = (row.get("日期") or "")[:10]
        code = normalize_code(row.get("代码"))
        if not day or not code:
            continue
        tid = _trade_id(row, index)
        if tid in by_trade:
            continue

        key = (day, code)
        seq_by_day_code[key] = seq_by_day_code.get(key, 0) + 1
        decision_id = make_id(day, code, seq_by_day_code[key])
        while decision_id in seen_ids:
            seq_by_day_code[key] += 1
            decision_id = make_id(day, code, seq_by_day_code[key])
        seen_ids.add(decision_id)

        price = row.get("价格") or ""
        qty = row.get("数量") or ""
        amount = row.get("金额") or ""
        reason = row.get("决策理由") or ""
        planned = row.get("计划内?") or row.get("计划内") or ""
        earning = row.get("赚钱类型") or ""
        emotion = row.get("情绪分1-5") or row.get("情绪分") or ""
        name = row.get("名称") or ""
        time = row.get("时间") or ""

        actual = "{0} {1} @ {2} × {3}".format(time, side, price, qty).strip()
        if amount:
            actual = "{0} 金额 {1}".format(actual, amount)

        decision = Decision(
            id=decision_id,
            date=day,
            code=code,
            name=name,
            side=side,
            thesis=reason if reason and "截图导入" not in reason else "",
            expectation="",
            plan_entry="",
            plan_stop="",
            plan_size=amount or qty,
            planned=planned if planned else "待复盘",
            earning_type=earning.upper() if _E_TYPE.match(earning or "") else earning,
            invalidation="",
            holding_period="",
            market_context="",
            evidence="",
            trade_ids=tid,
            prediction_ids="",
            actual_summary=actual,
            outcome="",
            error_type="",
            tags="",
            emotion=emotion,
            status="draft",
            reviewed_at="",
            note="auto-draft from 交易流水",
        )
        decision.status = infer_status(decision)
        drafts.append(decision)

    return drafts


def merge_decisions(
    existing: Sequence[Decision],
    drafts: Sequence[Decision],
) -> List[Decision]:
    """按 id 合并：已有记录优先保留人工字段，draft 只补空槽。"""
    by_id: Dict[str, Decision] = {item.id: item for item in existing if item.id}
    order = [item.id for item in existing if item.id]

    for draft in drafts:
        if draft.id not in by_id:
            by_id[draft.id] = draft
            order.append(draft.id)
            continue
        current = by_id[draft.id]
        merged = Decision(**current.as_dict())  # type: ignore[arg-type]
        for key, value in draft.as_dict().items():
            if key == "id":
                continue
            if _blank(getattr(merged, key, "")) and not _blank(value):
                setattr(merged, key, value)
        merged.status = infer_status(merged)
        by_id[draft.id] = merged

    return [by_id[i] for i in order]


def link_predictions(
    decisions: Sequence[Decision],
    predictions_path: Path = PREDICTIONS_CSV,
) -> List[Decision]:
    """按日期+关联标的弱关联预测台账 ID（不覆盖已有 prediction_ids）。"""
    preds = _read_csv_dicts(predictions_path)
    if not preds:
        return list(decisions)

    out: List[Decision] = []
    for item in decisions:
        if not _blank(item.prediction_ids):
            out.append(item)
            continue
        hits: List[str] = []
        for pred in preds:
            pred_day = (pred.get("日期") or "")[:10]
            if pred_day and pred_day != item.date:
                continue
            related = pred.get("关联标的") or ""
            if item.code and item.code in related.replace(".", ""):
                hits.append(pred.get("ID") or "")
            elif item.name and item.name in related:
                hits.append(pred.get("ID") or "")
        if hits:
            updated = Decision(**item.as_dict())  # type: ignore[arg-type]
            updated.prediction_ids = ",".join(h for h in hits if h)
            out.append(updated)
        else:
            out.append(item)
    return out


def summarize(decisions: Sequence[Decision], cfg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    data = cfg if cfg is not None else load_config()
    status_counts: Dict[str, int] = {}
    error_counts: Dict[str, int] = {}
    ready = 0
    rates: List[float] = []
    for item in decisions:
        status_counts[item.status] = status_counts.get(item.status, 0) + 1
        if item.error_type:
            error_counts[item.error_type] = error_counts.get(item.error_type, 0) + 1
        comp = completeness(item, data)
        rates.append(comp["rate"])
        if comp["ready_for_reviewed"]:
            ready += 1
    avg = round(sum(rates) / len(rates), 1) if rates else 0.0
    return {
        "total": len(decisions),
        "ready_for_reviewed": ready,
        "avg_completeness": avg,
        "by_status": status_counts,
        "by_error_type": error_counts,
        "path": str(DECISIONS_CSV),
    }


def sync(
    trades_path: Path = TRADES_CSV,
    decisions_path: Path = DECISIONS_CSV,
    predictions_path: Path = PREDICTIONS_CSV,
    write: bool = True,
) -> Dict[str, Any]:
    """流水 → 决策台账投影。默认写回 CSV。"""
    existing = load_decisions(decisions_path)
    drafts = draft_from_trades(trades_path, existing=existing)
    merged = merge_decisions(existing, drafts)
    merged = link_predictions(merged, predictions_path)
    for item in merged:
        item.status = infer_status(item)
    if write:
        if not decisions_path.exists():
            write_template(decisions_path)
        write_decisions(merged, decisions_path)
    return {
        "ok": True,
        "drafted": len(drafts),
        "total": len(merged),
        "summary": summarize(merged),
        "written": write,
        "path": str(decisions_path),
    }


def decisions_to_store_rows(decisions: Iterable[Decision]) -> List[Dict[str, Any]]:
    """转成 store.upsert('decision', ...) 可用的行。"""
    return [item.as_dict() for item in decisions]
