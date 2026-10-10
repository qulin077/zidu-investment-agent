"""总控对话层：意图、槽位多轮、按房间装配上下文。

闲聊不能填槽。工作记忆有预算，会话本身不限 8 句。
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from core.chain_brief import resolve
from core.config import CONFIG_DIR, DATA_DIR
from core.store import STORE, Store

DIALOGUE_YAML = CONFIG_DIR / "dialogue.yaml"
SESSION_PATH = DATA_DIR / "cache" / "sessions" / "default.json"

_REPLAY_KW = ("收盘", "交割", "入库", "复盘", "对账", "预测", "执行力", "理解力", "闭环")
_MODE_KW = ("短线", "主升", "震荡", "景气", "风控", "用短线", "切到")
_BOARD_KW = ("看板", "环境", "数据状态")
_RESEARCH_KW = ("怎么样", "利好", "产业链", "行研", "研报", "英伟达", "长鑫", "估值")
_CHAT_EXACT = {
    "你好",
    "您好",
    "你好啊",
    "在吗",
    "在不在",
    "嗨",
    "哈喽",
    "hello",
    "hi",
    "hey",
    "谢谢",
    "谢谢你",
    "早上好",
    "晚上好",
    "午安",
    "早安",
    "嗯",
    "哦",
    "好",
    "好的",
    "ok",
    "okay",
}

_NOT_LOADED = (
    "02 笔记全文",
    "财报 PDF",
    "全部历史交割",
    "会话以外的闲聊",
    "人设语录库",
)


def load_dialogue_cfg(path: Path = DIALOGUE_YAML) -> Dict[str, Any]:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def is_chitchat(text: str) -> bool:
    q = re.sub(r"[\s!！。.?？,，~～]+", "", (text or "").strip()).lower()
    return q in _CHAT_EXACT or q in {item.lower() for item in _CHAT_EXACT}


def looks_like_slot(slot: str, text: str) -> bool:
    q = (text or "").strip()
    if not q or is_chitchat(q):
        return False
    if slot == "earning_type":
        return bool(re.search(r"E[1-7]", q, re.I)) or "说不清" in q or "违规" in q
    if slot == "fail":
        return any(k in q for k in ("止损", "失效", "跌破", "破位", "走", "MA", "均线", "卖出条件"))
    if slot == "score":
        return any(k in q for k in ("对", "错", "打分", "待验", "验", "✅", "❌", "P1", "P2", "P3"))
    if slot == "forecast":
        return len(q) >= 8 and any(
            k in q for k in ("明天", "窗口", "如果", "则", "日内", "T+", "T+1", "预期")
        )
    if slot == "trades":
        return bool(re.search(r"\d{6}", q)) or any(
            k in q for k in ("买", "卖", "流水", "交割", "截图")
        )
    if slot == "query":
        return len(q) >= 2
    if slot == "mode":
        return any(k in q for k in ("短线", "主升", "震荡", "景气", "风控"))
    return len(q) >= 8


def classify(text: str, store: Store = STORE) -> str:
    q = (text or "").strip()
    if not q:
        return "unknown"
    if is_chitchat(q):
        return "chat.hello"
    if "对账" in q or "验昨" in q or ("打分" in q and "预测" in q):
        return "replay.score"
    if any(k in q for k in _REPLAY_KW):
        return "replay.ingest"
    if any(k in q for k in _BOARD_KW) and not any(k in q for k in _RESEARCH_KW):
        return "board.look"
    if any(k in q for k in ("用短线", "切到主升", "用主升", "用震荡", "风控官", "换眼镜")):
        return "mode.set"
    resolved = resolve(q, store=store)
    kind = resolved.get("kind")
    if kind in ("company", "chain", "news"):
        return "research.ask"
    if any(k in q for k in _RESEARCH_KW):
        return "research.ask"
    if any(k in q for k in _MODE_KW) and len(q) < 20:
        return "mode.set"
    return "unknown"


def _room_for(intent: str, cfg: Dict[str, Any], fallback: str = "replay") -> str:
    spec = (cfg.get("intents") or {}).get(intent) or {}
    return spec.get("room") or fallback


def empty_session() -> Dict[str, Any]:
    return {
        "room": "replay",
        "intent": "",
        "mode": "",
        "slots": {},
        "history": [],
        "awaiting": "",
        "updated_at": "",
    }


def load_session(path: Path = SESSION_PATH) -> Dict[str, Any]:
    session = empty_session()
    if not path.exists():
        return session
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return session
    if isinstance(raw, dict):
        session.update(raw)
    if not isinstance(session.get("slots"), dict):
        session["slots"] = {}
    if not isinstance(session.get("history"), list):
        session["history"] = []
    return session


def save_session(session: Dict[str, Any], path: Path = SESSION_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    session["updated_at"] = datetime.now().isoformat(timespec="seconds")
    path.write_text(json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def reset_session(path: Path = SESSION_PATH) -> Dict[str, Any]:
    session = empty_session()
    save_session(session, path)
    return session


def _replay_gaps(
    store: Store = STORE,
    filled: Optional[Dict[str, str]] = None,
) -> List[Dict[str, str]]:
    from app.api.services import replay

    filled = filled or {}
    data = replay(store=store)
    cfg = load_dialogue_cfg()
    asks = {item["id"]: item["ask"] for item in cfg.get("replay_slots") or []}
    gaps: List[Dict[str, str]] = []
    if not data.get("trades") and "trades" not in filled:
        gaps.append({"slot": "trades", "ask": asks.get("trades", "请贴交割")})
        return gaps
    if data.get("missing_earning_type") and "earning_type" not in filled:
        gaps.append({"slot": "earning_type", "ask": asks.get("earning_type", "")})
    thin = [
        row
        for row in data.get("trades") or []
        if "买" in (row.get("side") or "") and len(row.get("reason") or "") < 8
    ]
    if thin and "fail" not in filled:
        gaps.append({"slot": "fail", "ask": asks.get("fail", "")})
    if (data.get("predictions") or {}).get("pending_count") and "score" not in filled:
        gaps.append({"slot": "score", "ask": asks.get("score", "")})
    if "forecast" not in filled:
        gaps.append({"slot": "forecast", "ask": asks.get("forecast", "")})
    return gaps


def next_ask(
    intent: str,
    store: Store = STORE,
    filled: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    if intent in ("replay.ingest", "replay.score"):
        gaps = _replay_gaps(store, filled=filled)
        if intent == "replay.score":
            score = next((g for g in gaps if g["slot"] == "score"), None)
            return score or {"slot": "", "ask": "待验已经对完，可以写今日预期。"}
        return gaps[0] if gaps else {"slot": "", "ask": "槽位已满，可以写成长记录那一条规则。"}
    if intent == "research.ask":
        return {"slot": "query", "ask": "行研在跑。看完简报后说要不要把预测草稿写入台账；也可以继续问估值、链条。"}
    if intent == "mode.set":
        return {"slot": "mode", "ask": "用哪一副眼镜？短线 / 主升 / 震荡 / 景气 / 风控。"}
    if intent == "board.look":
        return {"slot": "", "ask": "看板不聊天。环境看首页，有事件再走行研。"}
    if intent == "chat.hello":
        return {
            "slot": "",
            "ask": "复盘室在。打招呼不会跳过、也不会入库。收盘把交割单截图贴进来，或说「对账预测」。",
        }
    if intent == "chat.clarify":
        return {"slot": "", "ask": "这句话不像在答当前那一问。请按提示答，或换一张更清楚的截图。"}
    return {"slot": "", "ask": "没听懂要进复盘还是行研。复盘请丢交割；行研请点名公司、链条或新闻。"}


def context_pack(intent: str, query: str, store: Store = STORE) -> Dict[str, Any]:
    cfg = load_dialogue_cfg()
    room = _room_for(intent, cfg)
    pack: Dict[str, Any] = {"room": room, "read": [], "facts": {}}
    if room == "replay":
        pack["read"] = (cfg.get("context_budget") or {}).get("replay") or []
        from app.api.services import replay

        data = replay(store=store)
        pack["facts"] = {
            "asof": data.get("asof"),
            "n_trades": data.get("n_trades"),
            "unplanned": data.get("unplanned"),
            "pending_predictions": data.get("predictions", {}).get("pending_count"),
            "missing_earning_type": data.get("missing_earning_type"),
        }
    elif room == "research":
        pack["read"] = (cfg.get("context_budget") or {}).get("research") or []
        resolved = resolve(query, store=store)
        pack["facts"] = {
            "kind": resolved.get("kind"),
            "name": resolved.get("name") or resolved.get("code"),
            "tool": 'python3 scripts/research_run.py --q "{0}"'.format(query),
        }
    elif room == "modes":
        pack["read"] = (cfg.get("context_budget") or {}).get("modes") or []
    return pack


def _is_room_switch(query: str, classified: str) -> bool:
    if classified in ("research.ask", "board.look", "replay.ingest", "replay.score"):
        return True
    if classified == "mode.set" and any(
        k in query for k in ("用短线", "切到", "换眼镜", "风控官")
    ):
        return True
    return False


def _follow(classified: str, session: Dict[str, Any], query: str) -> Tuple[str, bool]:
    if classified == "chat.hello" or is_chitchat(query):
        return "chat.hello", False
    awaiting = session.get("awaiting") or ""
    last_intent = session.get("intent") or ""
    last_room = session.get("room") or ""
    if awaiting and last_intent and not _is_room_switch(query, classified):
        if looks_like_slot(awaiting, query):
            return last_intent, True
        return "chat.clarify", False
    if classified != "unknown":
        return classified, False
    if last_room == "research":
        return "research.ask", False
    if last_room == "replay" and last_intent:
        return last_intent, True
    return "unknown", False


def _vision_summary(vision: Dict[str, Any]) -> str:
    trades = vision.get("trades") or []
    if not trades:
        return vision.get("error") or "截图里没读到成交。"
    lines = ["从图里读到 {0} 笔：".format(len(trades))]
    for row in trades[:12]:
        lines.append(
            "{0} {1} {2} {3} × {4}".format(
                row.get("time") or "",
                row.get("side") or "",
                row.get("name") or row.get("code") or "",
                row.get("price") or "",
                row.get("qty") or "",
            ).strip()
        )
    return "\n".join(lines)


def turn(
    query: str,
    store: Store = STORE,
    persist: bool = True,
    session_path: Path = SESSION_PATH,
    vision: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    cfg = load_dialogue_cfg()
    session = load_session(session_path)
    text = (query or "").strip()
    if vision and (vision.get("trades") or vision.get("error")) and not text:
        text = "交割单截图"
    classified = classify(text, store=store)
    if vision and vision.get("trades"):
        classified = "replay.ingest"
    intent, filling = _follow(classified, session, text)
    if vision and vision.get("trades"):
        intent, filling = "replay.ingest", True
    room = _room_for(intent, cfg, fallback=session.get("room") or "replay")
    slots = dict(session.get("slots") or {})
    filled_this: Dict[str, str] = {}
    if classified not in ("unknown", "chat.hello", "chat.clarify") and room != (
        session.get("room") or room
    ):
        slots = {}
    awaiting = session.get("awaiting") or ""
    if filling and awaiting:
        payload = text
        if vision and vision.get("trades") and awaiting == "trades":
            payload = _vision_summary(vision)
        slots[awaiting] = payload
        filled_this[awaiting] = payload
    if vision and vision.get("trades"):
        slots["trades"] = _vision_summary(vision)
        filled_this["trades"] = slots["trades"]
        filling = True
        intent = "replay.ingest"
    anchor = text
    if intent == "research.ask" and classified == "unknown":
        for item in reversed(session.get("history") or []):
            if item.get("intent") == "research.ask" and item.get("classified") not in (
                "unknown",
                None,
                "chat.hello",
            ):
                anchor = item.get("text") or text
                break
    ask = next_ask(intent, store=store, filled=slots)
    if intent in ("chat.hello", "chat.clarify") and session.get("awaiting"):
        pending = next_ask(session.get("intent") or "replay.ingest", store=store, filled=slots)
        if intent == "chat.hello":
            ask = {
                "slot": pending.get("slot") or session.get("awaiting") or "",
                "ask": "复盘室在。打招呼不会跳过。还在等：{0}".format(pending.get("ask") or ""),
            }
        else:
            ask = {
                "slot": pending.get("slot") or session.get("awaiting") or "",
                "ask": "这句不像在答当前问题。还是这个问题：{0}".format(pending.get("ask") or ""),
            }
    if vision and vision.get("trades"):
        pending = next_ask("replay.ingest", store=store, filled=slots)
        ask = {
            "slot": pending.get("slot") or "",
            "ask": "{0}\n\n{1}".format(_vision_summary(vision), pending.get("ask") or "交割已读到，继续补逻辑。"),
        }
    elif vision and vision.get("error"):
        ask = {
            "slot": session.get("awaiting") or "trades",
            "ask": "截图没读清：{0}。再拍一张或直接粘贴成交文字。".format(vision.get("error")),
        }
        intent = "chat.clarify"
    pack = context_pack(
        "replay.ingest" if intent in ("chat.hello", "chat.clarify") and (session.get("room") == "replay") else intent,
        anchor,
        store=store,
    )
    history = list(session.get("history") or [])
    history.append(
        {
            "role": "user",
            "text": text,
            "intent": intent,
            "classified": classified,
            "image": bool(vision and (vision.get("trades") or vision.get("error"))),
        }
    )
    history.append(
        {
            "role": "assistant",
            "text": ask.get("ask") or "",
            "intent": intent,
            "slot": ask.get("slot") or "",
        }
    )
    budget = int((cfg.get("context_budget") or {}).get("max_history_turns") or 40)
    keep_room = session.get("room") or "replay"
    if intent not in ("chat.hello", "chat.clarify", "unknown"):
        keep_room = room
    keep_intent = session.get("intent") or ""
    if intent not in ("chat.hello", "chat.clarify"):
        keep_intent = intent
    keep_awaiting = ask.get("slot") or session.get("awaiting") or ""
    if intent not in ("chat.hello", "chat.clarify"):
        keep_awaiting = ask.get("slot") or ""
    session.update(
        {
            "room": keep_room,
            "intent": keep_intent,
            "slots": slots,
            "history": history[-budget:],
            "awaiting": keep_awaiting,
        }
    )
    if persist:
        save_session(session, session_path)
    followup = filling or (classified == "unknown" and intent not in ("unknown", "chat.hello", "chat.clarify"))
    from core.tools import next_tools

    planned = next_tools(intent, anchor)
    action = {
        "replay.ingest": "按收盘闭环补槽；缺的只问下一问。截图会走视觉识别。",
        "replay.score": "只对账待验预测，不要开新研究。",
        "research.ask": "调用 Tool research_run，再回答。",
        "mode.set": "调用 Tool personas_get。只改眼镜，不改 Gate。",
        "board.look": "调用 Tool board_get。看板不聊天。",
        "chat.hello": "闲聊，不填槽、不跳过。",
        "chat.clarify": "没听懂这一句，槽位保持不动。",
        "unknown": "先澄清房间。",
    }.get(intent, "")
    reply = ask.get("ask") or action
    return {
        "query": text,
        "intent": intent,
        "classified": classified,
        "room": keep_room,
        "followup": followup,
        "next": ask,
        "reply": reply,
        "action": action,
        "tools": planned,
        "filled": filled_this,
        "slots": slots,
        "vision": {
            "ok": bool(vision and vision.get("trades")),
            "n_trades": len((vision or {}).get("trades") or []),
            "error": (vision or {}).get("error") or "",
        }
        if vision
        else None,
        "context": pack,
        "window": {
            "max_history_turns": budget,
            "history_turns": len(session.get("history") or []),
            "prompt_turns": int((cfg.get("context_budget") or {}).get("prompt_turns") or 8),
            "loaded": pack.get("read") or [],
            "facts_keys": list((pack.get("facts") or {}).keys()),
            "not_loaded": list(_NOT_LOADED),
        },
        "history": session.get("history") or [],
        "history_turns": len(session.get("history") or []),
        "disclaimer": "研究框架，非投资建议。",
    }
