"""标的代码与股票池的唯一出口。

替代散在 account_snapshot_calc / behavior_review / trade_gate /
trading_data_audit / personal_board 里的五份代码规范化实现。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Dict, List, Optional

import yaml

from core.config import UNIVERSE_YAML

_NULLISH = {"", "nan", "none", "null", "na", "-"}
_TRAILING_ZERO_FLOAT = re.compile(r"^-?\d+\.0+$")
_SIX_DIGITS = re.compile(r"\d{6}")


def normalize_code(value: Any) -> str:
    """统一成 6 位 A 股代码。

    覆盖实际数据里出现过的全部写法：``2384``、``2384.0``、``002384``、
    ``002384.SZ``、``sz002384``、``600000.SH``。无法识别时返回去空白的原串，
    不静默造出一个假代码。空值返回空串。
    """
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() in _NULLISH:
        return ""
    # pandas 读数值列常见的 2384.0
    if _TRAILING_ZERO_FLOAT.match(text):
        text = text.split(".", 1)[0]
    match = _SIX_DIGITS.search(text)
    if match:
        return match.group(0)
    if text.isdigit():
        return text.zfill(6)
    return text


def is_valid_code(value: Any) -> bool:
    code = normalize_code(value)
    return len(code) == 6 and code.isdigit() and code != "000000"


def market_prefix(code: Any) -> str:
    """交易所前缀。北交所走 bj，沪市 sh，其余 sz。"""
    norm = normalize_code(code).zfill(6)
    if norm.startswith(("5", "6", "9")):
        return "sh"
    if norm.startswith(("4", "8")):
        return "bj"
    return "sz"


def tencent_symbol(code: Any) -> str:
    return "{0}{1}".format(market_prefix(code), normalize_code(code).zfill(6))


def dotted_symbol(code: Any) -> str:
    """600000.SH 形式，部分数据源与研报口径使用。"""
    return "{0}.{1}".format(normalize_code(code).zfill(6), market_prefix(code).upper())


@dataclass(frozen=True)
class Instrument:
    code: str
    name: str
    sector: str
    role: str
    priority: int

    @property
    def board(self) -> str:
        if self.code.startswith("688"):
            return "科创板"
        if self.code.startswith("30"):
            return "创业板"
        if self.code.startswith(("4", "8")):
            return "北交所"
        if self.code.startswith("6"):
            return "沪主板"
        if self.code.startswith(("0", "2")):
            return "深主板"
        return "其他"


@lru_cache(maxsize=1)
def load_universe() -> List[Instrument]:
    """读取 config/universe.yaml。结果缓存，进程内只解析一次。"""
    if not UNIVERSE_YAML.exists():
        return []
    with UNIVERSE_YAML.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    out: List[Instrument] = []
    seen = set()
    for item in data.get("stocks") or []:
        code = normalize_code(item.get("code"))
        if not is_valid_code(code) or code in seen:
            continue
        seen.add(code)
        out.append(
            Instrument(
                code=code,
                name=str(item.get("name") or "").strip(),
                sector=str(item.get("sector") or "").strip(),
                role=str(item.get("role") or "").strip(),
                priority=int(item.get("priority") or 99),
            )
        )
    return out


def universe_codes(priority_max: Optional[int] = None) -> List[str]:
    return [
        inst.code
        for inst in load_universe()
        if priority_max is None or inst.priority <= priority_max
    ]


def universe_index() -> Dict[str, Instrument]:
    return {inst.code: inst for inst in load_universe()}


def resolve_name(code: Any) -> str:
    inst = universe_index().get(normalize_code(code))
    return inst.name if inst else ""
