"""收盘导入。

分三层，是为了让输入源可换而下游不动：

    RawExecutionAdapter  →  NormalizedExecution  →  ExecutionImporter
    （CSV / Excel /          （唯一的中间契约，        （去重、落库、
      券商 API / 截图）        带稳定 fingerprint）      不关心来源）

P1.1 只实现 CSV 适配器。Vision 适配器已声明接口但不调用模型。
"""
from core.review.intake.normalized import (  # noqa: F401
    NormalizedExecution,
    NonTradeRow,
    ParseResult,
    fingerprint_of,
)
