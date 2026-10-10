"""口径冲突保持并列。不取平均，不合成第三个数字。"""
from __future__ import annotations

from typing import Iterable, List, Optional


def _value(claim: dict):
    number = claim.get("numeric_value")
    if number is not None and number != "":
        return ("n", float(number))
    text = (claim.get("object") or claim.get("claim_text") or "").strip()
    return ("t", text)


def detect(claims: Iterable[dict]) -> List[dict]:
    groups = {}
    for claim in claims:
        metric = (claim.get("metric") or "").strip()
        if not metric:
            continue
        groups.setdefault(metric, []).append(claim)
    found = []
    for metric, rows in groups.items():
        values = [_value(row) for row in rows]
        unique = []
        for item in values:
            if item not in unique:
                unique.append(item)
        if len(unique) < 2:
            continue
        left, right = rows[0], rows[1]
        local_ids = [row.get("local_id") or "" for row in rows]
        found.append({
            "topic": metric,
            "metric": metric,
            "value_a": str(unique[0][1]),
            "definition_a": left.get("definition") or "",
            "value_b": str(unique[1][1]),
            "definition_b": right.get("definition") or "",
            "possible_reason": "先核对时间、地区、产品定义、市场边界、收入与GMV、出货与装机、名义与实际、历史与预测。口径未对齐，禁止取平均。",
            "status": "OPEN",
            "claim_ids": local_ids,
            "claim_local_ids": local_ids,
        })
    return found


def contains_average(claims: Iterable[dict]) -> bool:
    groups = {}
    for claim in claims:
        metric = (claim.get("metric") or "").strip()
        number = claim.get("numeric_value")
        if not metric or number is None or number == "":
            continue
        groups.setdefault(metric, []).append(float(number))
    for nums in groups.values():
        if len(nums) < 3:
            continue
        for number in nums:
            rest = [item for item in nums if item != number]
            if len(set(rest)) < 2:
                continue
            if abs(number - (sum(rest) / float(len(rest)))) < 1e-9:
                return True
    return False


def merged_value(_claims: Iterable[dict]) -> Optional[float]:
    """研究冲突没有合并值。调用方应保留两边原文。"""
    return None
