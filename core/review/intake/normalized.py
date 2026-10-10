"""NormalizedExecution：所有输入源汇合的唯一契约。

适配器只负责把各自的原始格式翻译成这个结构，之后的去重、匹配、落库都不再
关心数据是从 CSV、券商 API 还是截图来的。

fingerprint 的取舍：
  有 broker_order_id 就用它 —— 券商订单号是唯一真正可靠的成交标识。
  没有就退化成 (account, code, 日期, 时间, 方向, 价, 量) 的哈希。
  同一批输入里出现多笔完全相同的成交时，按出现次序加序号区分 —— 这样
  重复导入同一份文件仍然幂等，而真实的两笔相同成交不会被吞掉一笔。
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# 非交易流水的方向关键词。这些是公司行为，不是成交，绝不猜成买卖。
NON_TRADE_KEYWORDS = (
    "红股", "配股", "分红", "派息", "送股", "转增", "股息",
    "利息", "费用", "税", "冻结", "解冻", "转账", "银证",
)


@dataclass
class NormalizedExecution:
    """一笔成交的标准形态。字段语义与 execution 表一致。"""

    code: str
    executed_on: str
    side: str                      # BUY / SELL
    price: float
    qty: float
    account: str = ""
    broker_order_id: str = ""
    executed_at: str = ""          # HH:MM:SS
    name: str = ""
    amount: Optional[float] = None
    size_pct: Optional[float] = None
    planned: str = "unknown"
    note: str = ""
    source: str = "trade_import"
    raw: Dict[str, Any] = field(default_factory=dict)
    # 由 importer 在整批归一后填入，适配器不要自己算
    fingerprint: str = ""

    def base_key(self) -> str:
        return "|".join([
            self.account,
            self.code,
            self.executed_on,
            self.executed_at,
            self.side,
            "{0:.4f}".format(float(self.price)),
            "{0:.4f}".format(float(self.qty)),
        ])


@dataclass
class NonTradeRow:
    """不是成交的行。留着报给用户看，不入库。"""

    reason: str
    detail: str
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ParseResult:
    """适配器的产出。解析失败的行必须显式列出，不允许静默丢弃。"""

    executions: List[NormalizedExecution] = field(default_factory=list)
    non_trade: List[NonTradeRow] = field(default_factory=list)
    unparseable: List[NonTradeRow] = field(default_factory=list)
    adapter: str = ""
    source_ref: str = ""

    @property
    def rows_in(self) -> int:
        return len(self.executions) + len(self.non_trade) + len(self.unparseable)


def _sha(text: str, length: int = 20) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:length]


def fingerprint_of(item: NormalizedExecution, occurrence: int = 0) -> str:
    """稳定去重键。同样的输入永远得到同样的值。"""
    if item.broker_order_id:
        return "fp:oid:" + _sha("{0}|{1}".format(item.account, item.broker_order_id), 16)
    return "fp:{0}".format(_sha("{0}#{1}".format(item.base_key(), occurrence)))


def assign_fingerprints(items: List[NormalizedExecution]) -> List[NormalizedExecution]:
    """给一批成交打指纹。按 base_key 分组编号，处理同秒同价同量的重复成交。"""
    seen: Dict[str, int] = {}
    for item in items:
        if item.broker_order_id:
            item.fingerprint = fingerprint_of(item)
            continue
        key = item.base_key()
        index = seen.get(key, 0)
        seen[key] = index + 1
        item.fingerprint = fingerprint_of(item, index)
    return items


def looks_non_trade(direction: str) -> Optional[str]:
    """方向字段像公司行为就返回命中的关键词，否则 None。"""
    text = direction or ""
    for word in NON_TRADE_KEYWORDS:
        if word in text:
            return word
    return None
