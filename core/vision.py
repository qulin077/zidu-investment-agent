"""交割单截图 → 成交列表。DashScope Qwen-VL。"""
from __future__ import annotations

import base64
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from core.config import DATA_DIR
from core.http import DEFAULT_CLIENT

IMAGE_DIR = DATA_DIR / "cache" / "replay_images"
VISION_MODEL = os.environ.get("DASHSCOPE_VISION_MODEL", "qwen-vl-plus")
_PROMPT = """这是A股券商APP的交割单或当日成交明细截图。
只输出JSON，不要markdown，不要解释。
字段：
{"date":"YYYY-MM-DD或空","trades":[{"time":"HH:MM","code":"6位数字","name":"简称","side":"买或卖","price":0,"qty":0}],"note":""}
规则：看不清就不要编；没有成交则 trades=[]；side只能是买或卖。
"""


def _decode_image(raw: str) -> tuple[bytes, str]:
    blob = (raw or "").strip()
    mime = "image/png"
    if blob.startswith("data:"):
        header, _, b64 = blob.partition(",")
        mime = header.replace("data:", "").split(";")[0] or mime
        blob = b64
    data = base64.b64decode(blob)
    if len(data) > 5 * 1024 * 1024:
        raise ValueError("截图超过 5MB，压一下再传")
    if len(data) < 32:
        raise ValueError("图片是空的")
    return data, mime


def _parse_json(text: str) -> Dict[str, Any]:
    match = re.search(r"\{[\s\S]*\}", text or "")
    if not match:
        return {"trades": [], "error": "模型没有返回JSON"}
    try:
        obj = json.loads(match.group(0))
    except json.JSONDecodeError:
        return {"trades": [], "error": "模型JSON无效"}
    trades = []
    for row in obj.get("trades") or []:
        code = re.sub(r"\D", "", str(row.get("code") or ""))[:6]
        side = str(row.get("side") or "")
        if "买" in side:
            side = "买"
        elif "卖" in side:
            side = "卖"
        else:
            continue
        trades.append(
            {
                "time": str(row.get("time") or ""),
                "code": code,
                "name": str(row.get("name") or ""),
                "side": side,
                "price": row.get("price"),
                "qty": row.get("qty"),
            }
        )
    return {
        "date": obj.get("date") or "",
        "trades": trades,
        "note": obj.get("note") or "",
        "error": "" if trades else (obj.get("note") or "没读到成交行"),
    }


def extract_trades(image_base64: str, mime: Optional[str] = None) -> Dict[str, Any]:
    key = os.environ.get("DASHSCOPE_API_KEY") or os.environ.get("NARRATIVE_LLM_KEY") or ""
    if not key:
        return {"trades": [], "error": "没配 DASHSCOPE_API_KEY，截图读不了。先粘贴成交文字。"}
    try:
        data, guessed = _decode_image(image_base64)
    except Exception as exc:  # noqa: BLE001
        return {"trades": [], "error": str(exc)}
    mime = mime or guessed
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    suffix = ".jpg" if "jpeg" in mime or "jpg" in mime else ".png"
    path = IMAGE_DIR / "{0}{1}".format(datetime.now().strftime("%Y%m%d_%H%M%S"), suffix)
    path.write_bytes(data)
    url = os.environ.get(
        "DASHSCOPE_COMPAT_URL",
        "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
    )
    data_url = "data:{0};base64,{1}".format(mime, base64.b64encode(data).decode("ascii"))
    try:
        payload = DEFAULT_CLIENT.post_json(
            url,
            json_body={
                "model": VISION_MODEL,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": data_url}},
                            {"type": "text", "text": _PROMPT},
                        ],
                    }
                ],
                "temperature": 0,
            },
            headers={"Authorization": "Bearer {0}".format(key)},
            timeout=90,
            attempts=2,
        )
        content = (((payload.get("choices") or [{}])[0].get("message") or {}).get("content")) or ""
    except Exception as exc:  # noqa: BLE001
        return {"trades": [], "error": "视觉接口失败：{0}".format(exc), "path": str(path)}
    parsed = _parse_json(content if isinstance(content, str) else json.dumps(content, ensure_ascii=False))
    parsed["path"] = str(path)
    parsed["model"] = VISION_MODEL
    if parsed.get("trades"):
        parsed["error"] = ""
    return parsed
