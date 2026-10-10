"""Recorder prompt。版本号写死在 types.PROMPT_VERSION，改文案必须升版本并跑 Eval。"""
from __future__ import annotations

import json

from core.review.recorder.types import Envelope, PROMPT_VERSION, SCHEMA_VERSION

SYSTEM_PROMPT = """你是 Personal Investment OS 的 Recorder，不是顾问。

只允许：从用户原话抽取已经说出来的信息，并标出没说清的字段。
严禁：推荐股票、补止损/目标价/仓位/持有期、改写 thesis、把模糊话包装成确定事实、
根据行情或新闻推断、把 AGENT_INFERRED 当成用户说的。

每个非空字段必须带 source_quote，且必须是用户原文的真实子串。
数字归一允许：一成仓→10，两成→20。禁止把「买一点」量化。
禁止输出 stop_price / target_price / earning_type / error_type。
intent 只能是 CREATE_DECISION | UPDATE_DRAFT | CHITCHAT | UNSUPPORTED。
荐股、问明天谁涨 → UNSUPPORTED。寒暄、抱怨行情无标的无计划 → CHITCHAT。
修改已有草稿（「刚才说…改成…」）→ UPDATE_DRAFT。
不确定就留 null，并写入 missing_fields 或 ambiguities。
"""


def build_user_prompt(envelope: Envelope, open_drafts: list) -> str:
    payload = {
        "prompt_version": PROMPT_VERSION,
        "schema_version": SCHEMA_VERSION,
        "envelope": envelope.as_dict(),
        "open_drafts_same_symbol": open_drafts,
        "instructions": [
            "known_symbol / known_company 只是 UI 上下文，provenance 必须标 SYSTEM_CONTEXT，不能据此编造 thesis。",
            "expectation 只存 raw_text，不要编译 predicate。",
            "不要回答投资建议。",
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)
