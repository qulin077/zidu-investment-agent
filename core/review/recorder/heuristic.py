"""受限抽取器。没有 API key 时作为默认模型；也是 Eval 离线后端。

它只做原文匹配和明确数字归一，不调用外部模型，也不会补用户没说的止损/仓位。
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

from core.review.recorder.schema import empty_quoted
from core.review.recorder.types import Envelope
from core.symbols import load_universe, normalize_code

_SIZE_WORDS = {
    "一成": 10, "1成": 10, "二成": 20, "两成": 20, "2成": 20,
    "三成": 30, "3成": 30, "半成": 5, "五成": 50, "半仓": 50,
}
_CHITCHAT = (
    "你好", "您好", "谢谢", "哈哈", "真烦", "好累", "无聊", "天气",
)
_UNSUPPORTED = (
    "哪个涨", "哪些涨", "推荐", "买什么", "给个票", "你觉得明天",
    "帮我选", "最该买", "稳赚",
)
_UPDATE = ("改成", "改一下", "刚才说", "之前说", "修正为")
_POSTHOC = ("上午其实", "才买的", "已经买了", "我上午是因为", "昨晚大涨才买")
_FUZZY_SIZE = ("买一点", "买一些", "看看", "少量")
_NEGATION = ("不是说", "没说", "不代表", "没有打算", "不是跌破")
_CONTRAST_SKIP = ("不是我要买", "不是我要做", "不是我买")
_HISTORICAL = ("上次", "以前", "之前那次")
_HYPOTHETICAL = ("还没决定", "还没想好", "没决定做")


def _q(value: Any, quote: Optional[str], provenance: str = "USER_EXPLICIT") -> dict:
    return {"value": value, "source_quote": quote, "provenance": provenance}


def _empty() -> dict:
    return empty_quoted()


def _alias_map() -> List[Tuple[str, str, str]]:
    rows = []
    extra = {
        "特变": ("600089", "特变电工"),
        "特变电工": ("600089", "特变电工"),
        "中际": ("300308", "中际旭创"),
        "旭创": ("300308", "中际旭创"),
        "中际旭创": ("300308", "中际旭创"),
        "新易盛": ("300502", "新易盛"),
    }
    for name, (code, company) in extra.items():
        rows.append((name, code, company))
    for inst in load_universe():
        if inst.name:
            rows.append((inst.name, inst.code, inst.name))
    rows.sort(key=lambda r: -len(r[0]))
    return rows


def resolve_symbols(text: str) -> List[Tuple[str, str, str]]:
    found: List[Tuple[str, str, str]] = []
    seen = set()
    for name, code, company in _alias_map():
        if name and name in text and code not in seen:
            found.append((name, code, company))
            seen.add(code)
    for match in re.finditer(r"\b(\d{6})\b", text):
        code = normalize_code(match.group(1))
        if code not in seen:
            found.append((match.group(1), code, ""))
            seen.add(code)
    return found


def classify_intent(text: str, envelope: Envelope, has_open_draft: bool) -> str:
    compact = text.strip()
    if any(k in compact for k in _UNSUPPORTED):
        return "UNSUPPORTED"
    if any(k in compact for k in _UPDATE) and (has_open_draft or envelope.draft_id):
        return "UPDATE_DRAFT"
    size_or_plan = ("买", "仓", "成", "跌破", "回踩", "回调", "失效", "逻辑", "计划")
    if any(k in compact for k in _CHITCHAT) and not resolve_symbols(compact):
        if not any(k in compact for k in size_or_plan):
            return "CHITCHAT"
    if len(compact) <= 8 and not resolve_symbols(compact) and not envelope.known_symbol:
        if not any(k in compact for k in size_or_plan):
            return "CHITCHAT"
    return "CREATE_DECISION"


def _clause(text: str, keys: Tuple[str, ...]) -> Optional[str]:
    # 逗号优先：避免把「回踩…，跌破…，拿几天」整句塞进同一个字段。
    for part in re.split(r"[，,；;。！？\n]", text):
        piece = part.strip(" ，,")
        if piece and any(k in piece for k in keys):
            return piece
    return None


def _blocked_plan_clause(piece: str, full: str) -> bool:
    if any(k in piece for k in _NEGATION):
        return True
    if piece.startswith("不是") and any(k in piece for k in ("跌破", "卖", "止损")):
        return True
    if "观察位" in piece and "才算" not in piece and "失效" not in piece:
        return True
    if any(k in piece for k in _HISTORICAL) and any(k in full for k in ("这次", "还没想好", "还没决定")):
        return True
    if ("如果是" in piece or "假如" in piece) and any(k in full for k in _HYPOTHETICAL):
        return True
    if any(k in piece for k in ("还没想好", "还没决定", "没决定做", "还没定", "先不说")):
        return True
    return False


def _clauses(text: str, keys: Tuple[str, ...]) -> List[str]:
    out = []
    for part in re.split(r"[，,；;。！？\n]", text):
        piece = part.strip(" ，,")
        if piece and any(k in piece for k in keys):
            out.append(piece)
    return out


def _quote(text: str, fragment: str) -> str:
    return fragment if fragment in text else fragment


def extract(envelope: Envelope, has_open_draft: bool = False) -> dict:
    text = envelope.raw_text or ""
    intent = classify_intent(text, envelope, has_open_draft)
    blank = {
        "intent": intent,
        "symbol": _empty(),
        "thesis": _empty(),
        "market_context": _empty(),
        "expectations": [],
        "plan": {
            "entry_rule": _empty(),
            "invalidation": _empty(),
            "target_size_pct": _empty(),
            "holding_period": _empty(),
        },
        "missing_fields": [],
        "ambiguities": [],
        "unsupported_fields": [],
    }
    if intent in ("CHITCHAT", "UNSUPPORTED"):
        return blank

    symbols = resolve_symbols(text)
    filtered = []
    for name, code, company in symbols:
        idx = text.find(name)
        after = text[idx + len(name): idx + len(name) + 12] if idx >= 0 else ""
        if any(k in after or k in text[max(0, idx - 2): idx + len(name) + 12] for k in _CONTRAST_SKIP):
            continue
        if name + "不是" in text and "主要看" + name not in text and "先做" + name not in text:
            continue
        filtered.append((name, code, company))
    symbols = filtered or []
    if len(symbols) > 1:
        blank["ambiguities"].append("提到多个标的，未自动拆成多条 Decision")
        preferred = None
        for name, code, company in symbols:
            if any(tag + name in text for tag in ("优先", "先做", "只做", "只打算先做", "主要看")):
                preferred = (name, code, company)
                break
            if name + "优先" in text:
                preferred = (name, code, company)
                break
        name, code, company = preferred or symbols[0]
        blank["symbol"] = _q(code, name)
        others = [n for n, c, _ in symbols if c != code]
        if others:
            blank["ambiguities"].append("次要提及：" + "、".join(others))
    elif symbols:
        name, code, company = symbols[0]
        blank["symbol"] = _q(code, name)
    elif envelope.known_symbol:
        blank["symbol"] = _q(
            envelope.known_symbol, None, "SYSTEM_CONTEXT",
        )

    mkt = _clause(text, ("科技", "市场", "高位", "修复", "情绪", "行情"))
    if mkt and any(k in mkt for k in ("科技", "高位", "修复", "市场")):
        blank["market_context"] = _q(mkt, mkt)

    entry = None
    for piece in _clauses(text, ("回踩", "回调", "附近", "不破", "买入", "可以看", "可以买", "低开", "企稳")):
        if _blocked_plan_clause(piece, text):
            continue
        if "观察位" in piece:
            continue
        entry = piece
        break
    if entry:
        blank["plan"]["entry_rule"] = _q(entry, entry)

    inv = None
    for piece in _clauses(text, ("跌破", "失效", "就不看", "逻辑就算错", "止损", "才算")):
        if _blocked_plan_clause(piece, text):
            continue
        if "观察位" in piece and "才算" not in piece:
            continue
        inv = piece
        if "才算" in piece:
            break
    if inv:
        blank["plan"]["invalidation"] = _q(inv, inv)

    mentions = []
    for word, pct in _SIZE_WORDS.items():
        start = 0
        while True:
            pos = text.find(word, start)
            if pos < 0:
                break
            mentions.append((pos, word, pct))
            start = pos + 1
    for match in re.finditer(r"(\d+(?:\.\d+)?)\s*%\s*仓?", text):
        if "买一点" in text:
            continue
        mentions.append((match.start(), match.group(0), float(match.group(1))))
    mentions.sort()
    size_quote = size_val = None
    if mentions:
        if any(k in text for k in _HYPOTHETICAL) and any(k in text for k in ("如果是", "假如", "可能买")):
            size_quote = size_val = None
        elif any(k in text for k in ("改成", "算了")):
            size_quote, size_val = mentions[-1][1], mentions[-1][2]
            blank["ambiguities"].append("correction: 使用最后一次仓位表达")
        else:
            size_quote, size_val = mentions[0][1], mentions[0][2]
    fuzzy = any(w in text for w in _FUZZY_SIZE)
    if size_val is not None and not (fuzzy and size_quote is None):
        blank["plan"]["target_size_pct"] = _q(
            float(size_val), size_quote, "NORMALIZED_FROM_USER",
        )
    elif fuzzy:
        blank["ambiguities"].append("仓位表达模糊，不能量化")

    hold = None
    for piece in _clauses(text, ("交易日", "拿", "持有", "几天", "短线")):
        if _blocked_plan_clause(piece, text):
            continue
        if any(k in piece for k in ("交易日", "天", "拿")):
            hold = piece
            break
    if hold:
        blank["plan"]["holding_period"] = _q(hold, hold)

    exp = _clause(text, ("预计", "能够", "应该", "企稳", "强于", "未来", "如果继续"))
    if exp and exp != (blank["plan"]["entry_rule"] or {}).get("value"):
        blank["expectations"].append({
            "raw_text": exp,
            "source_quote": exp,
            "window": None,
            "confidence": None,
            "provenance": "USER_EXPLICIT",
        })
    elif blank["market_context"]["value"] and any(
        k in str(blank["market_context"]["value"]) for k in ("如果", "会", "应该", "预计")
    ):
        mkt = str(blank["market_context"]["value"])
        blank["expectations"].append({
            "raw_text": mkt,
            "source_quote": mkt,
            "window": None,
            "confidence": None,
            "provenance": "USER_EXPLICIT",
        })

    # thesis：带观点的短句，不编造
    thesis = _clause(text, ("想看", "觉得", "感觉", "挺强", "不错", "逻辑", "参与", "机会"))
    if not thesis:
        thesis = _clause(text, ("如果", "今天"))
    if thesis:
        blank["thesis"] = _q(thesis, thesis)
    elif blank["plan"]["entry_rule"]["value"]:
        # 有计划但没单独 thesis 时，不把 entry 冒充 thesis
        pass

    if any(k in text for k in ("应该也是", "记不清", "大概是", "好像")):
        blank["ambiguities"].append("retrospective / uncertain：不能写成 USER_EXPLICIT thesis")
        if blank["thesis"]["value"]:
            blank["thesis"] = _empty()

    if any(k in text for k in _POSTHOC) or envelope.mode == "posthoc":
        blank["ambiguities"].append("事后解释：不能改写成事前计划")

    return blank


class HeuristicLLM:
    """LLMClient 兼容：generate_structured 返回抽取 JSON 字符串。"""

    name = "recorder-heuristic-r1"

    def generate_structured(
        self,
        system: str,
        user: str,
        schema: dict,
        temperature: float = 0,
        timeout: int = 30,
    ) -> str:
        envelope_data = {}
        payload: Dict[str, Any] = {}
        try:
            payload = json.loads(user)
            envelope_data = payload.get("envelope") or {}
        except json.JSONDecodeError:
            envelope_data = {"raw_text": user}
        env = Envelope(
            raw_text=str(envelope_data.get("raw_text") or ""),
            recorded_at=str(envelope_data.get("recorded_at") or ""),
            source=str(envelope_data.get("source") or "web"),
            mode=str(envelope_data.get("mode") or ""),
            known_symbol=str(envelope_data.get("known_symbol") or ""),
            known_company=str(envelope_data.get("known_company") or ""),
            account=str(envelope_data.get("account") or ""),
            draft_id=str(envelope_data.get("draft_id") or ""),
        )
        has_open = bool(payload.get("open_drafts_same_symbol")) if isinstance(payload, dict) else False
        return json.dumps(extract(env, has_open), ensure_ascii=False)
