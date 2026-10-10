"""把模型 JSON 收成 RecorderDraft。非法结构当场失败，不猜。"""
from __future__ import annotations

import json
from typing import Any, Dict, Tuple

from core.review.recorder.types import FORBIDDEN_KEYS, INTENTS, RecorderDraft


class ParseError(ValueError):
    pass


def parse_json(raw: str) -> Tuple[RecorderDraft, Dict[str, Any]]:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ParseError("模型输出不是合法 JSON") from exc
    if not isinstance(data, dict):
        raise ParseError("模型输出必须是对象")
    extra: list = []

    def walk(obj) -> None:
        if isinstance(obj, dict):
            extra.extend(k for k in obj if k in FORBIDDEN_KEYS)
            for value in obj.values():
                walk(value)
        elif isinstance(obj, list):
            for value in obj:
                walk(value)

    walk(data)
    if extra:
        raise ParseError("禁止字段出现在输出里：{0}".format(",".join(sorted(set(extra)))))
    draft = RecorderDraft.from_dict(data)
    if draft.intent not in INTENTS:
        raise ParseError("未知 intent：{0}".format(draft.intent))
    return draft, data
