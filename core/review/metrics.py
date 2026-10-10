"""确定性 Metrics。

每个指标返回统一结构：

    value        分子/分母，无合格样本时是 None（不是 0）
    eligible_n   进入分母的样本数
    excluded_n   被排除的样本数
    excluded_why 排除原因计数，看得见才不会自欺
    period       统计区间
    definition   口径原文（来自 config/review.yaml）

分母纪律：subjective_context=unavailable 的历史记录、没有事前 plan 的
Decision、未经用户确认的 predicate，一律不进分母。宁可 eligible_n=0，
也不要一个看着精确但没有意义的百分比。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from core.review import repo
from core.review.defs import metric_spec, required_plan_fields
from core.store import STORE, Store

_ADHERENCE_BREAKERS = ("UNPLANNED_EXECUTION", "SIZE_EXCEEDED", "LATE_ENTRY")


def _result(
    name: str,
    hits: int,
    eligible: int,
    excluded: Dict[str, int],
    period: Tuple[str, str],
) -> Dict[str, Any]:
    spec = metric_spec(name)
    return {
        "metric": name,
        "value": round(hits / eligible * 100, 1) if eligible else None,
        "hits": hits,
        "eligible_n": eligible,
        "excluded_n": sum(excluded.values()),
        "excluded_why": {k: v for k, v in excluded.items() if v},
        "period": {"start": period[0] or "", "end": period[1] or ""},
        "definition": spec.get("definition") or "",
        "denominator": spec.get("denominator") or "",
        "excludes": spec.get("excludes") or "",
    }


def _window(start: str, end: str) -> Tuple[str, str]:
    return (start or "", end or "")


def _decisions_in(start: str, end: str, store: Store) -> List[Dict[str, Any]]:
    sql = "SELECT * FROM decision WHERE 1=1"
    params: List[Any] = []
    if start:
        sql += " AND opened_on >= ?"
        params.append(start)
    if end:
        sql += " AND opened_on <= ?"
        params.append(end)
    return store.query(sql + " ORDER BY opened_on", params)


def _executions_in(start: str, end: str, store: Store) -> List[Dict[str, Any]]:
    sql = "SELECT * FROM execution WHERE 1=1"
    params: List[Any] = []
    if start:
        sql += " AND executed_on >= ?"
        params.append(start)
    if end:
        sql += " AND executed_on <= ?"
        params.append(end)
    return store.query(sql + " ORDER BY executed_on", params)


def _has_exante_plan(decision_id: str, store: Store) -> bool:
    """plan 必须在首笔 execution 之前就录入，事后补的不算事前计划。

    origin=POST_HOC 一律不算事前计划：成交之后才为了复盘建立的 Decision，
    不能伪装成当时就有 plan。origin 不是绕开 created_at 纪律的捷径——
    EX_ANTE 仍然要比系统见证的录入时刻。
    """
    row = repo.get_decision(decision_id, store)
    if row and (row.get("origin") or "EX_ANTE") == "POST_HOC":
        return False
    plans = repo.plans(decision_id, store)
    if not plans:
        return False
    ex = repo.executions(decision_id, store)
    if not ex:
        return True
    first_recorded = min(e.get("created_at") or "" for e in ex)
    witnessed = (row or {}).get("witnessed_at") or (row or {}).get("created_at") or ""
    if witnessed and first_recorded and witnessed > first_recorded:
        return False
    return any((p.get("created_at") or "") <= first_recorded for p in plans)


# ----------------------------------------------------------------- 各指标


def plan_adherence(start: str = "", end: str = "", store: Store = STORE) -> Dict[str, Any]:
    hits = 0
    eligible = 0
    excluded: Dict[str, int] = {
        "无事前 plan": 0, "尚未执行": 0, "事后 Decision": 0, "成交时间精度不足": 0,
    }
    for d in _decisions_in(start, end, store):
        if (d.get("origin") or "EX_ANTE") == "POST_HOC":
            excluded["事后 Decision"] += 1
            continue
        if (d.get("origin_confidence") or "KNOWN") == "UNKNOWN":
            excluded["成交时间精度不足"] += 1
            continue
        if not repo.executions(d["id"], store):
            excluded["尚未执行"] += 1
            continue
        if not _has_exante_plan(d["id"], store):
            excluded["无事前 plan"] += 1
            continue
        eligible += 1
        codes = {v["code"] for v in repo.violations(d["id"], store)}
        if not codes.intersection(_ADHERENCE_BREAKERS):
            hits += 1
    return _result("plan_adherence", hits, eligible, excluded, _window(start, end))


def execution_discipline(
    start: str = "", end: str = "", store: Store = STORE
) -> Dict[str, Any]:
    hits = 0
    eligible = 0
    excluded: Dict[str, int] = {"planned=unknown": 0, "无事前记录(legacy)": 0}
    for ex in _executions_in(start, end, store):
        if ex.get("subjective_context") == "unavailable":
            excluded["无事前记录(legacy)"] += 1
            continue
        if ex.get("planned") not in ("yes", "no"):
            excluded["planned=unknown"] += 1
            continue
        eligible += 1
        if ex["planned"] == "yes":
            hits += 1
    return _result("execution_discipline", hits, eligible, excluded, _window(start, end))


def risk_discipline(start: str = "", end: str = "", store: Store = STORE) -> Dict[str, Any]:
    """分母只含真的触发过失效/止损条件的 Decision。没触发过不算守纪律。"""
    triggers = ("INVALIDATION_TRIGGERED", "STOP_NOT_EXECUTED")
    hits = 0
    eligible = 0
    excluded: Dict[str, int] = {"未触发失效条件": 0, "无 stop/invalidation 可判": 0}
    for d in _decisions_in(start, end, store):
        plan = repo.current_plan(d["id"], store)
        if not plan or (plan.get("stop_price") is None and not plan.get("invalidation")):
            excluded["无 stop/invalidation 可判"] += 1
            continue
        codes = {v["code"] for v in repo.violations(d["id"], store)}
        breached = codes.intersection(triggers)
        sells = [e for e in repo.executions(d["id"], store) if e["side"] == "SELL"]
        if not breached and not sells:
            excluded["未触发失效条件"] += 1
            continue
        eligible += 1
        if not breached:
            hits += 1
    return _result("risk_discipline", hits, eligible, excluded, _window(start, end))


def prediction_accuracy(
    start: str = "", end: str = "", store: Store = STORE
) -> Dict[str, Any]:
    """未确认 predicate 的 expectation 不进分母。P0 通常返回 eligible_n=0。"""
    sql = "SELECT e.*, d.origin AS decision_origin, d.origin_confidence AS origin_confidence FROM expectation e JOIN decision d ON d.id = e.decision_id WHERE 1=1"
    params: List[Any] = []
    if start:
        sql += " AND d.opened_on >= ?"
        params.append(start)
    if end:
        sql += " AND d.opened_on <= ?"
        params.append(end)
    rows = store.query(sql, params)

    hits = 0
    eligible = 0
    excluded: Dict[str, int] = {
        "事后 Decision": 0,
        "成交时间精度不足": 0,
        "predicate 未经用户确认": 0,
        "verdict 尚未判定": 0,
        "无法验证": 0,
    }
    for e in rows:
        if (e.get("decision_origin") or "EX_ANTE") == "POST_HOC":
            excluded["事后 Decision"] += 1
            continue
        if (e.get("origin_confidence") or "KNOWN") == "UNKNOWN":
            excluded["成交时间精度不足"] += 1
            continue
        if not int(e.get("user_confirmed") or 0):
            excluded["predicate 未经用户确认"] += 1
            continue
        if e.get("verdict") == "PENDING":
            excluded["verdict 尚未判定"] += 1
            continue
        if e.get("verdict") == "UNVERIFIABLE":
            excluded["无法验证"] += 1
            continue
        eligible += 1
        if e["verdict"] == "CORRECT":
            hits += 1
    return _result("prediction_accuracy", hits, eligible, excluded, _window(start, end))


def plan_completeness(start: str = "", end: str = "", store: Store = STORE) -> Dict[str, Any]:
    fields = required_plan_fields()
    after_planned = {"PLANNED", "ACTIVE", "CLOSED", "REVIEW_PENDING", "REVIEWED"}
    hits = 0
    eligible = 0
    excluded: Dict[str, int] = {"尚未进入 PLANNED": 0, "事后 Decision": 0, "成交时间精度不足": 0}
    for d in _decisions_in(start, end, store):
        if (d.get("origin") or "EX_ANTE") == "POST_HOC":
            excluded["事后 Decision"] += 1
            continue
        if (d.get("origin_confidence") or "KNOWN") == "UNKNOWN":
            excluded["成交时间精度不足"] += 1
            continue
        if d["status"] not in after_planned:
            excluded["尚未进入 PLANNED"] += 1
            continue
        eligible += 1
        plan = repo.current_plan(d["id"], store) or {}
        if all(str(plan.get(f) or "").strip() for f in fields):
            hits += 1
    return _result("plan_completeness", hits, eligible, excluded, _window(start, end))


ALL = {
    "plan_adherence": plan_adherence,
    "execution_discipline": execution_discipline,
    "risk_discipline": risk_discipline,
    "prediction_accuracy": prediction_accuracy,
    "plan_completeness": plan_completeness,
}


def summary(start: str = "", end: str = "", store: Store = STORE) -> Dict[str, Any]:
    return {
        "period": {"start": start or "", "end": end or ""},
        "metrics": [fn(start, end, store) for fn in ALL.values()],
        "note": "value=None 表示该区间没有合格样本，不是 0%。",
    }
