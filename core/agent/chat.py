"""没有技能要跑的时候，正常说话。"""
from __future__ import annotations

import json

from core.agent.environment import answer_environment_question, runtime_context

CHAT_PROMPT = """
你是用户长期使用的 Investment Agent。现在是自然对话，不调用研究技能。
结合最近对话接住用户当前这句话。用户表达情绪、抱怨、卖飞、后悔或困惑时，先回应其真实感受，
不要立刻说教，也不要把对话强行导向公司研究。必要时只问一个贴近上下文的问题。
优先回答用户当前真正问的事，不要因为历史里出现过某家公司就擅自把话题拉回去。
runtime_context 是运行环境提供的可信当前日期和时间；遇到日期、时间、星期问题直接据此回答。
如果涉及最新事实，不能凭记忆声称为最新，要说明需要走研究技能。
如果用户只是表达情绪或聊天，直接正常回应。
天气等需要外部实时数据的非投资任务，如果没有对应工具，简短说明不支持即可；不要借机罗列旧公司、旧决策或待办。
不要给买卖建议、目标价或仓位。
只输出 JSON：reply。
""".strip()

TOOL_RESULT_PROMPT = """
你是用户长期使用的 Investment Agent。工具已经执行完毕，下面的 tool_result 是本轮唯一可用的事实边界。
请把它整理成一段自然、连贯、像长期搭档一样的中文回答，而不是照搬内部工作流输出。
必须保留原文中的关键数字、日期、不确定性和 [C...] 引用；不得补充 tool_result 之外的事实。
如果原文说明“首次建立研究档案”“加载已有研究”“本轮搜索/新增”“已保存到本地”，这些研究生命周期信息也必须保留，
让用户能分清旧证据和本轮新增，而不是只看到一版无法判断新旧的结论。
工具失败时，直接说明卡在哪里以及用户怎样能帮你继续，不要伪装成功。
不要透露内部 skill、router、trace 等实现词，不给买卖建议、目标价或仓位。
只输出 JSON：reply。
""".strip()


def reply(message: str, llm=None, summary: dict | None = None, history: list | None = None) -> str:
    text = (message or "").strip()
    environment = runtime_context()
    direct_reply = answer_environment_question(text, environment)
    if direct_reply:
        return direct_reply
    if llm is not None:
        try:
            raw = llm.generate_structured(
                CHAT_PROMPT,
                json.dumps({
                    "message": text,
                    "runtime_context": environment,
                    "active_entity": (summary or {}).get("active_entity") or "",
                    "recent_conversation": [
                        {"role": row.get("role") or "user", "content": (row.get("content") or "")[:600]}
                        for row in (history or [])[-12:]
                    ],
                }, ensure_ascii=False),
                {"type": "object"},
                temperature=0.4,
                timeout=25,
            )
            data = json.loads(raw) if isinstance(raw, str) else {}
            spoken = (data.get("reply") or "").strip()
            if spoken:
                return spoken
        except Exception:
            pass
    if any(token in text for token in ("累", "很难", "想太多", "状态一般")):
        return "听起来今天挺消耗的。我在，你可以先把最难受的那一段说出来。"
    if text in {"你好", "您好", "你好啊", "在吗", "嗨", "哈喽"} or text.lower() in {"hi", "hello", "hey"}:
        return "在。今天想聊什么都可以。"
    return "我在听。你接着说就好。"


def present_tool_result(
    message: str,
    tool_result: str,
    skill: str,
    llm=None,
    summary: dict | None = None,
    history: list | None = None,
) -> str:
    """让模型负责表达，不让它越过工具结果的事实边界。"""
    result = (tool_result or "").strip()
    if not result or llm is None:
        return result
    try:
        raw = llm.generate_structured(
            TOOL_RESULT_PROMPT,
            json.dumps({
                "message": (message or "").strip(),
                "tool": skill,
                "tool_result": result,
                "active_entity": (summary or {}).get("active_entity") or "",
                "recent_conversation": [
                    {"role": row.get("role") or "user", "content": (row.get("content") or "")[:600]}
                    for row in (history or [])[-12:]
                ],
            }, ensure_ascii=False),
            {"type": "object"},
            temperature=0.25,
            timeout=30,
        )
        data = json.loads(raw) if isinstance(raw, str) else {}
        spoken = (data.get("reply") or "").strip()
        return spoken or result
    except Exception:
        return result
