"""采集器的公共类型与工具。"""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd


@dataclass
class IngestResult:
    dataset: str
    rows: int = 0
    asof: str = ""
    ok: bool = True
    message: str = ""
    skipped: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "dataset": self.dataset,
            "rows": self.rows,
            "asof": self.asof,
            "ok": self.ok,
            "message": self.message,
            "skipped": self.skipped[:20],
        }


def read_csv(path: Path, **kwargs: Any) -> Optional[pd.DataFrame]:
    """读 CSV。现有产物多为 utf-8-sig（带 BOM），统一在这里处理。"""
    if not path.exists():
        return None
    try:
        return pd.read_csv(path, encoding="utf-8-sig", **kwargs)
    except (pd.errors.EmptyDataError, pd.errors.ParserError, UnicodeDecodeError, OSError):
        return None


def clean(value: Any) -> Any:
    """把 pandas 的 NaN/NaT 转成 None，避免写进 SQLite 变成字符串 'nan'。"""
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if value is pd.NaT:
        return None
    if isinstance(value, str):
        text = value.strip()
        return None if text.lower() in {"", "nan", "none", "nat"} else text
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def as_float(value: Any) -> Optional[float]:
    cleaned = clean(value)
    if cleaned is None:
        return None
    try:
        result = float(cleaned)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(result) else result


def as_text(value: Any) -> str:
    cleaned = clean(value)
    return "" if cleaned is None else str(cleaned)


def stable_id(*parts: Any) -> str:
    """内容哈希，给没有天然主键的记录生成稳定 id，重复导入不会产生重复行。"""
    joined = "|".join(as_text(p) for p in parts)
    return hashlib.sha1(joined.encode("utf-8")).hexdigest()[:20]
