"""输入适配器。

每个适配器只做一件事：把某种原始格式翻译成 NormalizedExecution。
不去重、不落库、不匹配、不推进状态 —— 那些都在下游，且与来源无关。

新增一种输入源 = 新写一个 parse()，下游零改动。
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol

from core.review.intake.normalized import (
    NonTradeRow,
    NormalizedExecution,
    ParseResult,
    looks_non_trade,
)
from core.symbols import normalize_code


class RawExecutionAdapter(Protocol):
    """适配器契约。"""

    name: str

    def parse(self, source: Any, account: str = "") -> ParseResult:
        ...


def _num(raw: Any) -> Optional[float]:
    try:
        text = str(raw).replace(",", "").replace("¥", "").strip()
        return float(text) if text else None
    except (TypeError, ValueError):
        return None


def _side(raw: str) -> Optional[str]:
    text = raw or ""
    if "买" in text or text.strip().upper() in ("BUY", "B"):
        return "BUY"
    if "卖" in text or text.strip().upper() in ("SELL", "S"):
        return "SELL"
    return None


def _pick(row: Dict[str, str], *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if value:
            return str(value).strip()
    return ""


class CsvAdapter:
    """券商导出 / 手工整理的 CSV。

    列名按别名匹配，兼容仓库里 `交易流水.csv` 的中文表头和常见券商英文表头。
    认不出的列一律忽略，认不出的行进 unparseable —— 不猜。
    """

    name = "csv"

    def parse(self, source: Any, account: str = "") -> ParseResult:
        path = Path(source)
        result = ParseResult(adapter=self.name, source_ref=str(path))
        if not path.exists():
            raise FileNotFoundError("找不到输入文件：{0}".format(path))

        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = [
                {k: (v or "").strip() for k, v in row.items() if k}
                for row in csv.DictReader(handle)
            ]

        for row in rows:
            direction = _pick(row, "方向", "买卖方向", "操作", "side", "Side")
            non_trade = looks_non_trade(direction)
            if non_trade:
                result.non_trade.append(
                    NonTradeRow(
                        reason="公司行为/资金流水，非成交",
                        detail="{0} {1}".format(direction, _pick(row, "名称", "证券名称", "name")),
                        raw=row,
                    )
                )
                continue

            side = _side(direction)
            code = normalize_code(_pick(row, "代码", "证券代码", "股票代码", "symbol", "code"))
            day = _pick(row, "日期", "成交日期", "date", "trade_date")[:10]
            price = _num(_pick(row, "价格", "成交价", "成交价格", "price"))
            qty = _num(_pick(row, "数量", "成交数量", "成交量", "qty", "quantity"))

            missing = [
                label
                for label, ok in (
                    ("方向", side), ("代码", code), ("日期", day),
                    ("价格", price), ("数量", qty),
                )
                if not ok
            ]
            if missing:
                result.unparseable.append(
                    NonTradeRow(
                        reason="缺少必填字段：{0}".format("、".join(missing)),
                        detail=str(row)[:160],
                        raw=row,
                    )
                )
                continue

            result.executions.append(
                NormalizedExecution(
                    code=code,
                    executed_on=day,
                    side=side,
                    price=float(price),
                    qty=abs(float(qty)),
                    account=_pick(row, "账户", "account") or account,
                    broker_order_id=_pick(row, "委托编号", "合同编号", "订单号",
                                          "broker_order_id", "order_id"),
                    executed_at=_pick(row, "时间", "成交时间", "time"),
                    name=_pick(row, "名称", "证券名称", "股票名称", "name"),
                    amount=_num(_pick(row, "金额", "成交金额", "amount")),
                    note=_pick(row, "备注", "note"),
                    raw=row,
                )
            )
        return result


class VisionAdapter:
    """交割单截图 → NormalizedExecution。

    P1.1 只声明接口。真正接上时，这里调 core.vision 拿到成交列表，再翻译成
    NormalizedExecution 即可 —— 去重、匹配、队列全部复用现有链路，不需要改。

    刻意不在本轮实现：视觉识别有错读风险，必须先设计逐笔确认界面，
    否则会把识别错误静默写进真相源。
    """

    name = "vision"

    def parse(self, source: Any, account: str = "") -> ParseResult:
        raise NotImplementedError(
            "Vision 适配器在 P1.1 只定义接口。接入前需要先做逐笔人工确认界面，"
            "否则 OCR 误读会静默污染 execution 表。"
        )


ADAPTERS: Dict[str, RawExecutionAdapter] = {
    CsvAdapter.name: CsvAdapter(),
    VisionAdapter.name: VisionAdapter(),
}


def get_adapter(name: str) -> RawExecutionAdapter:
    adapter = ADAPTERS.get(name)
    if adapter is None:
        raise KeyError("未知适配器：{0}。可用：{1}".format(name, sorted(ADAPTERS)))
    return adapter
