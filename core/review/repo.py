"""Review 域的数据访问层。

三条约束落在这里，其它模块不用重复实现：

1. Provenance —— 每行都带 created_at / effective_at / source / created_by / revision。
2. Append-only —— 改字段走 amend()，原值进 revision 表；状态转换进
   decision_transition 表。没有任何函数会静默丢掉旧值。
3. Decision 1:N Execution —— execution.decision_id 允许为空，历史流水只落
   execution，不生成假 Decision。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date as date_cls
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence

from core.review import lifecycle
from core.review.defs import threshold
from core.store import STORE, Store
from core.symbols import normalize_code

SOURCES = {"user", "system", "trade_import", "legacy_import", "agent"}
ORIGINS = {"EX_ANTE", "POST_HOC"}
SUBJECTIVE_CONTEXTS = {"available", "not_recorded", "unavailable"}


class ReviewError(Exception):
    """领域约束被破坏。CLI 捕获后打人话。"""


def _maybe_freeze_entry(decision_id: str, store: Store) -> None:
    try:
        from core.review import flags as _flags
        if not _flags.decision_context_enabled():
            return
        from core.context.store import freeze_entry
        freeze_entry(decision_id, store)
    except Exception:  # noqa: BLE001
        return


def _maybe_freeze_review(decision_id: str, store: Store) -> None:
    try:
        from core.review import flags as _flags
        if not _flags.decision_context_enabled():
            return
        from core.context.store import freeze_review
        freeze_review(decision_id, store)
    except Exception:  # noqa: BLE001
        return


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def today() -> str:
    return date_cls.today().isoformat()


def _prov(source: str, created_by: str, effective_at: str = "") -> Dict[str, Any]:
    if source not in SOURCES:
        raise ReviewError("未知 source：{0}。允许：{1}".format(source, sorted(SOURCES)))
    stamp = now()
    return {
        "created_at": stamp,
        "effective_at": effective_at or stamp,
        "source": source,
        "created_by": created_by,
        "revision": 1,
    }


def _insert(store: Store, table: str, row: Dict[str, Any]) -> None:
    cols = list(row.keys())
    sql = "INSERT INTO {0} ({1}) VALUES ({2})".format(
        table, ", ".join(cols), ", ".join("?" for _ in cols)
    )
    with store.connect() as conn:
        conn.execute(sql, tuple(row[c] for c in cols))


# ------------------------------------------------------------------- id 生成

_ID_SEQ = re.compile(r"-(\d+)$")


def _next_seq(store: Store, table: str, prefix: str) -> int:
    rows = store.query(
        "SELECT id FROM {0} WHERE id LIKE ? ORDER BY id".format(table), (prefix + "%",)
    )
    top = 0
    for row in rows:
        m = _ID_SEQ.search(str(row["id"]))
        if m:
            top = max(top, int(m.group(1)))
    return top + 1


def make_decision_id(day: str, code: str, store: Store = STORE) -> str:
    compact = (day or today()).replace("-", "")[:8]
    norm = normalize_code(code) or "000000"
    prefix = "D-{0}-{1}".format(compact, norm)
    return "{0}-{1:02d}".format(prefix, _next_seq(store, "decision", prefix + "-"))


def _child_id(store: Store, table: str, kind: str, decision_id: str) -> str:
    prefix = "{0}-{1}".format(kind, decision_id[2:] if decision_id.startswith("D-") else decision_id)
    return "{0}-{1:02d}".format(prefix, _next_seq(store, table, prefix + "-"))


# -------------------------------------------------------------------- 读取


def get_decision(decision_id: str, store: Store = STORE) -> Optional[Dict[str, Any]]:
    rows = store.query("SELECT * FROM decision WHERE id = ?", (decision_id,))
    return rows[0] if rows else None


def require_decision(decision_id: str, store: Store = STORE) -> Dict[str, Any]:
    row = get_decision(decision_id, store)
    if row is None:
        raise ReviewError("找不到 Decision：{0}".format(decision_id))
    return row


def list_decisions(
    status: str = "", code: str = "", limit: int = 50, store: Store = STORE
) -> List[Dict[str, Any]]:
    sql = "SELECT * FROM decision WHERE 1=1"
    params: List[Any] = []
    if status:
        sql += " AND status = ?"
        params.append(status)
    if code:
        sql += " AND code = ?"
        params.append(normalize_code(code) or code)
    sql += " ORDER BY opened_on DESC, id DESC LIMIT ?"
    params.append(limit)
    return store.query(sql, params)


def executions_on(day: str, store: Store = STORE) -> List[Dict[str, Any]]:
    return store.query(
        "SELECT * FROM execution WHERE executed_on = ? ORDER BY executed_at, id",
        (day,),
    )


def has_recorded_context(decision_id: str, store: Store = STORE) -> bool:
    """主观记录是否真实存在：thesis 或至少一版 plan。"""
    row = get_decision(decision_id, store)
    if row is None:
        return False
    if (row.get("thesis") or "").strip():
        return True
    return current_plan(decision_id, store) is not None


def executions_on(day: str, store: Store = STORE) -> List[Dict[str, Any]]:
    return store.query(
        "SELECT * FROM execution WHERE executed_on = ? ORDER BY executed_at, id",
        (day,),
    )


def has_recorded_context(decision_id: str, store: Store = STORE) -> bool:
    """主观记录是否真实存在：thesis 或至少一版 plan。"""
    row = get_decision(decision_id, store)
    if row is None:
        return False
    if (row.get("thesis") or "").strip():
        return True
    return current_plan(decision_id, store) is not None


def expectations(decision_id: str, store: Store = STORE) -> List[Dict[str, Any]]:
    return store.query(
        "SELECT * FROM expectation WHERE decision_id = ? ORDER BY id", (decision_id,)
    )


def plans(decision_id: str, store: Store = STORE) -> List[Dict[str, Any]]:
    return store.query(
        "SELECT * FROM plan WHERE decision_id = ? ORDER BY revision", (decision_id,)
    )


def current_plan(decision_id: str, store: Store = STORE) -> Optional[Dict[str, Any]]:
    """最新一版未被取代的 plan。"""
    rows = store.query(
        "SELECT * FROM plan WHERE decision_id = ? AND superseded_by = ''"
        " ORDER BY revision DESC LIMIT 1",
        (decision_id,),
    )
    return rows[0] if rows else None


def executions(decision_id: str, store: Store = STORE) -> List[Dict[str, Any]]:
    return store.query(
        "SELECT * FROM execution WHERE decision_id = ?"
        " ORDER BY executed_on, executed_at, id",
        (decision_id,),
    )


def orphan_executions(
    code: str = "", limit: int = 50, store: Store = STORE
) -> List[Dict[str, Any]]:
    """没挂 Decision 的 execution。历史流水导入后都在这里。"""
    sql = "SELECT * FROM execution WHERE decision_id IS NULL"
    params: List[Any] = []
    if code:
        sql += " AND code = ?"
        params.append(normalize_code(code) or code)
    sql += " ORDER BY executed_on DESC, executed_at DESC LIMIT ?"
    params.append(limit)
    return store.query(sql, params)


def get_outcome(decision_id: str, store: Store = STORE) -> Optional[Dict[str, Any]]:
    rows = store.query("SELECT * FROM outcome WHERE decision_id = ?", (decision_id,))
    return rows[0] if rows else None


def reviews(decision_id: str, store: Store = STORE) -> List[Dict[str, Any]]:
    return store.query(
        "SELECT * FROM review WHERE decision_id = ? ORDER BY reviewed_on, id",
        (decision_id,),
    )


def attributions(decision_id: str, store: Store = STORE) -> List[Dict[str, Any]]:
    return store.query(
        "SELECT * FROM attribution WHERE decision_id = ? ORDER BY id", (decision_id,)
    )


def violations(decision_id: str, store: Store = STORE) -> List[Dict[str, Any]]:
    return store.query(
        "SELECT * FROM process_violation WHERE decision_id = ? ORDER BY code, id",
        (decision_id,),
    )


def revisions(row_id: str, store: Store = STORE) -> List[Dict[str, Any]]:
    return store.query(
        "SELECT * FROM revision WHERE row_id = ? ORDER BY id", (row_id,)
    )


def transitions_of(decision_id: str, store: Store = STORE) -> List[Dict[str, Any]]:
    return store.query(
        "SELECT * FROM decision_transition WHERE decision_id = ? ORDER BY id",
        (decision_id,),
    )


# -------------------------------------------------------------- 派生量


def net_qty(decision_id: str, store: Store = STORE) -> float:
    rows = executions(decision_id, store)
    total = 0.0
    for row in rows:
        q = float(row.get("qty") or 0)
        total += q if row.get("side") == "BUY" else -q
    return total


def _derive_action(side: str, running_qty: float, qty: float) -> str:
    eps = threshold("flat_qty_epsilon", 1e-6)
    if side == "BUY":
        return "OPEN" if abs(running_qty) <= eps else "ADD"
    remaining = running_qty - qty
    return "CLOSE" if remaining <= eps else "REDUCE"


def _entry_window_passed(decision_id: str, store: Store, ref: str = "") -> bool:
    plan = current_plan(decision_id, store)
    if not plan:
        return False
    end = (plan.get("entry_window_end") or "").strip()
    if not end:
        return False
    return (ref or today()) > end


def context(decision_id: str, store: Store = STORE) -> lifecycle.Context:
    """给状态机守卫组装事实。"""
    row = require_decision(decision_id, store)
    plan = current_plan(decision_id, store)
    outcome = get_outcome(decision_id, store)
    revs = reviews(decision_id, store)
    latest = revs[-1] if revs else {}
    confirmed_attr = [
        a for a in attributions(decision_id, store) if int(a.get("user_confirmed") or 0)
    ]
    return lifecycle.Context(
        thesis=row.get("thesis") or "",
        n_expectations=len(expectations(decision_id, store)),
        n_plans=len(plans(decision_id, store)),
        has_invalidation=bool((plan or {}).get("invalidation")),
        n_executions=len(executions(decision_id, store)),
        net_qty=net_qty(decision_id, store),
        has_outcome=outcome is not None,
        outcome_confirmed=bool(int(latest.get("outcome_confirmed") or 0)),
        violations_confirmed=bool(int(latest.get("violations_confirmed") or 0)),
        n_confirmed_attributions=len(confirmed_attr),
        entry_window_passed=_entry_window_passed(decision_id, store),
        origin=row.get("origin") or "EX_ANTE",
        current_status=row.get("status") or "",
    )


# -------------------------------------------------------------- 写入：Decision


def create_decision(
    code: str,
    name: str = "",
    thesis: str = "",
    earning_type: str = "",
    holding_period: str = "",
    market_context: str = "",
    direction: str = "long",
    opened_on: str = "",
    account: str = "",
    source: str = "user",
    created_by: str = "user",
    subjective_context: str = "",
    legacy_reconstructed: bool = False,
    origin: str = "EX_ANTE",
    witnessed_at: str = "",
    recorder_input_id: str = "",
    recorder_draft_id: str = "",
    origin_status: str = "",
    origin_confidence: str = "",
    environment: str = "",
    demo: Optional[int] = None,
    research_project_id: str = "",
    research_thesis_id: str = "",
    research_thesis_version: int = 0,
    store: Store = STORE,
) -> str:
    day = opened_on or today()
    norm = normalize_code(code) or code
    origin = (origin or "EX_ANTE").upper()
    if origin not in ORIGINS:
        raise ReviewError("未知 origin：{0}。允许：{1}".format(origin, sorted(ORIGINS)))
    if not subjective_context:
        subjective_context = "available" if (thesis or "").strip() else "not_recorded"
    if subjective_context not in SUBJECTIVE_CONTEXTS:
        raise ReviewError(
            "未知 subjective_context：{0}。允许：{1}".format(
                subjective_context, sorted(SUBJECTIVE_CONTEXTS)
            )
        )
    if origin == "POST_HOC" and subjective_context == "available" and not (thesis or "").strip():
        subjective_context = "not_recorded"
    decision_id = make_decision_id(day, norm, store)
    row: Dict[str, Any] = {
        "id": decision_id,
        "opened_on": day,
        "code": norm,
        "name": name,
        "direction": direction,
        "thesis": thesis,
        "earning_type": earning_type,
        "holding_period": holding_period,
        "market_context": market_context,
        "status": lifecycle.DRAFT,
        "closed_on": "",
        "reviewed_at": "",
        "subjective_context": subjective_context,
        "legacy_reconstructed": 1 if legacy_reconstructed else 0,
        "account": account,
        "origin": origin,
        "witnessed_at": witnessed_at or "",
        "recorder_input_id": recorder_input_id,
        "recorder_draft_id": recorder_draft_id,
        "origin_status": origin_status or ("SETTLED" if origin == "POST_HOC" else "PROVISIONAL"),
        "origin_confidence": origin_confidence or "KNOWN",
    }
    if research_project_id or research_thesis_id or research_thesis_version:
        from core.research.decision_link import assert_link
        assert_link(research_project_id, research_thesis_id, int(research_thesis_version or 0), store)
        row["research_project_id"] = research_project_id
        row["research_thesis_id"] = research_thesis_id
        row["research_thesis_version"] = int(research_thesis_version)
    try:
        from core.review import flags as _flags
        row["environment"] = environment or _flags.current_environment()
        row["demo"] = 1 if (demo if demo is not None else (1 if _flags.is_demo() else 0)) else 0
    except Exception:  # noqa: BLE001
        pass
    row.update(_prov(source, created_by, effective_at=day))
    _insert(store, "decision", row)
    _log_transition(decision_id, "", lifecycle.DRAFT, created_by, source, "created", store)
    _maybe_freeze_entry(decision_id, store)
    return decision_id


def add_expectation(
    decision_id: str,
    raw_text: str,
    window_start: str = "",
    window_end: str = "",
    confidence: Optional[int] = None,
    source: str = "user",
    created_by: str = "user",
    store: Store = STORE,
) -> str:
    require_decision(decision_id, store)
    if not (raw_text or "").strip():
        raise ReviewError("expectation 原文不能为空")
    eid = _child_id(store, "expectation", "E", decision_id)
    row: Dict[str, Any] = {
        "id": eid,
        "decision_id": decision_id,
        "raw_text": raw_text,
        "predicate_json": "",
        "predicate_version": 0,
        "compiler": "",
        "compiler_version": "",
        "user_confirmed": 0,
        "confirmed_at": "",
        "window_start": window_start,
        "window_end": window_end,
        "confidence": confidence,
        "status": "OPEN",
        "verdict": "PENDING",
        "evaluated_at": "",
        "evaluation_note": "",
    }
    row.update(_prov(source, created_by))
    _insert(store, "expectation", row)
    return eid


def add_plan(
    decision_id: str,
    entry_rule: str = "",
    invalidation: str = "",
    target_size_pct: Optional[float] = None,
    target_size_amount: Optional[float] = None,
    stop_price: Optional[float] = None,
    stop_rule: str = "",
    add_rule: str = "",
    reduce_rule: str = "",
    holding_period: str = "",
    entry_window_start: str = "",
    entry_window_end: str = "",
    reason_for_revision: str = "",
    source: str = "user",
    created_by: str = "user",
    store: Store = STORE,
) -> str:
    """追加一版 plan。已有版本被标 superseded_by，行本身不改内容。"""
    require_decision(decision_id, store)
    existing = plans(decision_id, store)
    revision = len(existing) + 1
    if revision > 1 and not reason_for_revision:
        raise ReviewError("改计划必须写 reason_for_revision —— 改的理由本身就是复盘素材")
    pid = _child_id(store, "plan", "PL", decision_id)
    row: Dict[str, Any] = {
        "id": pid,
        "decision_id": decision_id,
        "revision": revision,
        "entry_rule": entry_rule,
        "entry_window_start": entry_window_start,
        "entry_window_end": entry_window_end,
        "target_size_pct": target_size_pct,
        "target_size_amount": target_size_amount,
        "add_rule": add_rule,
        "reduce_rule": reduce_rule,
        "stop_price": stop_price,
        "stop_rule": stop_rule,
        "invalidation": invalidation,
        "holding_period": holding_period,
        "superseded_by": "",
        "reason_for_revision": reason_for_revision,
    }
    prov = _prov(source, created_by)
    prov.pop("revision", None)  # plan 自己有 revision 语义
    row.update(prov)
    _insert(store, "plan", row)
    with store.connect() as conn:
        conn.execute(
            "UPDATE plan SET superseded_by = ? WHERE decision_id = ? AND id != ?"
            " AND superseded_by = ''",
            (pid, decision_id, pid),
        )
    return pid


def add_execution(
    code: str,
    executed_on: str,
    side: str,
    price: float,
    qty: float,
    decision_id: Optional[str] = None,
    name: str = "",
    executed_at: str = "",
    amount: Optional[float] = None,
    size_pct: Optional[float] = None,
    planned: str = "unknown",
    trade_id: str = "",
    note: str = "",
    source: str = "user",
    created_by: str = "user",
    subjective_context: str = "",
    account: str = "",
    broker_order_id: str = "",
    fingerprint: str = "",
    store: Store = STORE,
) -> str:
    """登记一笔成交。decision_id 可为 None —— 历史流水就是这么进来的。"""
    side = (side or "").upper()
    if side not in ("BUY", "SELL"):
        raise ReviewError("side 只能是 BUY / SELL，收到 {0!r}".format(side))
    if planned not in ("yes", "no", "unknown"):
        raise ReviewError("planned 只能是 yes / no / unknown")
    norm = normalize_code(code) or code

    if not subjective_context:
        if source == "legacy_import":
            subjective_context = "unavailable"
        elif decision_id and has_recorded_context(decision_id, store):
            subjective_context = "available"
        else:
            subjective_context = "not_recorded"
    if subjective_context not in SUBJECTIVE_CONTEXTS:
        raise ReviewError(
            "未知 subjective_context：{0}。允许：{1}".format(
                subjective_context, sorted(SUBJECTIVE_CONTEXTS)
            )
        )
    if subjective_context == "available" and not decision_id:
        raise ReviewError("execution.subjective_context=available 需要已关联有主观记录的 Decision")
    if subjective_context == "available" and decision_id and not has_recorded_context(decision_id, store):
        subjective_context = "not_recorded"

    running = 0.0
    action = ""
    if decision_id:
        row = require_decision(decision_id, store)
        if row["code"] and norm != row["code"]:
            raise ReviewError(
                "标的不符：Decision {0} 是 {1}，这笔成交是 {2}".format(
                    decision_id, row["code"], norm
                )
            )
        running = net_qty(decision_id, store)
        action = _derive_action(side, running, float(qty))
        if side == "SELL" and float(qty) - running > threshold("flat_qty_epsilon", 1e-6):
            raise ReviewError(
                "卖出 {0} 超过该 Decision 当前持仓 {1}。请拆成两笔或挂到正确的 Decision".format(
                    qty, running
                )
            )

    eid = "X-{0}-{1}-{2:04d}".format(
        (executed_on or today()).replace("-", ""),
        norm,
        _next_seq(
            store,
            "execution",
            "X-{0}-{1}-".format((executed_on or today()).replace("-", ""), norm),
        ),
    )
    row_ex: Dict[str, Any] = {
        "id": eid,
        "decision_id": decision_id,
        "trade_id": trade_id,
        "executed_on": executed_on or today(),
        "executed_at": executed_at,
        "code": norm,
        "name": name,
        "side": side,
        "action": action,
        "price": float(price),
        "qty": float(qty),
        "amount": float(amount) if amount is not None else float(price) * float(qty),
        "size_pct": size_pct,
        "planned": planned,
        "subjective_context": subjective_context,
        "note": note,
        "account": account,
        "broker_order_id": broker_order_id,
        "fingerprint": fingerprint,
    }
    row_ex.update(_prov(source, created_by, effective_at=executed_on or today()))
    _insert(store, "execution", row_ex)
    if decision_id:
        from core.review.origin import maybe_settle_on_attach
        maybe_settle_on_attach(
            decision_id, get_execution(eid, store) or row_ex,
            changed_by=created_by, store=store,
        )
    return eid


def get_execution(execution_id: str, store: Store = STORE) -> Optional[Dict[str, Any]]:
    rows = store.query("SELECT * FROM execution WHERE id = ?", (execution_id,))
    return rows[0] if rows else None


def record_match_status(
    execution_id: str,
    status: str,
    by: str = "",
    reason: str = "",
    matcher_version: str = "",
    store: Store = STORE,
) -> None:
    """写匹配审计。AUTO_MATCHED / REVIEW_REQUIRED / NO_CANDIDATE 都留痕。"""
    with store.connect() as conn:
        conn.execute(
            "UPDATE execution SET match_status = ?, matched_at = ?, matched_by = ?,"
            " match_reason = ?, matcher_version = ? WHERE id = ?",
            (status, now(), by, reason, matcher_version, execution_id),
        )


def attach_execution(
    execution_id: str,
    decision_id: str,
    planned: str = "",
    changed_by: str = "user",
    match_status: str = "",
    match_reason: str = "",
    matcher_version: str = "",
    store: Store = STORE,
) -> None:
    """把一笔孤儿 execution 挂到 Decision 上。

    走 amend 写 revision，再写 match_* 审计字段 —— 谁挂的、依据是什么、
    是自动还是人工，全部可回溯。
    """
    ex = get_execution(execution_id, store)
    if ex is None:
        raise ReviewError("找不到 execution：{0}".format(execution_id))
    if ex.get("decision_id"):
        raise ReviewError(
            "{0} 已挂在 {1} 上。要改归属请先作废重录，不做静默改挂".format(
                execution_id, ex["decision_id"]
            )
        )
    decision = require_decision(decision_id, store)
    if ex["code"] != decision["code"]:
        raise ReviewError(
            "标的不符：execution 是 {0}，Decision 是 {1}".format(ex["code"], decision["code"])
        )
    if (ex.get("account") or "") != (decision.get("account") or ""):
        raise ReviewError(
            "账户不符：execution 在 {0!r}，Decision 在 {1!r}".format(
                ex.get("account") or "", decision.get("account") or ""
            )
        )

    amend("execution", execution_id, "decision_id", decision_id,
          match_reason or "关联到 Decision", changed_by,
          source="system" if changed_by == "system" else "user", store=store)
    if planned:
        amend("execution", execution_id, "planned", planned, "复盘时补记是否计划内",
              changed_by, store=store)

    running = 0.0
    for row in executions(decision_id, store):
        if row["id"] == execution_id:
            action = _derive_action(row["side"], running, float(row["qty"]))
            amend("execution", execution_id, "action", action, "关联后重算 action",
                  "system", source="system", store=store)
        running += float(row["qty"]) if row["side"] == "BUY" else -float(row["qty"])

    if match_status:
        record_match_status(execution_id, match_status, changed_by, match_reason,
                            matcher_version, store)
    _sync_execution_subjective(execution_id, decision_id, changed_by, store)
    clear_candidates(execution_id, store)
    from core.review.origin import maybe_settle_on_attach
    maybe_settle_on_attach(decision_id, get_execution(execution_id, store) or ex,
                           changed_by=changed_by, store=store)


def _sync_execution_subjective(
    execution_id: str, decision_id: str, changed_by: str, store: Store
) -> None:
    """挂上 Decision 后，按有没有真实主观记录升级 not_recorded → available。

    unavailable 永不升级：历史缺失是永久的，不允许为了自动化补。
    """
    ex = get_execution(execution_id, store)
    if ex is None:
        return
    if (ex.get("subjective_context") or "") == "unavailable":
        return
    target = "available" if has_recorded_context(decision_id, store) else "not_recorded"
    if (ex.get("subjective_context") or "") == target:
        return
    amend(
        "execution", execution_id, "subjective_context", target,
        "关联 Decision 后同步主观上下文可得性",
        changed_by,
        source="system" if changed_by == "system" else "user",
        store=store,
    )


def clear_candidates(execution_id: str, store: Store = STORE) -> None:
    with store.connect() as conn:
        conn.execute("DELETE FROM match_candidate WHERE execution_id = ?", (execution_id,))


def candidates_of(execution_id: str, store: Store = STORE) -> List[Dict[str, Any]]:
    return store.query(
        "SELECT * FROM match_candidate WHERE execution_id = ? ORDER BY rank",
        (execution_id,),
    )


# ------------------------------------------------------------- append-only 改写


_AMENDABLE = {
    "decision": {
        "thesis", "name", "earning_type", "holding_period", "market_context", "direction",
        "subjective_context", "origin",
        "research_project_id", "research_thesis_id", "research_thesis_version",
    },
    "expectation": {
        "predicate_json", "predicate_version", "compiler", "compiler_version",
        "user_confirmed", "confirmed_at", "window_start", "window_end",
        "confidence", "status", "verdict", "evaluated_at", "evaluation_note",
    },
    "plan": {"superseded_by"},
    "execution": {"decision_id", "planned", "action", "size_pct", "note", "subjective_context"},
    "review": {"outcome_confirmed", "violations_confirmed", "lesson", "user_note"},
    "attribution": {
        "primary_error", "contributing", "counterfactual", "confidence",
        "evidence", "user_confirmed",
    },
}

# 用户原话与确定性产物不可改写。要改就作废重录。
_FROZEN = {
    "expectation": {"raw_text"},
    "execution": {"price", "qty", "side", "executed_on", "code"},
    "outcome": {"*"},
}


def amend(
    table: str,
    row_id: str,
    field: str,
    new_value: Any,
    reason: str = "",
    changed_by: str = "user",
    source: str = "user",
    store: Store = STORE,
) -> Dict[str, Any]:
    """改一个字段：写 revision 事件 + 更新投影。旧值永不丢失。"""
    frozen = _FROZEN.get(table, set())
    if "*" in frozen or field in frozen:
        raise ReviewError(
            "{0}.{1} 是只读的。用户原话和确定性产物不允许改写，需要变更请作废重录".format(table, field)
        )
    allowed = _AMENDABLE.get(table)
    if allowed is None:
        raise ReviewError("{0} 不支持 amend".format(table))
    if field not in allowed:
        raise ReviewError("{0}.{1} 不在可修订字段里：{2}".format(table, field, sorted(allowed)))
    rows = store.query("SELECT * FROM {0} WHERE id = ?".format(table), (row_id,))
    if not rows:
        raise ReviewError("找不到 {0}：{1}".format(table, row_id))
    old = rows[0].get(field)
    if str(old) == str(new_value):
        return {"changed": False, "field": field, "value": old}
    if table == "execution" and field == "subjective_context" and str(old) == "unavailable":
        raise ReviewError("legacy unavailable 是永久缺失，不能改成 available / not_recorded")
    if table == "decision" and field == "origin":
        from core.review.origin import assert_not_upgrade
        assert_not_upgrade(str(old), str(new_value))
    if not reason:
        raise ReviewError("修改必须写 reason —— 为什么改，本身就是复盘素材")

    with store.connect() as conn:
        conn.execute(
            "INSERT INTO revision (table_name, row_id, field, old_value, new_value,"
            " reason, changed_at, changed_by, source) VALUES (?,?,?,?,?,?,?,?,?)",
            (table, row_id, field, str(old), str(new_value), reason, now(), changed_by, source),
        )
        conn.execute(
            "UPDATE {0} SET {1} = ? WHERE id = ?".format(table, field), (new_value, row_id)
        )
        has_rev = any(
            r[1] == "revision" for r in conn.execute("PRAGMA table_info({0})".format(table))
        )
        if has_rev and table != "plan":
            conn.execute(
                "UPDATE {0} SET revision = revision + 1 WHERE id = ?".format(table), (row_id,)
            )
    return {"changed": True, "field": field, "old": old, "new": new_value}


# -------------------------------------------------------------- 状态转换


def _log_transition(
    decision_id: str,
    from_status: str,
    to_status: str,
    changed_by: str,
    source: str,
    reason: str,
    store: Store = STORE,
) -> None:
    with store.connect() as conn:
        conn.execute(
            "INSERT INTO decision_transition (decision_id, from_status, to_status,"
            " occurred_at, changed_by, source, reason) VALUES (?,?,?,?,?,?,?)",
            (decision_id, from_status, to_status, now(), changed_by, source, reason),
        )


def transition(
    decision_id: str,
    target: str,
    reason: str = "",
    changed_by: str = "user",
    source: str = "user",
    store: Store = STORE,
) -> Dict[str, Any]:
    row = require_decision(decision_id, store)
    current = row["status"]
    lifecycle.assert_can(current, target, context(decision_id, store))

    extra: Dict[str, Any] = {}
    if target == lifecycle.CLOSED:
        ex = executions(decision_id, store)
        extra["closed_on"] = ex[-1]["executed_on"] if ex else today()
    if target == lifecycle.REVIEWED:
        extra["reviewed_at"] = now()

    sets = ["status = ?"]
    params: List[Any] = [target]
    for key, value in extra.items():
        sets.append("{0} = ?".format(key))
        params.append(value)
    params.append(decision_id)
    with store.connect() as conn:
        conn.execute("UPDATE decision SET {0} WHERE id = ?".format(", ".join(sets)), params)
    _log_transition(decision_id, current, target, changed_by, source, reason, store)
    if target == lifecycle.REVIEW_PENDING:
        _maybe_freeze_review(decision_id, store)
    return {"id": decision_id, "from": current, "to": target}


def advance(
    decision_id: str, changed_by: str = "system", store: Store = STORE
) -> List[Dict[str, Any]]:
    """把能自动走的状态一次走完（PLANNED→ACTIVE→CLOSED→REVIEW_PENDING）。"""
    moved: List[Dict[str, Any]] = []
    for _ in range(4):
        row = require_decision(decision_id, store)
        target = lifecycle.auto_target(row["status"], context(decision_id, store))
        if not target:
            break
        moved.append(
            transition(decision_id, target, "auto", changed_by, "system", store)
        )
    return moved


# -------------------------------------------------------------- Review 写入


def add_review(
    decision_id: str,
    lesson: str = "",
    user_note: str = "",
    reviewed_on: str = "",
    outcome_confirmed: bool = False,
    violations_confirmed: bool = False,
    created_by: str = "user",
    store: Store = STORE,
) -> str:
    require_decision(decision_id, store)
    rid = _child_id(store, "review", "RV", decision_id)
    row: Dict[str, Any] = {
        "id": rid,
        "decision_id": decision_id,
        "kind": "decision",
        "reviewed_on": reviewed_on or today(),
        "outcome_confirmed": 1 if outcome_confirmed else 0,
        "violations_confirmed": 1 if violations_confirmed else 0,
        "lesson": lesson,
        "user_note": user_note,
    }
    row.update(_prov("user", created_by))
    _insert(store, "review", row)
    return rid


def add_attribution(
    decision_id: str,
    review_id: str,
    primary_error: str,
    contributing: Optional[Sequence[str]] = None,
    counterfactual: str = "",
    confidence: str = "medium",
    evidence: Optional[Sequence[str]] = None,
    user_confirmed: bool = False,
    created_by: str = "user",
    store: Store = STORE,
) -> str:
    from core.review.defs import error_types

    require_decision(decision_id, store)
    valid = set(error_types())
    if primary_error not in valid:
        raise ReviewError("未知 primary_error：{0}。允许：{1}".format(primary_error, sorted(valid)))
    for item in contributing or []:
        if item not in valid:
            raise ReviewError("未知 contributing：{0}".format(item))
    aid = _child_id(store, "attribution", "AT", decision_id)
    row: Dict[str, Any] = {
        "id": aid,
        "review_id": review_id,
        "decision_id": decision_id,
        "primary_error": primary_error,
        "contributing": json.dumps(list(contributing or []), ensure_ascii=False),
        "counterfactual": counterfactual,
        "confidence": confidence,
        "evidence": json.dumps(list(evidence or []), ensure_ascii=False),
        "user_confirmed": 1 if user_confirmed else 0,
    }
    row.update(_prov("user", created_by))
    _insert(store, "attribution", row)
    return aid


def acknowledge_violations(
    decision_id: str, changed_by: str = "user", store: Store = STORE
) -> int:
    with store.connect() as conn:
        cur = conn.execute(
            "UPDATE process_violation SET acknowledged = 1 WHERE decision_id = ?"
            " AND acknowledged = 0",
            (decision_id,),
        )
        return cur.rowcount
