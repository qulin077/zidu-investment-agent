"""Trusted facts supplied by the runtime rather than guessed by the model."""
from __future__ import annotations

from datetime import datetime
import re


_WEEKDAYS = ("星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日")


def runtime_context(now: datetime | None = None) -> dict:
    """Return a compact, serialisable view of the process-local clock."""
    current = now or datetime.now().astimezone()
    if current.tzinfo is None:
        current = current.replace(tzinfo=datetime.now().astimezone().tzinfo)
    offset = current.strftime("%z")
    if len(offset) == 5:
        offset = f"{offset[:3]}:{offset[3:]}"
    return {
        "current_datetime": current.isoformat(timespec="seconds"),
        "current_date": current.date().isoformat(),
        "current_time": current.strftime("%H:%M:%S"),
        "weekday": _WEEKDAYS[current.weekday()],
        "timezone": current.tzname() or "local",
        "utc_offset": offset,
    }


def answer_environment_question(message: str, context: dict | None = None) -> str:
    """Answer only narrow clock/calendar questions from trusted runtime data.

    This intentionally is not a general intent router. Market dates, trading
    calendars and all external facts still belong to business tools.
    """
    text = re.sub(r"[\s，,。.!！?？]", "", (message or "").strip())
    text = re.sub(r"^(你好|您好|嗨|哈喽|请问|麻烦问一下)", "", text)
    env = context or runtime_context()

    if re.fullmatch(r"今天(?:是)?(?:几月几号|几号|什么日期|日期是多少)", text):
        return f"今天是 {env['current_date']}，{env['weekday']}。"
    if re.fullmatch(r"今天(?:是)?(?:星期几|周几)", text):
        return f"今天是 {env['weekday']}（{env['current_date']}）。"
    if re.fullmatch(r"(?:现在|当前)(?:是)?几点(?:了)?", text):
        return f"现在是 {env['current_time']}（{env['timezone']}，UTC{env['utc_offset']}）。"
    return ""
