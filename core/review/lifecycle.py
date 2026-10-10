"""Decision 状态机。

状态转换是这套系统里唯一允许改写 decision 行的操作，所以守卫写在一处，
并且每次转换都往 decision_transition 追加一条事件 —— 当前 status 是事件流的投影。

不允许跳状态。DRAFT → REVIEWED 会被 IllegalTransition 拒绝。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from core.review.defs import load

DRAFT = "DRAFT"
PLANNED = "PLANNED"
ACTIVE = "ACTIVE"
CLOSED = "CLOSED"
REVIEW_PENDING = "REVIEW_PENDING"
REVIEWED = "REVIEWED"
CANCELLED = "CANCELLED"
EXPIRED = "EXPIRED"


class IllegalTransition(Exception):
    """目标状态不在当前状态的合法后继里。"""


class GuardFailed(Exception):
    """转换合法，但前置条件没满足。"""


def transitions() -> Dict[str, List[str]]:
    cfg = (load().get("lifecycle") or {}).get("transitions") or {}
    return {k: list(v or []) for k, v in cfg.items()}


def states() -> List[str]:
    return list(((load().get("lifecycle") or {}).get("states") or {}).keys())


def terminal_states() -> List[str]:
    return list((load().get("lifecycle") or {}).get("terminal") or [])


def is_allowed(current: str, target: str) -> bool:
    return target in transitions().get(current, [])


def assert_allowed(current: str, target: str) -> None:
    if not is_allowed(current, target):
        allowed = transitions().get(current, [])
        raise IllegalTransition(
            "{0} → {1} 不允许。{0} 的合法后继：{2}".format(
                current, target, allowed or "（终态，无后继）"
            )
        )


# ------------------------------------------------------------------ 前置条件


@dataclass(frozen=True)
class Context:
    """守卫需要的事实。由 repo 层组装，守卫本身不碰数据库。"""

    thesis: str = ""
    n_expectations: int = 0
    n_plans: int = 0
    has_invalidation: bool = False
    n_executions: int = 0
    net_qty: float = 0.0
    has_outcome: bool = False
    outcome_confirmed: bool = False
    violations_confirmed: bool = False
    n_confirmed_attributions: int = 0
    entry_window_passed: bool = False
    origin: str = "EX_ANTE"
    current_status: str = ""


def _guard_planned(ctx: Context) -> List[str]:
    missing: List[str] = []
    if not (ctx.thesis or "").strip():
        missing.append("thesis 为空")
    if ctx.n_expectations < 1:
        missing.append("没有 expectation")
    if ctx.n_plans < 1:
        missing.append("没有 plan")
    elif not ctx.has_invalidation:
        missing.append("plan 缺 invalidation")
    return missing


def _guard_active(ctx: Context) -> List[str]:
    missing: List[str] = []
    if ctx.n_executions < 1:
        missing.append("没有关联任何 execution")
    # EX_ANTE 必须先走过 PLANNED。POST_HOC 是成交之后才建的壳，允许 DRAFT→ACTIVE。
    if ctx.current_status == DRAFT and ctx.origin != "POST_HOC":
        missing.append("EX_ANTE Decision 不能从 DRAFT 直接进入 ACTIVE，须先 PLANNED")
    return missing


def _guard_closed(ctx: Context) -> List[str]:
    return [] if ctx.n_executions >= 1 else ["没有 execution，无法了结"]


def _guard_review_pending(ctx: Context) -> List[str]:
    return [] if ctx.has_outcome else ["outcome 尚未计算"]


def _guard_reviewed(ctx: Context) -> List[str]:
    missing: List[str] = []
    if not ctx.outcome_confirmed:
        missing.append("outcome 未经用户确认")
    if not ctx.violations_confirmed:
        missing.append("process violation 未经用户确认")
    if ctx.n_confirmed_attributions < 1:
        missing.append("没有用户确认的 attribution")
    return missing


def _guard_cancelled(ctx: Context) -> List[str]:
    return [] if ctx.n_executions == 0 else ["已有 execution，不能撤销，只能 CLOSED"]


def _guard_expired(ctx: Context) -> List[str]:
    missing: List[str] = []
    if ctx.n_executions != 0:
        missing.append("已有 execution，不算过期")
    if not ctx.entry_window_passed:
        missing.append("入场窗口尚未结束")
    return missing


GUARDS: Dict[str, Callable[[Context], List[str]]] = {
    PLANNED: _guard_planned,
    ACTIVE: _guard_active,
    CLOSED: _guard_closed,
    REVIEW_PENDING: _guard_review_pending,
    REVIEWED: _guard_reviewed,
    CANCELLED: _guard_cancelled,
    EXPIRED: _guard_expired,
}


def check(current: str, target: str, ctx: Context) -> Tuple[bool, List[str]]:
    """返回 (能不能转, 缺什么)。不抛异常，供 CLI 预检查用。"""
    if not is_allowed(current, target):
        return False, ["{0} → {1} 不是合法转换".format(current, target)]
    guard = GUARDS.get(target)
    missing = guard(ctx) if guard else []
    return (not missing), missing


def assert_can(current: str, target: str, ctx: Context) -> None:
    assert_allowed(current, target)
    guard = GUARDS.get(target)
    missing = guard(ctx) if guard else []
    if missing:
        raise GuardFailed("{0} → {1} 前置条件不满足：{2}".format(current, target, "；".join(missing)))


def next_states(current: str, ctx: Optional[Context] = None) -> List[Dict[str, object]]:
    """当前状态能去哪，以及各自还缺什么。CLI 的 show 用它给出下一步提示。"""
    out: List[Dict[str, object]] = []
    for target in transitions().get(current, []):
        if ctx is None:
            out.append({"to": target, "ready": None, "missing": []})
            continue
        ok, missing = check(current, target, ctx)
        out.append({"to": target, "ready": ok, "missing": missing})
    return out


def auto_target(current: str, ctx: Context) -> Optional[str]:
    """由事实推导出的自动转换目标。只处理无歧义的那几步。

    DRAFT   + POST_HOC + 有 execution → ACTIVE（事后复盘，跳过 PLANNED）
    PLANNED + 有 execution            → ACTIVE
    ACTIVE  + 净持仓归零              → CLOSED
    CLOSED  + outcome 已算            → REVIEW_PENDING
    """
    from core.review.defs import threshold

    eps = threshold("flat_qty_epsilon", 1e-6)
    if current == DRAFT and ctx.origin == "POST_HOC" and ctx.n_executions >= 1:
        return ACTIVE
    if current == PLANNED and ctx.n_executions >= 1:
        return ACTIVE
    if current == ACTIVE and ctx.n_executions >= 1 and abs(ctx.net_qty) <= eps:
        return CLOSED
    if current == CLOSED and ctx.has_outcome:
        return REVIEW_PENDING
    return None


def path_to(current: str, target: str) -> Sequence[str]:
    """从 current 走到 target 的最短合法路径。用于报错时告诉用户还差几步。"""
    graph = transitions()
    queue: List[List[str]] = [[current]]
    seen = {current}
    while queue:
        path = queue.pop(0)
        node = path[-1]
        if node == target:
            return path
        for nxt in graph.get(node, []):
            if nxt in seen:
                continue
            seen.add(nxt)
            queue.append(path + [nxt])
    return []
