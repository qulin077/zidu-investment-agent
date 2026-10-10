"""结构化 fingerprint。V0 不用 embedding。情绪标签只来自用户自述。"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Iterable, List, Sequence

from core.review.memory.types import FOMO_PHRASES


def _norm(text: str) -> str:
    return (text or "").strip()


def emotion_tag_from_text(*parts: str) -> str:
    blob = " ".join(_norm(p) for p in parts)
    if not blob:
        return ""
    if any(p in blob for p in FOMO_PHRASES):
        return "FOMO"
    return ""


def holding_bucket(raw: str) -> str:
    text = _norm(raw)
    if not text:
        return ""
    if any(k in text for k in ("日内", "短线", "短期", "数日", "几天")):
        return "SHORT"
    if any(k in text for k in ("波段", "数周", "几周")):
        return "SWING"
    if any(k in text for k in ("中长", "长期", "数月")):
        return "LONG"
    return "OTHER"


def behavior_tag(violation_codes: Sequence[str], primary_error: str) -> str:
    codes = set(violation_codes or [])
    if "SIZE_EXCEEDED" in codes:
        return "SIZE_EXPANSION"
    if primary_error == "EMOTION_ERROR":
        return "EMOTION_SELF"
    if primary_error == "PROCESS_ERROR":
        return "PROCESS"
    return primary_error or ""


def pattern_key(
    primary_error: str,
    violation_codes: Iterable[str],
    emotion_tag: str = "",
) -> str:
    """核心键：归因 + 违规 + 已确认情绪。不含人格，不含行情猜测。

    同一 SIZE_EXCEEDED 但 primary 不同 → 不同 key，不会被简单合并。
    上下文差异留在 instance 上，不进 key，以便形成 broad pattern 但仍可展示差别。
    """
    codes = sorted({c for c in (violation_codes or []) if c})
    return "|".join([
        _norm(primary_error) or "UNKNOWN",
        ",".join(codes) or "NO_VIOLATION",
        _norm(emotion_tag),
    ])


def pattern_id_for(key: str) -> str:
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]
    return "PT-{0}".format(digest)


def evidence_hash(decision_ids: Sequence[str]) -> str:
    joined = "|".join(sorted({d for d in decision_ids if d}))
    return hashlib.sha1(joined.encode("utf-8")).hexdigest()


def loads_list(raw: Any) -> List[str]:
    if isinstance(raw, list):
        return [str(x) for x in raw]
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return []
    if isinstance(data, list):
        return [str(x) for x in data]
    return []


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def context_tags(market_context: str) -> List[str]:
    text = _norm(market_context)
    if not text:
        return []
    tags = []
    if any(k in text for k in ("高开", "强势", "大涨")):
        tags.append("强势高开")
    if any(k in text for k in ("低开", "大跌", "恐慌盘")):
        tags.append("弱势低开")
    return tags
