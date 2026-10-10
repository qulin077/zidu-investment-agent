"""config/review.yaml 的读取入口。

枚举与阈值只在 YAML 里定义一次，代码不再各自硬编码。
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List

import yaml

from core.config import CONFIG_DIR

REVIEW_YAML = CONFIG_DIR / "review.yaml"


@lru_cache(maxsize=1)
def load(path: str = "") -> Dict[str, Any]:
    target = Path(path) if path else REVIEW_YAML
    if not target.exists():
        return {}
    return yaml.safe_load(target.read_text(encoding="utf-8")) or {}


def threshold(key: str, default: float) -> float:
    return float((load().get("thresholds") or {}).get(key, default))


def gate_version() -> str:
    return str(load().get("gate_version") or "g1")


def error_types() -> List[str]:
    return list((load().get("error_types") or {}).keys())


def violation_codes() -> List[str]:
    return list((load().get("process_violations") or {}).keys())


def violation_spec(code: str) -> Dict[str, str]:
    return dict((load().get("process_violations") or {}).get(code) or {})


def metric_spec(name: str) -> Dict[str, str]:
    return dict((load().get("metrics") or {}).get(name) or {})


def required_plan_fields() -> List[str]:
    return list((load().get("metrics") or {}).get("required_plan_fields") or [])
