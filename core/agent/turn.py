"""一轮主对话：路由、装配上下文、调用已有工作流、把结果写回同一会话。"""
from __future__ import annotations

from threading import Lock
from typing import Callable, Optional

from core.agent import artifacts, goals, journal
from core.agent.compaction import compact
from core.agent.context import assemble
from core.agent.harness import AgentRuntime
from core.agent.market_tools import market_data_status, refresh_market_data
from core.agent.personal_context import (
    active_workflow,
    complete_workflow,
    link_context,
    planner_state,
    start_workflow,
    update_workflow,
)
from core.agent.planner import ModelActionPlanner
from core.agent.research_intake import apply_research_intake, resume_pending_intake
from core.agent.home import panel
from core.agent.metrics import snapshot
from core.agent.research_ref import confirm_thesis, thesis_label
from core.agent.review_view import format_review
from core.agent import chat
from core.agent.router import route
from core.agent.store import add_activity, add_message, dumps, list_messages, main_session, recent_messages, save_session
from core.agent.tool_registry import READ_ONLY, WRITE_DRAFT, ToolRegistry, ToolSpec
from core.research.decision_link import review_snapshot
from core.research.sessions import get_session as research_session
from core.store import Store

_BANNED = ("建议买入", "建议卖出", "推荐买入", "推荐卖出", "目标价")
_RESEARCH = {"company-research", "industry-research", "event-impact"}
_PRESENTABLE = _RESEARCH | {"event-impact", "candidate-discovery", "market-scan", "security-snapshot", "portfolio-monitor", "memory-query"}
_UNAVAILABLE = "当前语义模型暂时不可用。你可以继续说，我会尽量使用本地能力；涉及实时研究的问题暂时无法可靠完成。"


def handle(
    store: Store,
    message: str,
    network: str = "replay",
    use_llm: bool = False,
    llm=None,
    progress: Optional[Callable[[dict], object]] = None,
) -> dict:
    process = []
    process_lock = Lock()

    def report(phase: str, title: str, *, status: str = "running", detail: str = "") -> dict:
        with process_lock:
            event = {
                "seq": len(process) + 1,
                "phase": phase,
                "title": title,
                "detail": detail,
                "status": status,
            }
            process.append(event)
        if progress is not None:
            progress(dict(event))
        return event

    def research_progress(event: dict) -> None:
        public = _research_progress_event(event)
        if public:
            report(**public)

    session = main_session(store)
    history = recent_messages(store, session["id"], limit=12)
    report("intent", "正在理解你的问题", detail="结合当前对话和长期上下文判断这轮要做什么")
    model = llm
    if model is None and use_llm:
        from core.agent.runtime import runtime_llm
        model = runtime_llm()
    # The rule router is only a fallback now.  With a model available, the
    # model sees the conversation, state and tool catalog and owns the action.
    fallback = route(message, session, llm=None, messages=history)
    fallback = _resume_workflow_route(store, session, message, fallback)
    resumed = resume_pending_intake(message, session.get("summary") or {}, fallback)
    if resumed is not None:
        fallback = resumed
    planner = ModelActionPlanner(
        model, summary=session.get("summary") or {}, history=history, network=network,
        context_state=planner_state(store, session),
    ) if use_llm and model is not None else None
    if planner is not None:
        fallback_context = assemble(store, session, fallback, message)
        preview_registry = _build_tool_registry(
            store, session, fallback, fallback_context, message,
            network=network, use_llm=True, llm=model, history=history,
        )
        routed = planner.plan_turn(message, fallback, preview_registry.descriptions())
    else:
        routed = fallback
    routed = apply_research_intake(routed, message, session.get("summary") or {})
    skill = routed.get("skill") or "conversation"
    entity = routed.get("entity") or {}
    report(
        "intent",
        "已识别：{0}".format(_skill_label(skill)),
        status="completed",
        detail=(entity.get("name") or entity.get("code") or routed.get("intent") or "继续当前对话"),
    )
    context = assemble(store, session, routed, message)
    skill = routed.get("skill") or ""
    domain = routed.get("domain") or "GENERAL"
    entity = routed.get("entity") or {}
    user_message_id = add_message(
        store, session["id"], "user", message, domain=domain, skill=skill,
        entity_refs=[entity] if entity.get("name") or entity.get("code") else [],
        project_refs=[session.get("active_project_id")] if session.get("active_project_id") else [],
    )
    registry = _build_tool_registry(
        store, session, routed, context, message,
        network=network, use_llm=bool(use_llm and model is not None),
        llm=model if use_llm else None, history=history,
        research_progress=research_progress,
    )
    def runtime_event(event):
        row = add_activity(
            store, session_id=session["id"], project_id=session.get("active_project_id") or "",
            type=event.get("type") or "AGENT_ACTION", status=event.get("status") or "ok",
            summary=event.get("summary") or "", metadata=event.get("metadata") or {},
        )
        metadata = event.get("metadata") or {}
        tool = metadata.get("tool") or ""
        if event.get("type") == "AGENT_ACTION":
            report("tool", "正在执行：{0}".format(_skill_label(tool)), detail=_tool_detail(tool, network))
        elif event.get("type") == "AGENT_OBSERVATION":
            report(
                "tool",
                "已完成：{0}".format(_skill_label(tool)),
                status="completed" if event.get("status") != "gap" else "gap",
                detail=_safe_progress_detail(event.get("summary") or ""),
            )
        return row

    runtime = AgentRuntime(
        store, registry, session_id=session["id"],
        planner=planner,
        event_sink=runtime_event,
    )
    runtime_result = runtime.run(message, routed)
    outcome = runtime_result.outcome
    outcome["activities"] = sorted(
        list(outcome.get("activities") or []) + list(runtime_result.activities or []),
        key=lambda row: row.get("id") or "",
    )
    seen_activity_ids = {row.get("id") for row in (runtime_result.activities or [])}
    for activity in (() if outcome.get("_research_progress_streamed") else (outcome.get("activities") or [])):
        if activity.get("id") in seen_activity_ids:
            continue
        report(
            _activity_phase(activity.get("type") or ""),
            _activity_title(activity),
            status="gap" if activity.get("status") == "gap" else "completed",
            detail=_safe_progress_detail(activity.get("summary") or ""),
        )
    result_tool = outcome.get("_runtime_tool") or skill
    if result_tool in _PRESENTABLE and use_llm and model is not None:
        structured_company_report = (
            result_tool == "company-research"
            and "# 公司档案" in (outcome.get("answer") or "")
        )
        if structured_company_report:
            # The company workflow already produced a stable, evidence-linked
            # document contract.  A second prose pass would flatten its
            # sections and prevent the UI from rendering semantic HTML cards.
            report("synthesis", "结构化公司档案已生成", status="completed", detail="保留结论、变化、预期、风险和来源分区")
        else:
            report("synthesis", "正在整理证据并生成回答", detail="区分事实、判断和仍需确认的问题")
            outcome["answer"] = chat.present_tool_result(
                message,
                outcome.get("answer") or "",
                result_tool,
                llm=model,
                summary=session.get("summary") or {},
                history=history,
            )
            report("synthesis", "回答已生成", status="completed")
    answer = _scrub(outcome.get("answer") or "")
    journal_entry = _capture_journal(store, session, routed, message, user_message_id, skill)
    if journal_entry:
        report("memory", "已写入今天的对话日记", status="completed", detail=journal_entry.get("summary") or "")
    if journal_entry and any(token in message for token in ("记一下", "记下来", "记下", "记录一下")) and skill != "decision-recorder":
        answer = answer.rstrip() + "\n\n我把这段记进了今天的对话日记。"
    project_ref = outcome.get("project_id") or session.get("active_project_id") or ""
    add_message(
        store, session["id"], "assistant", answer, domain=domain, skill=skill,
        entity_refs=[entity] if entity.get("name") else [],
        project_refs=[project_ref] if project_ref else [],
        decision_refs=[outcome["decision_id"]] if outcome.get("decision_id") else [],
        claim_refs=outcome.get("claim_refs") or [],
        source_refs=outcome.get("source_refs") or [],
    )
    summary = dict(session.get("summary") or {})
    previous_name = summary.get("active_entity") or summary.get("entity_name") or ""
    summary["last_skill"] = skill or "chat"
    summary["last_intent"] = routed.get("intent") or ""
    summary["last_domain"] = domain
    summary["last_user"] = (message or "")[:80]
    intake_action = routed.get("intake_action") or ""
    if intake_action == "awaiting_focus":
        summary["pending_research_intake"] = routed.get("pending_research_intake") or {}
    elif intake_action in ("resolved", "cancelled"):
        pending = summary.pop("pending_research_intake", {}) or {}
        if intake_action == "resolved":
            focus_name = (routed.get("entity") or {}).get("name") or pending.get("entity_name") or ""
            if focus_name:
                preferences = dict(summary.get("research_preferences_by_entity") or {})
                preferences[focus_name] = {
                    "focus": routed.get("research_focus") or message[:160],
                    "category": routed.get("research_focus_category") or "CUSTOM",
                }
                summary["research_preferences_by_entity"] = preferences
    else:
        pending = summary.get("pending_research_intake") or {}
        routed_name = (routed.get("entity") or {}).get("name") or ""
        if (
            pending.get("status") == "AWAITING_FOCUS"
            and routed.get("skill") == "company-research"
            and routed_name
            and routed_name != pending.get("entity_name")
        ):
            summary.pop("pending_research_intake", None)
    summary["runtime"] = {
        "last_turn_id": runtime_result.turn_id,
        "last_steps_used": runtime_result.steps_used,
        "last_stop_reason": runtime_result.stop_reason,
        "max_steps": runtime.max_steps,
        "model": getattr(model, "name", "") if model is not None else "",
        "model_calls": int(getattr(model, "calls", 0) or 0) if model is not None else 0,
        "planning_mode": "model-loop" if planner is not None else "router-fallback",
    }
    summary["conversation_compaction"] = compact(
        store, session["id"], summary.get("conversation_compaction") or {}, keep_recent=12,
    )
    entity_name = outcome.get("entity_name") or ""
    entity_type = ((routed.get("entities") or [{}])[0].get("type") or "")
    chosen_name = ""
    chosen_code = ""
    if entity_name:
        chosen_name = entity_name
        chosen_code = outcome.get("entity_code") or ""
    elif (routed.get("entity") or {}).get("name") and entity_type != "technology_platform":
        chosen_name = routed["entity"]["name"]
        chosen_code = routed["entity"].get("code") or ""
    if chosen_name:
        summary["active_entity"] = chosen_name
        summary["entity_name"] = chosen_name
        if chosen_code:
            summary["entity_code"] = chosen_code
        elif chosen_name != previous_name:
            summary["entity_code"] = ""
    if skill == "event-impact" or outcome.get("active_event"):
        summary["active_event"] = outcome.get("active_event") or (routed.get("entity") or {}).get("name") or summary.get("active_event") or ""
    elif routed.get("context_event"):
        summary["active_event"] = summary.get("active_event") or routed.get("context_event") or ""
    elif skill in _RESEARCH and routed.get("reason_code") not in ("ACTIVE_PROJECT", "SECTION_FOCUS"):
        summary["active_event"] = ""
    if skill == "industry-research":
        summary["active_industry"] = (message or "")[:40]
    if outcome.get("open_questions"):
        summary["open_questions"] = outcome.get("open_questions") or []
    if skill in _RESEARCH and outcome.get("research_session_id"):
        summary["last_research_skill"] = skill
        summary["research_session_id"] = outcome["research_session_id"]
        if outcome.get("entity_name"):
            summary["entity_name"] = outcome["entity_name"]
        if outcome.get("entity_code"):
            summary["entity_code"] = outcome["entity_code"]
    if outcome.get("thesis_label"):
        summary["thesis_label"] = outcome["thesis_label"]
    if outcome.get("recorder_draft_id"):
        summary["pending_recorder_draft_id"] = outcome["recorder_draft_id"]
    if outcome.get("clear_pending_recorder"):
        summary.pop("pending_recorder_draft_id", None)
    project_id = outcome.get("project_id") or session.get("active_project_id") or ""
    fields = {
        "current_domain": domain,
        "active_project_id": project_id,
        "summary_json": dumps(summary),
    }
    if outcome.get("decision_id"):
        fields["active_decision_id"] = outcome["decision_id"]
    save_session(store, session["id"], **fields)
    if outcome.get("research_session_id") or outcome.get("artifact"):
        report("memory", "研究档案已更新", status="completed", detail=outcome.get("entity_name") or "长期研究记忆")
    report("done", "本轮完成", status="completed", detail="已保留可核对的执行记录")
    fresh = main_session(store)
    return {
        "ok": True,
        "session_id": session["id"],
        "skill": skill,
        "domain": domain,
        "reason_code": routed.get("reason_code") or "",
        "entity": entity,
        "answer": answer,
        "active_project_id": fresh.get("active_project_id") or "",
        "research_session_id": (fresh.get("summary") or {}).get("research_session_id") or "",
        "thesis_label": (fresh.get("summary") or {}).get("thesis_label") or "",
        "context": context,
        "activities": outcome.get("activities") or [],
        "artifact": outcome.get("artifact") or {},
        "research_status": outcome.get("research_status") or "",
        "research_delta": outcome.get("research_delta") or {},
        "research_memory": outcome.get("research_memory") or {},
        "journal_entry": journal_entry or {},
        "process": process,
        "recorder_draft_id": outcome.get("recorder_draft_id") or "",
        "summary": fresh.get("summary") or {},
        "messages": list_messages(store, session["id"]),
        "panel": panel(store, fresh),
        "metrics": snapshot(store),
        "runtime": {
            "turn_id": runtime_result.turn_id,
            "steps_used": runtime_result.steps_used,
            "stop_reason": runtime_result.stop_reason,
            "max_steps": runtime.max_steps,
            "model": getattr(model, "name", "") if model is not None else "",
            "model_calls": int(getattr(model, "calls", 0) or 0) if model is not None else 0,
            "planning_mode": "model-loop" if planner is not None else "router-fallback",
        },
    }


def _build_tool_registry(
    store, session, routed, context, message, network, use_llm,
    llm=None, history=None, research_progress=None,
) -> ToolRegistry:
    """Bind the current turn's trusted workflow adapters to explicit tools."""
    registry = ToolRegistry()

    def call_values(call):
        call_route = dict(call.arguments.get("route") or routed)
        call_message = call.arguments.get("message") or message
        call_context = context if call_route == routed and call_message == message else assemble(store, session, call_route, call_message)
        return call_route, call_message, call_context

    def conversation(call):
        call_route, call_message, _call_context = call_values(call)
        reason = call_route.get("reason_code") or ""
        if reason in ("AMBIGUOUS", "NEEDS_CLARIFICATION"):
            return _note(store, session, "要看哪一边？公司研究还是行业研究？", "SKILL_SELECTED", "等待澄清")
        if reason == "CLARIFY":
            return _note(store, session, "可以，你想看市场、某家公司，还是复盘最近的交易？", "SKILL_SELECTED", "等待澄清")
        if reason == "LLM_UNAVAILABLE":
            return _note(store, session, _UNAVAILABLE, "SKILL_SELECTED", "语义模型不可用")
        spoken = call_route.get("reply") or chat.reply(
            call_message, llm=llm, summary=session.get("summary") or {}, history=history or [],
        )
        return _note(store, session, spoken, "SKILL_SELECTED", "普通对话")

    def research(call):
        call_route, call_message, _call_context = call_values(call)
        if call_route.get("reason_code") == "SECTION_FOCUS":
            return _expand(store, session, call_route, call_message)
        research_message = call_route.get("research_query") or call_message
        return _research(
            store, session, call_route, research_message, network, use_llm, llm,
            progress=research_progress,
        )

    def candidates(call):
        call_route, call_message, _call_context = call_values(call)
        return _candidates(store, session, call_route, call_message, network)

    def recorder(call):
        call_route, call_message, _call_context = call_values(call)
        return _record(store, session, call_route, call_message, llm=llm)

    def review(call):
        call_route, call_message, call_context = call_values(call)
        return _review(store, session, call_route, call_context, call_message)

    def memory(call):
        _call_route, call_message, _call_context = call_values(call)
        return _memory(store, session, call_message)

    def security_snapshot(call):
        call_route, call_message, _call_context = call_values(call)
        from core.agent.security_snapshot import run
        result = run(
            store, call_message, call_route, network=network,
            summary=session.get("summary") or {},
        )
        activity = add_activity(
            store, session_id=session["id"], type="SECURITY_SNAPSHOT_READ",
            status="ok" if result.get("ok") else "gap",
            summary="{0} · {1}".format(
                result.get("entity_name") or "单只行情", result.get("entity_code") or "代码未确认",
            ),
            metadata={"skill": "security-snapshot"},
        )
        result.setdefault("activities", []).append(activity)
        return result

    def market_status(call):
        status = market_data_status(store)
        target = call.arguments.get("target_tool") or "market-scan"
        base_arguments = {
            "message": call.arguments.get("message") or message,
            "route": call.arguments.get("route") or routed,
        }
        activity = add_activity(
            store, session_id=session["id"], type="DATA_FRESHNESS_CHECKED",
            status="ok" if status["ok"] else "gap",
            summary=(
                "行情可用：{0}，覆盖 {1}/{2}".format(status["asof"], status["covered"], status["universe"])
                if status["ok"] else "行情过期：{0}".format("；".join(status["issues"]))
            ),
            metadata={"asof": status["asof"], "expected_asof": status["expected_asof"]},
        )
        if status["ok"]:
            return {
                "answer": "行情数据检查通过。", "activities": [activity],
                "market_data_status": status,
                "runtime_next_action": {"name": target, "arguments": base_arguments},
            }
        if network == "live":
            base_arguments["target_tool"] = target
            return {
                "answer": "本地行情已过期，正在刷新后再分析。", "activities": [activity],
                "market_data_status": status,
                "runtime_next_action": {"name": "market-data-refresh", "arguments": base_arguments},
            }
        return {
            "answer": (
                "我先检查了数据，发现本地行情截止 {0}，而这轮至少需要 {1}。"
                "联网刷新已关闭，所以我不能拿旧看板回答当前盘面。"
            ).format(status["asof"] or "无数据", status["expected_asof"]),
            "activities": [activity], "market_data_status": status,
        }

    def market_refresh(call):
        refreshed = refresh_market_data(store)
        target = call.arguments.get("target_tool") or "market-scan"
        status = refreshed["status"]
        activity = add_activity(
            store, session_id=session["id"], type="MARKET_DATA_REFRESHED",
            status="ok" if refreshed["ok"] else "gap",
            summary=(
                "行情刷新完成：{0}，覆盖 {1}/{2}".format(status["asof"], status["covered"], status["universe"])
                if refreshed["ok"] else "行情刷新后仍不可用：{0}".format("；".join(status["issues"]))
            ),
            metadata={"asof": status["asof"], "expected_asof": status["expected_asof"]},
        )
        if not refreshed["ok"]:
            detail = (refreshed.get("ingest") or {}).get("message") or "数据源没有返回足够的新行情"
            return {
                "ok": False, "status": "DATA_UNAVAILABLE", "error_code": "MARKET_DATA_STALE",
                "answer": (
                    "我发现看板行情截止 {0}，已经尝试联网刷新，但刷新后仍未达到 {1}。"
                    "原因：{2}。因此这轮不引用旧板块涨幅回答当前盘面。"
                ).format(status["asof"] or "无数据", status["expected_asof"], detail),
                "activities": [activity], "market_data_status": status,
            }
        return {
            "answer": "行情已刷新到 {0}。".format(status["asof"]),
            "activities": [activity], "market_data_status": status,
            "runtime_next_action": {
                "name": target,
                "arguments": {
                    "message": call.arguments.get("message") or message,
                    "route": call.arguments.get("route") or routed,
                },
            },
        }

    registry.register(ToolSpec("conversation", conversation, READ_ONLY, "自然聊天、接住情绪或提出一个澄清问题"))
    registry.register(ToolSpec("company-research", research, READ_ONLY, "核对一家公司的业务、财务、驱动、风险与未知项"))
    registry.register(ToolSpec("industry-research", research, READ_ONLY, "研究行业边界、价值链、供需、技术路线和竞争格局"))
    registry.register(ToolSpec("event-impact", research, READ_ONLY, "持续核对事件状态、增量、产业传导和业绩兑现"))
    registry.register(ToolSpec("candidate-discovery", candidates, READ_ONLY, "从已确认事件或主题发现相关公司并核对暴露"))
    registry.register(ToolSpec("market-scan", lambda _call: _market(store, session, network), READ_ONLY, "读取合格行情，分析盘面、板块强弱和风格"))
    registry.register(ToolSpec("security-snapshot", security_snapshot, READ_ONLY, "读取单只股票最新价格、K线并本地计算技术指标"))
    registry.register(ToolSpec("portfolio-monitor", lambda _call: _portfolio(store, session), READ_ONLY, "对照持仓、行情和研究查看变化"))
    registry.register(ToolSpec(
        "decision-recorder", recorder,
        WRITE_DRAFT, "决策草稿与确认写入", ("CONFIRM_DECISION", "CANCEL_DECISION"),
    ))
    registry.register(ToolSpec("guided-review", review, READ_ONLY, "复盘具体决策，对照当时 Thesis 与结果"))
    registry.register(ToolSpec("memory-query", memory, READ_ONLY, "查询已确认的个人模式、规则和历史经验"))
    registry.register(ToolSpec("market-data-status", market_status, READ_ONLY, "检查行情日期与覆盖率", internal=True))
    registry.register(ToolSpec("market-data-refresh", market_refresh, READ_ONLY, "联网刷新股票池行情", internal=True))
    return registry


def _research(store, session, routed, message, network, use_llm, llm=None, progress=None) -> dict:
    from core.research.workspace import run_turn

    summary = session.get("summary") or {}
    name = (routed.get("entity") or {}).get("name") or summary.get("entity_name") or ""
    routed_code = (routed.get("entity") or {}).get("code") or ""
    remembered_code = (
        (summary.get("entity_code") or "")
        if name == summary.get("entity_name") else ""
    )
    reuse = _reuse(store, summary, name, routed.get("reason_code") or "")
    provider = "ddgs" if (network or "replay") == "live" else "fixture"
    result = run_turn(
        store, message, session_id=reuse, mode="remote_shadow", network=network or "replay",
        search_provider=provider, use_llm=bool(use_llm), llm=llm, skill=routed.get("skill") or "",
        entity_hint={
            "name": name,
            "code": routed_code or remembered_code,
        },
        refresh_market=bool((network or "replay") == "live" and routed.get("skill") == "company-research"),
        progress=progress,
    )
    research_id = result.get("session_id") or reuse
    row = research_session(store, research_id) if research_id else {}
    body = (row or {}).get("summary") or {}
    entity_name = (row or {}).get("primary_entity_name") or name
    entity_code = (row or {}).get("primary_entity_code") or (routed.get("entity") or {}).get("code") or ""
    project_id = (row or {}).get("project_id") or research_id
    label = thesis_label(store, entity_name, research_id)
    artifact = artifacts.rebuild(store, project_id) if project_id else {}
    activities = _trace(store, session["id"], project_id, result.get("run_id") or "", result, body, routed.get("skill") or "")
    sources = []
    for item in body.get("sources") or []:
        url = item.get("url") or item.get("path") or ""
        if url:
            sources.append(url)
    answer = result.get("answer") or ""
    if result.get("status") == "INTERRUPTED":
        answer = answer or "这一轮研究中断了，没有把未完成的结果当成结论。"
    elif result.get("status") == "UNAVAILABLE" or "研究不可用" in answer:
        queries = result.get("queries") or []
        answer = "\n".join([
            "我认到了{0}，也尝试查了公开资料，但这轮找到的页面没有成功打开成可引用正文。".format(entity_name or "这家公司"),
            "我不想拿搜索摘要或模型记忆冒充最新事实，所以先停在这里。",
            "已经尝试：{0}".format("；".join(queries[:3]) if queries else "公司年报、公告和投资者关系资料"),
            "如果你给我股票代码或一条公告链接，我可以沿着它继续；当前失败不会被写成正式研究结论。",
        ])
    status = result.get("status") or ""
    completion = result.get("research_completion") or body.get("research_completion") or {}
    questions = list(body.get("open_questions") or [])[:6]
    if status == "UNAVAILABLE" or completion.get("status") == "SOURCE_UNAVAILABLE":
        stage = "SOURCE_UNAVAILABLE"
    elif completion.get("status") == "PARTIAL":
        stage = "COVERAGE_PARTIAL"
    elif completion.get("status") == "COMPLETE":
        stage = "COVERAGE_COMPLETE"
    else:
        stage = "OPEN_QUESTIONS" if questions else "DOSSIER_READY"
    strategy_id = session.get("active_strategy_id") or ""
    workflow_fields = {
        "strategy_id": strategy_id,
        "pending_question": questions[0] if questions else "",
        "state": {
            "research_session_id": research_id, "skill": routed.get("skill") or "",
            "research_mode": completion.get("mode") or "",
            "coverage_status": completion.get("status") or "",
            "coverage_missing": completion.get("missing_required") or [],
        },
    }
    if routed.get("skill") == "industry-research":
        workflow_fields["industry_project_id"] = project_id
    elif routed.get("skill") == "event-impact":
        workflow_fields["event_project_id"] = project_id
    else:
        workflow_fields["company_project_id"] = project_id
    workflow = start_workflow(store, session["id"], "RESEARCH", stage, **workflow_fields)
    if strategy_id and project_id:
        link_context(
            store, from_type="STRATEGY", from_id=strategy_id,
            relation="USES_RESEARCH", to_type="RESEARCH_PROJECT", to_id=project_id,
        )
    return {
        "answer": answer or "这轮研究没有写成回答。",
        "project_id": project_id,
        "research_session_id": research_id,
        "entity_name": entity_name,
        "entity_code": entity_code,
        "thesis_label": label,
        "claim_refs": result.get("claim_refs") or [],
        "source_refs": sources[:8],
        "open_questions": questions,
        "activities": activities,
        "artifact": artifact,
        "research_status": result.get("status") or "",
        "research_delta": result.get("research_delta") or {},
        "research_memory": result.get("research_memory") or {},
        "research_completion": completion,
        "workflow": workflow,
        "runtime_primary_deliverable": True,
        "runtime_terminal": True,
        "_research_progress_streamed": bool(progress),
    }


def _candidates(store, session, routed, message, network) -> dict:
    from core.agent.skill_runtime import run_candidates

    event = routed.get("context_event") or (session.get("summary") or {}).get("active_event") or (routed.get("entity") or {}).get("name") or ""
    result = run_candidates(message, event, network=network)
    activity = add_activity(
        store, session_id=session["id"], project_id=session.get("active_project_id") or "",
        type="SKILL_SELECTED", status="ok", summary="candidate-discovery · {0}".format(event or "主题"),
        metadata={"skill": "candidate-discovery"},
    )
    return {
        "answer": result["answer"],
        "activities": [activity],
        "active_event": event,
        "project_id": session.get("active_project_id") or "",
    }


def _market(store, session, network: str = "replay") -> dict:
    from core.agent.skill_runtime import run_market

    result = run_market(store, network=network)
    activity = add_activity(
        store, session_id=session["id"], type="SKILL_SELECTED", status="ok",
        summary="market-scan · iFinD + 本地行情", metadata={"skill": "market-scan"},
    )
    return {"answer": result["answer"], "activities": [activity], "project_id": session.get("active_project_id") or ""}


def _portfolio(store, session) -> dict:
    from core.agent.skill_runtime import run_portfolio

    result = run_portfolio(store, session.get("summary") or {})
    activity = add_activity(
        store, session_id=session["id"], type="SKILL_SELECTED", status="ok",
        summary="portfolio-monitor · 持仓", metadata={"skill": "portfolio-monitor"},
    )
    return {"answer": result["answer"], "activities": [activity], "project_id": session.get("active_project_id") or ""}


def _expand(store, session, routed, message) -> dict:
    project_id = session.get("active_project_id") or ""
    focus = message.replace("展开", "").strip() or "这一段"
    artifact = artifacts.rebuild(store, project_id, focus=focus) if project_id else {}
    activity = add_activity(
        store, session_id=session["id"], project_id=project_id, type="SKILL_SELECTED", status="ok",
        summary="继续「{0}」。没有整份重写。".format(focus), metadata={"skill": routed.get("skill") or ""},
    )
    gaps = ((artifact.get("data") or {}).get("variant_unknown") or [])
    gap_line = gaps[0] if gaps else "没有新的未知项。"
    return {
        "answer": "继续看这一段：{0}。没有整份重写。\n{1}".format(focus, gap_line),
        "project_id": project_id,
        "artifact": artifact,
        "activities": [activity],
        "thesis_label": (session.get("summary") or {}).get("thesis_label") or "",
    }


def _record(store, session, routed, message, llm=None) -> dict:
    from core.review.recorder import service as recorder

    summary = session.get("summary") or {}
    name = (routed.get("entity") or {}).get("name") or summary.get("entity_name") or ""
    code = (routed.get("entity") or {}).get("code") or summary.get("entity_code") or ""
    research_id = summary.get("research_session_id") or ""
    label = thesis_label(store, name, research_id)
    intent = routed.get("intent") or "DECISION_RECORD"
    pending = routed.get("pending_draft_id") or summary.get("pending_recorder_draft_id") or ""
    if intent == "CONFIRM_DECISION" and pending:
        try:
            saved = recorder.confirm(pending, confirmed=True, store=store)
        except Exception as exc:  # Write Gate 的错误要回到对话，不把请求炸成 500
            return {
                "answer": "这份草稿还不能保存：{0}".format(str(exc)),
                "project_id": session.get("active_project_id") or "",
                "recorder_draft_id": pending,
                "activities": [add_activity(
                    store, session_id=session["id"], type="DECISION_DRAFTED", status="gap",
                    summary="Recorder 草稿仍需补充。", metadata={"draft_id": pending},
                )],
            }
        decision_id = saved.get("decision_id") or ""
        workflow = _bind_confirmed_decision(store, session, decision_id)
        return {
            "answer": "已经保存这笔决策。{0}".format("编号：{0}".format(decision_id) if decision_id else ""),
            "decision_id": decision_id,
            "clear_pending_recorder": True,
            "project_id": session.get("active_project_id") or "",
            "workflow": workflow,
            "activities": [add_activity(
                store, session_id=session["id"], decision_id=decision_id,
                type="DECISION_CONFIRMED", status="ok", summary="Decision 已由用户确认保存。",
            )],
        }
    if intent == "CANCEL_DECISION" and pending:
        recorder.reject(pending, store=store)
        workflow = active_workflow(store, session["id"])
        if workflow and workflow.get("workflow_type") == "DECISION":
            complete_workflow(store, workflow["id"], status="CANCELLED")
        return {
            "answer": "好，这份决策草稿不保存。",
            "clear_pending_recorder": True,
            "project_id": session.get("active_project_id") or "",
            "activities": [add_activity(
                store, session_id=session["id"], type="DECISION_DRAFTED", status="ok",
                summary="用户放弃 Recorder 草稿。", metadata={"draft_id": pending},
            )],
        }
    parsed = recorder.parse(
        message, known_symbol=code, known_company=name, source="agent", mode="intraday",
        llm=llm, store=store,
    )
    draft = parsed.get("draft") or {}
    draft_id = parsed.get("draft_id") or ""
    activity = add_activity(
        store, session_id=session["id"], project_id=session.get("active_project_id") or "",
        type="DECISION_DRAFTED", status="ok" if parsed.get("status") != "FAILED" else "gap",
        summary="已见证原话并生成 Recorder 草稿；尚未写入 Decision。",
        metadata={"skill": "decision-recorder", "thesis_label": label, "draft_id": draft_id},
    )
    if parsed.get("status") == "FAILED":
        answer = "我先保留了你的原话，但这次没有成功整理成决策草稿。你可以补一句：标的、逻辑和什么情况下算判断失效。"
    else:
        answer = _format_recorder_draft(draft, label, parsed.get("ask") or "")
    missing = list(draft.get("missing_fields") or [])
    workflow = start_workflow(
        store,
        session["id"],
        "DECISION",
        "MISSING_FIELDS" if missing else "AWAITING_CONFIRMATION",
        strategy_id=session.get("active_strategy_id") or "",
        company_project_id=session.get("active_project_id") or "",
        draft_id=draft_id,
        pending_question=parsed.get("ask") or "请确认或取消这份 Decision 草稿。",
        state={"missing_fields": missing, "thesis_label": label},
    )
    return {
        "answer": answer,
        "project_id": session.get("active_project_id") or "",
        "thesis_label": label,
        "recorder_draft_id": draft_id,
        "workflow": workflow,
        "activities": [activity],
    }


def _format_recorder_draft(draft: dict, label: str, ask: str) -> str:
    def value(row):
        return (row or {}).get("value") if isinstance(row, dict) else row

    plan = draft.get("plan") or {}
    lines = ["Based on: {0}".format(label), "", "我先按你的原话整理成一份待确认草稿："]
    symbol = value(draft.get("symbol"))
    thesis = value(draft.get("thesis"))
    if symbol:
        lines.append("- 标的：{0}".format(symbol))
    if thesis:
        lines.append("- 你的逻辑：{0}".format(thesis))
    size = value(plan.get("target_size_pct"))
    invalidation = value(plan.get("invalidation"))
    holding = value(plan.get("holding_period"))
    if size not in (None, ""):
        lines.append("- 目标仓位：{0}".format(size))
    if invalidation:
        lines.append("- 失效条件：{0}".format(invalidation))
    if holding:
        lines.append("- 持有周期：{0}".format(holding))
    lines.append("- 研究依据：{0}".format(label))
    missing = list(draft.get("missing_fields") or [])
    if missing:
        lines.append("还缺：{0}".format("、".join(missing)))
    lines.append(ask or "如果这份草稿准确，回复“确认保存”；不想保存就说“取消”。")
    return "\n".join(lines)


def _capture_journal(store, session, routed, message, source_message_id, skill) -> dict:
    proposal = routed.get("journal") or {}
    text = (message or "").strip()
    explicit = any(token in text for token in ("帮我记一下", "帮我记下", "记下来", "记录一下"))
    feelings = any(token in text for token in ("难受", "后悔", "烦", "好累", "太累", "焦虑", "害怕", "心情", "抱怨", "卖飞"))
    trade_note = any(token in text for token in ("买了", "卖了", "卖飞", "追高", "割了", "加仓", "减仓", "冲动"))
    should_save = bool(proposal.get("save")) or explicit or (feelings and skill not in _RESEARCH)
    if not should_save or skill == "decision-recorder":
        return {}
    kind = proposal.get("entry_type") or ("TRADE_NOTE" if trade_note else "FEELING" if feelings else "THOUGHT")
    entities = routed.get("entities") or []
    entry = journal.save(
        store,
        session_id=session["id"],
        source_message_id=source_message_id,
        raw_text=text,
        summary=proposal.get("summary") or text,
        entry_type=kind,
        entity_refs=entities,
    )
    add_activity(
        store, session_id=session["id"], project_id=session.get("active_project_id") or "",
        type="JOURNAL_SAVED", status="ok", summary="已记入今天的对话日记。",
        metadata={"journal_id": entry.get("id") or "", "entry_type": entry.get("entry_type") or ""},
    )
    return entry


def _review(store, session, routed, context, message) -> dict:
    decision = (context.get("packet") or {}).get("decision")
    if not decision:
        activity = add_activity(
            store, session_id=session["id"], type="REVIEW_STARTED", status="gap",
            summary="还没指定要复盘的 Decision。",
        )
        return {"answer": format_review({}), "activities": [activity], "project_id": session.get("active_project_id") or ""}
    snapshot = review_snapshot(decision["id"], store)
    activity = add_activity(
        store, session_id=session["id"], decision_id=decision["id"],
        project_id=session.get("active_project_id") or "",
        type="REVIEW_STARTED", status="ok",
        summary="并列 Decision-time Thesis 和当前 Thesis。",
    )
    decision_rows = store.query("SELECT status FROM decision WHERE id = ?", (decision["id"],))
    if decision_rows and decision_rows[0].get("status") == "REVIEW_PENDING":
        guided_result = _guided_review_turn(store, session, decision["id"], message)
        guided_result.setdefault("activities", []).insert(0, activity)
        guided_result.setdefault("project_id", session.get("active_project_id") or "")
        return guided_result
    return {
        "answer": format_review(snapshot),
        "decision_id": decision["id"],
        "activities": [activity],
        "project_id": session.get("active_project_id") or "",
    }


def _resume_workflow_route(store, session, message, fallback):
    workflow = active_workflow(store, session.get("id") or "")
    if not workflow or workflow.get("workflow_type") != "GUIDED_REVIEW":
        return fallback
    compact = "".join((message or "").split())
    if compact in ("暂停复盘", "先不复盘", "取消复盘"):
        complete_workflow(store, workflow["id"], status="PAUSED")
        planned = dict(fallback)
        planned.update({
            "mode": "CHAT", "skill": "", "domain": "GENERAL", "intent": "PAUSE_REVIEW",
            "reply": "好，这次复盘先暂停。进度已经保留，之后说“继续复盘”可以接着来。",
            "reason_code": "WORKFLOW_PAUSED", "write_action": False,
        })
        return planned
    if fallback.get("skill") not in ("", "guided-review") and fallback.get("mode") == "SKILL":
        return fallback
    planned = dict(fallback)
    planned.update({
        "mode": "SKILL", "skill": "guided-review", "domain": "REVIEW",
        "intent": "GUIDED_REVIEW_CONTINUE", "reason_code": "ACTIVE_WORKFLOW",
        "need_decision_memory": True, "write_action": False,
        "entity": {}, "entities": [],
    })
    return planned


def _bind_confirmed_decision(store, session, decision_id: str) -> dict:
    strategy_id = session.get("active_strategy_id") or ""
    project_id = session.get("active_project_id") or ""
    if decision_id and strategy_id:
        with store.connect() as conn:
            conn.execute("UPDATE decision SET strategy_id = ? WHERE id = ?", (strategy_id, decision_id))
        link_context(
            store, from_type="STRATEGY", from_id=strategy_id,
            relation="GOVERNS_DECISION", to_type="DECISION", to_id=decision_id,
            source="user", user_confirmed=True,
        )
    if decision_id and project_id:
        link_context(
            store, from_type="DECISION", from_id=decision_id,
            relation="BASED_ON", to_type="RESEARCH_PROJECT", to_id=project_id,
            source="user", user_confirmed=True,
        )
    research_id = (session.get("summary") or {}).get("research_session_id") or ""
    research = research_session(store, research_id) if research_id else {}
    thesis_id = (research or {}).get("current_thesis_id") or ""
    thesis_version = int((research or {}).get("current_thesis_version") or 0)
    thesis_project = (research or {}).get("project_id") or project_id
    if decision_id and thesis_project and thesis_id and thesis_version:
        confirm_thesis(store, decision_id, thesis_project, thesis_id, thesis_version)
    current = active_workflow(store, session["id"])
    if current and current.get("workflow_type") == "DECISION":
        return update_workflow(
            store, current["id"], stage="WAITING_EXECUTION", decision_id=decision_id,
            strategy_id=strategy_id, company_project_id=project_id,
            draft_id="", pending_question="等待成交导入或计划更新。",
        )
    return start_workflow(
        store, session["id"], "DECISION", "WAITING_EXECUTION",
        strategy_id=strategy_id, company_project_id=project_id,
        decision_id=decision_id, pending_question="等待成交导入或计划更新。",
    )


def _guided_review_turn(store, session, decision_id: str, message: str) -> dict:
    from core.review.guided import service as guided

    workflow = active_workflow(store, session["id"])
    if not workflow or workflow.get("workflow_type") != "GUIDED_REVIEW" or workflow.get("decision_id") != decision_id:
        started = guided.start(decision_id, store=store)
        return _save_guided_turn(store, session, decision_id, started)

    stage = workflow.get("stage") or ""
    compact = "".join((message or "").split()).lower()
    yes = compact in ("确认", "确认无误", "是", "对", "没问题", "yes", "y")
    if stage == "OUTCOME":
        if not yes:
            return _guided_retry(workflow, "Outcome 尚未确认。请核对详情；确认无误后回复“确认”。")
        return _save_guided_turn(store, session, decision_id, guided.confirm_outcome(decision_id, store=store))
    if stage == "VIOLATIONS":
        if not yes:
            return _guided_retry(workflow, "流程违规尚未确认。请核对后回复“确认”，或到 Review 详情页修正事实。")
        return _save_guided_turn(store, session, decision_id, guided.confirm_violations(decision_id, store=store))
    if stage == "ATTRIBUTION":
        primary = _attribution_type(message)
        if not primary:
            return _guided_retry(
                workflow,
                "请明确选择主要归因：研究、预期、择时、仓位、执行、风控、情绪、流程、外部冲击或无错误。",
            )
        guided.answer(decision_id, answer_text=message, option_id=primary, store=store)
        guided.confirm_attribution(decision_id, primary, store=store)
        if primary == "RESEARCH_ERROR":
            from core.agent.research_feedback import propose

            propose(
                store, decision_id, message,
                evidence=["decision.thesis", "guided_review.user_attribution"],
            )
        next_turn = guided.start(decision_id, store=store)
        return _save_guided_turn(store, session, decision_id, next_turn)
    if stage == "LESSON":
        if len((message or "").strip()) < 2:
            return _guided_retry(workflow, "请写一句下次可执行的纪律或过程提醒。")
        guided.answer(decision_id, answer_text=message, store=store)
        completed = guided.complete(decision_id, lesson=message.strip(), store=store)
        complete_workflow(store, workflow["id"])
        return {
            "answer": "这次复盘已经完成。Lesson：{0}。它不会自动升级成 Rule；只有重复出现并经你确认后才会进入规则。".format(message.strip()),
            "decision_id": decision_id,
            "review_id": completed.get("review_id") or "",
            "workflow": {},
        }
    started = guided.start(decision_id, store=store)
    return _save_guided_turn(store, session, decision_id, started)


def _save_guided_turn(store, session, decision_id: str, payload: dict) -> dict:
    turn = payload.get("turn") or {}
    stage = payload.get("unresolved") or turn.get("unresolved_dimension") or "LESSON"
    question = turn.get("question") or "继续这次复盘。"
    current = active_workflow(store, session["id"])
    fields = {
        "decision_id": decision_id,
        "review_id": (payload.get("facts") or {}).get("review_id") or "",
        "pending_question": question,
        "state": {"turn": turn, "guided_session_id": payload.get("session_id") or ""},
    }
    if current and current.get("workflow_type") == "GUIDED_REVIEW":
        workflow = update_workflow(store, current["id"], stage=stage, **fields)
    else:
        workflow = start_workflow(store, session["id"], "GUIDED_REVIEW", stage, **fields)
    return {
        "answer": _format_guided_question(turn),
        "decision_id": decision_id,
        "review_id": fields["review_id"],
        "workflow": workflow,
    }


def _guided_retry(workflow: dict, answer: str) -> dict:
    return {"answer": answer, "decision_id": workflow.get("decision_id") or "", "workflow": workflow}


def _format_guided_question(turn: dict) -> str:
    lines = [turn.get("question") or "继续这次复盘。"]
    for option in turn.get("options") or []:
        lines.append("- {0}：{1}".format(option.get("id") or "", option.get("label") or ""))
    return "\n".join(lines)


def _attribution_type(message: str) -> str:
    text = (message or "").upper()
    mapping = (
        (("无错误", "没有错误", "NONE"), "NONE"),
        (("研究", "RESEARCH_ERROR"), "RESEARCH_ERROR"),
        (("预期", "EXPECTATION_ERROR"), "EXPECTATION_ERROR"),
        (("择时", "时机", "TIMING_ERROR"), "TIMING_ERROR"),
        (("仓位", "SIZING_ERROR"), "SIZING_ERROR"),
        (("执行", "EXECUTION_ERROR"), "EXECUTION_ERROR"),
        (("风控", "止损", "RISK_CONTROL_ERROR"), "RISK_CONTROL_ERROR"),
        (("情绪", "FOMO", "EMOTION_ERROR"), "EMOTION_ERROR"),
        (("流程", "PROCESS_ERROR"), "PROCESS_ERROR"),
        (("外部", "冲击", "EXTERNAL_SHOCK"), "EXTERNAL_SHOCK"),
    )
    for tokens, value in mapping:
        if any(token.upper() in text for token in tokens):
            return value
    return ""


def _memory(store, session, message) -> dict:
    patterns = store.query("SELECT id, pattern_key, summary, status FROM pattern ORDER BY created_at DESC")
    rules = store.query("SELECT id, rule_text, status FROM rule WHERE status = 'ACTIVE'")
    pattern_hits = [row for row in patterns if _pattern_hit(message, row)]
    rule_hits = [row for row in rules if _rule_hit(message, row.get("rule_text") or "")]
    lines = ["从 Personal Decision Memory 里查 Pattern 和 Rule。不从聊天记录编造。"]
    if pattern_hits:
        lines.append("Pattern")
        for row in pattern_hits[:5]:
            lines.append("- {0} · {1} · {2}".format(row["pattern_key"], row["status"], row.get("summary") or ""))
    if rule_hits:
        lines.append("Rule")
        for row in rule_hits[:5]:
            lines.append("- {0}".format(row["rule_text"]))
    if not pattern_hits and not rule_hits:
        lines.append("记忆里还没有和这句对得上的已确认 Pattern。")
    activities = [add_activity(
        store, session_id=session["id"], type="PATTERN_FOUND",
        status="ok" if pattern_hits else "gap",
        summary="命中 {0} 条 Pattern。".format(len(pattern_hits)),
    )]
    if rule_hits:
        activities.append(add_activity(
            store, session_id=session["id"], type="RULE_TRIGGERED", status="ok",
            summary=rule_hits[0]["rule_text"][:80],
            metadata={"rule_id": rule_hits[0]["id"]},
        ))
    return {"answer": "\n".join(lines), "activities": activities, "project_id": session.get("active_project_id") or ""}


def _note(store, session, answer, activity_type, summary) -> dict:
    activity = add_activity(
        store, session_id=session["id"], project_id=session.get("active_project_id") or "",
        type=activity_type, status="ok", summary=summary,
    )
    return {"answer": answer, "activities": [activity], "project_id": session.get("active_project_id") or ""}


def _reuse(store, summary, name, reason) -> str:
    preferred = summary.get("research_session_id") or ""
    if reason in ("ACTIVE_PROJECT", "SECTION_FOCUS", "SAME_ENTITY") and preferred:
        return preferred
    if not name:
        return ""
    rows = store.query(
        "SELECT id FROM research_session WHERE primary_entity_name = ? ORDER BY updated_at DESC LIMIT 1",
        (name,),
    )
    return rows[0]["id"] if rows else ""


def _trace(store, session_id, project_id, run_id, result, body, skill) -> list:
    entity = result.get("entity") or {}
    name = entity.get("canonical_name") or entity.get("name") or ""
    ticker = entity.get("ticker") or ""
    rows = [
        add_activity(
            store, session_id=session_id, project_id=project_id, run_id=run_id,
            type="ENTITY_RESOLVED", status="ok" if name else "gap",
            summary="{0} {1}".format(name, ticker).strip() or "没有解析出实体",
        ),
        add_activity(
            store, session_id=session_id, project_id=project_id, run_id=run_id,
            type="SKILL_SELECTED", status="ok", summary=skill,
            metadata={"skill": skill},
        ),
    ]
    tasks = ((result.get("plan") or body.get("plan") or {}).get("tasks") or [])
    execution = ((result.get("plan") or body.get("plan") or {}).get("execution") or {})
    if tasks:
        hypotheses = execution.get("hypotheses") or []
        parallel = execution.get("parallel_skills") or []
        plan_summary = "Planner：{0} 个可验证假设，按证据收敛停止".format(
            len(hypotheses) or len(tasks),
        ) if execution else "{0} 个研究问题".format(len(tasks))
        if parallel:
            plan_summary += "；首轮并行 {0} 个来源 Skill".format(len(parallel))
        rows.append(add_activity(
            store, session_id=session_id, project_id=project_id, run_id=run_id,
            type="PLAN_CREATED", status="ok", summary=plan_summary,
        ))
    completed = execution.get("completed_actions") or []
    if completed:
        for step in completed:
            if step.get("action") == "PARALLEL_SKILL":
                summary_text = "{0} · {1} · 打开 {2} 份正文".format(
                    step.get("label") or step.get("skill") or "来源核对",
                    step.get("reason") or "独立证据",
                    step.get("sources_opened") or 0,
                )
                activity_type = "SOURCE_SKILL_COMPLETED"
            else:
                summary_text = "第{0}轮：搜「{1}」— {2}".format(
                    step.get("wave") or "?", step.get("query") or "",
                    step.get("reason") or "补齐证据缺口",
                )
                activity_type = "PLANNER_STEP"
            rows.append(add_activity(
                store, session_id=session_id, project_id=project_id, run_id=run_id,
                type=activity_type, status="ok" if step.get("sources_opened") or activity_type == "PLANNER_STEP" else "gap",
                summary=summary_text,
                metadata={"coverage_after": step.get("coverage_after") or {}, "skill": step.get("skill") or ""},
            ))
        if execution.get("stop_reason"):
            rows.append(add_activity(
                store, session_id=session_id, project_id=project_id, run_id=run_id,
                type="PLANNER_STOP", status="ok", summary="停止：" + execution["stop_reason"],
            ))
    else:
        queries = result.get("queries") or []
        if queries:
            rows.append(add_activity(
                store, session_id=session_id, project_id=project_id, run_id=run_id,
                type="SEARCH_STARTED", status="ok", summary="、".join(queries[:3]),
            ))
    for source in (body.get("sources") or [])[:6]:
        rows.append(add_activity(
            store, session_id=session_id, project_id=project_id, run_id=run_id,
            type="SOURCE_OPENED", status="ok",
            summary=source.get("title") or source.get("url") or "来源",
        ))
    claims = body.get("claims") or []
    rows.append(add_activity(
        store, session_id=session_id, project_id=project_id, run_id=run_id,
        type="CLAIMS_EXTRACTED", status="ok" if claims else "gap",
        summary="提取 {0} 条 Claim".format(len(claims)),
    ))
    gaps = body.get("open_questions") or []
    if gaps:
        rows.append(add_activity(
            store, session_id=session_id, project_id=project_id, run_id=run_id,
            type="GAP_FOUND", status="gap", summary=gaps[0],
        ))
    completion = result.get("research_completion") or body.get("research_completion") or {}
    if completion:
        rows.append(add_activity(
            store, session_id=session_id, project_id=project_id, run_id=run_id,
            type="COVERAGE_CHECKED", status="ok" if completion.get("passed") else "gap",
            summary="{0} · {1}/{2} 项通过 · {3}".format(
                completion.get("status") or "PARTIAL",
                completion.get("passed_count") or 0,
                completion.get("checked_count") or 0,
                completion.get("completion_reason") or "",
            ),
            metadata={
                "mode": completion.get("mode") or "",
                "missing_required": completion.get("missing_required") or [],
                "attempted_unavailable": completion.get("attempted_unavailable") or [],
            },
        ))
    rows.append(add_activity(
        store, session_id=session_id, project_id=project_id, run_id=run_id,
        type="THESIS_UPDATED", status="ok",
        summary="草稿已更新，未写入正式 Thesis",
    ))
    return rows


_SKILL_LABELS = {
    "conversation": "继续对话",
    "company-research": "公司研究",
    "industry-research": "行业研究",
    "event-impact": "事件影响分析",
    "candidate-discovery": "相关公司核对",
    "market-scan": "盘面分析",
    "security-snapshot": "个股行情与技术面",
    "portfolio-monitor": "持仓变化检查",
    "decision-recorder": "交易想法记录",
    "guided-review": "决策复盘",
    "memory-query": "长期记忆检索",
    "market-data-status": "行情日期检查",
    "market-data-refresh": "最新行情刷新",
}

_ACTIVITY_LABELS = {
    "ENTITY_RESOLVED": "已确认研究对象",
    "SKILL_SELECTED": "已选择处理方式",
    "PLAN_CREATED": "研究计划已生成",
    "PLANNER_STEP": "正在补齐证据",
    "SOURCE_SKILL_COMPLETED": "来源 Skill 已完成",
    "PLANNER_STOP": "证据搜集已停止",
    "SEARCH_STARTED": "正在搜索公开资料",
    "SOURCE_OPENED": "已读取来源",
    "CLAIMS_EXTRACTED": "已提取可引用事实",
    "COVERAGE_CHECKED": "研究覆盖合同已验收",
    "GAP_FOUND": "发现仍需确认的问题",
    "THESIS_UPDATED": "研究草稿已更新",
    "DATA_FRESHNESS_CHECKED": "已检查行情日期",
    "MARKET_DATA_REFRESHED": "行情刷新完成",
    "SECURITY_SNAPSHOT_READ": "已读取个股行情与技术面",
    "PATTERN_FOUND": "已查询历史模式",
    "RULE_TRIGGERED": "已匹配个人规则",
    "JOURNAL_SAVED": "已保存对话日记",
    "REVIEW_STARTED": "已读取决策上下文",
}


def _skill_label(skill: str) -> str:
    return _SKILL_LABELS.get(skill or "", skill or "继续对话")


def _tool_detail(tool: str, network: str) -> str:
    if tool in ("company-research", "industry-research", "event-impact", "candidate-discovery"):
        return "读取已有研究，并{0}核对新增资料".format("联网" if network == "live" else "使用本地资料")
    if tool == "market-data-status":
        return "先验证数据日期和覆盖率，避免拿旧看板回答今天"
    if tool == "market-data-refresh":
        return "从已配置的数据源拉取最新行情"
    if tool == "security-snapshot":
        return "确认股票代码，刷新多源行情并本地计算技术指标"
    if tool == "memory-query":
        return "只查询已确认的 Pattern 和 Rule"
    return "执行已授权的只读能力"


def _activity_phase(activity_type: str) -> str:
    if activity_type in ("SEARCH_STARTED", "SOURCE_OPENED", "PLANNER_STEP", "PLANNER_STOP", "SOURCE_SKILL_COMPLETED", "COVERAGE_CHECKED"):
        return "research"
    if activity_type in ("THESIS_UPDATED", "JOURNAL_SAVED"):
        return "memory"
    if activity_type in ("DATA_FRESHNESS_CHECKED", "MARKET_DATA_REFRESHED"):
        return "data"
    return "tool"


def _activity_title(activity: dict) -> str:
    activity_type = activity.get("type") or ""
    if activity_type == "SOURCE_OPENED":
        return "已读取：{0}".format(_safe_progress_detail(activity.get("summary") or "来源"))
    if activity_type == "PLANNER_STEP":
        return _safe_progress_detail(activity.get("summary") or "正在补齐证据")
    return _ACTIVITY_LABELS.get(activity_type, _safe_progress_detail(activity.get("summary") or activity_type))


def _safe_progress_detail(value: str, limit: int = 140) -> str:
    text = " ".join((value or "").split())
    return text[:limit]


def _research_progress_event(event: dict) -> dict | None:
    """Turn a stored research event into a public, action-level trace row.

    The trace explains what the workflow did and observed.  It deliberately
    excludes prompts, hidden reasoning, model scratchpads and raw page bodies.
    """
    event_type = event.get("event_type") or ""
    payload = dict(event.get("payload") or {})
    raw_status = event.get("status") or "running"
    status = {
        "ok": "completed", "replay": "completed", "gap": "gap",
        "failed": "failed", "running": "running",
    }.get(raw_status, "running")

    def row(phase: str, title: str, detail: str = "") -> dict:
        return {
            "phase": phase,
            "title": _safe_progress_detail(title, 100),
            "detail": _safe_progress_detail(detail, 220),
            "status": status,
        }

    if event_type == "entity_resolved":
        subject = " ".join(value for value in (payload.get("name"), payload.get("ticker")) if value)
        extra = " · ".join(value for value in (payload.get("exchange"), payload.get("universe_status")) if value)
        return row("intent", "研究对象已核验：{0}".format(subject or "未确认"), extra)
    if event_type == "skill_selected":
        return None  # The outer Agent already displays the selected skill.
    if event_type == "plan_created":
        questions = [item.get("question") or "" for item in payload.get("tasks") or [] if item.get("question")]
        return row(
            "plan", "研究计划已生成 · {0} 个核对问题".format(payload.get("task_count") or len(questions)),
            " → ".join(questions[:4]),
        )
    if event_type == "parallel_skills":
        if raw_status == "running":
            labels = [str(value) for value in payload.get("skills") or [] if value]
            return row("plan", "并行启动 {0} 条证据线".format(payload.get("count") or len(labels)), " · ".join(labels))
        gaps = payload.get("critical_gaps") or []
        detail = "打开 {0} 份正文".format(payload.get("sources_opened") or 0)
        if gaps:
            detail += " · 仍缺：" + "、".join(str(value) for value in gaps[:4])
        return row("evidence", "并行证据搜集已汇总", detail)
    if event_type == "source_skill_started":
        return row(
            "search", "开始检索：{0}".format(payload.get("label") or payload.get("name") or "来源"),
            "用途：{0} · 查询：{1}".format(payload.get("evidence_role") or "独立核对", payload.get("query") or ""),
        )
    if event_type in ("source_skill_search_completed", "source_skill"):
        count = int(payload.get("count") or 0)
        title = "{0}：找到 {1} 条候选".format(payload.get("label") or payload.get("name") or "来源检索", count)
        if not count:
            title = "{0}：没有找到可用候选".format(payload.get("label") or payload.get("name") or "来源检索")
        details = []
        if payload.get("query_count"):
            details.append("执行 {0} 次检索".format(payload["query_count"]))
        if payload.get("official_annual_reports_complete"):
            details.append("官方最近三年年报目录已齐")
        if payload.get("error_code"):
            details.append("错误：{0}".format(payload["error_code"]))
        return row("search", title, " · ".join(details) or (payload.get("query") or ""))
    if event_type == "planner_decision":
        wave = payload.get("wave") or "?"
        if payload.get("action") == "FINISH":
            return row("plan", "Planner 决定停止继续搜索", payload.get("reason") or "关键证据已覆盖")
        query = payload.get("query") or ""
        return row("plan", "第 {0} 轮：决定补查「{1}」".format(wave, query), payload.get("reason") or "补齐证据缺口")
    if event_type == "wave":
        if payload.get("title") == "Synthesis":
            return row("synthesis", "开始综合证据", "完成门检查：{0}".format("通过" if payload.get("completion_passed") else "仍有缺口"))
        return None
    if event_type == "search":
        queries = [str(value) for value in payload.get("queries") or [] if value]
        return row(
            "search", "第 {0} 轮搜索返回 {1} 条线索".format(payload.get("wave") or "?", payload.get("count") or 0),
            "；".join(queries[:2]),
        )
    if event_type == "read":
        if raw_status == "ok":
            title = payload.get("title") or payload.get("url") or "来源正文"
            label = payload.get("source_label") or ""
            return row("read", "已打开原文：{0}".format(title), label or "正文通过主体与时间校验")
        return row(
            "read", "来源未能读取",
            "{0} · {1}".format(payload.get("error_code") or "SOURCE_UNREADABLE", payload.get("url") or ""),
        )
    if event_type == "gap":
        next_action = payload.get("next_action") or {}
        detail = payload.get("text") or "发现证据缺口"
        if next_action.get("query"):
            detail += " · 下一步：" + next_action["query"]
        return row("evidence", "仍有待核对项目", detail)
    if event_type == "ifind_financials":
        if raw_status == "running":
            return row(
                "data", "正在调用 iFinD 核对结构化财务指标",
                payload.get("role") or "与官方财报原文交叉校验",
            )
        return row(
            "data",
            "iFinD 财务交叉校验{0}".format("已完成" if raw_status == "ok" else "暂不可用"),
            payload.get("message") or "数据商口径不会替代交易所公告原文",
        )
    if event_type == "financial_analysis":
        if raw_status == "running":
            years = "、".join(str(value) for value in payload.get("required_years") or [])
            return row("data", "正在解析三年财报", "目标年份：{0} · 已读来源 {1} 份".format(years or "待确认", payload.get("source_count") or 0))
        return row(
            "data", "三年财务基线：{0}".format(payload.get("coverage_status") or "INCOMPLETE"),
            "年度 {0} 个 · 最新季报/半年报 {1} 期 · 产品分部 {2} 行 · 风险检查 {3} 项".format(
                payload.get("record_count") or 0, payload.get("periodic_count") or 0,
                payload.get("segment_count") or 0, payload.get("risk_count") or 0,
            ),
        )
    if event_type == "market_data":
        return row(
            "data", "行情与技术面数据{0}".format("已更新" if raw_status == "ok" else "未能更新"),
            payload.get("message") or "日期 {0} · {1} 行".format(payload.get("asof") or "UNKNOWN", payload.get("rows") or 0),
        )
    if event_type == "dossier":
        if raw_status == "running":
            return row("synthesis", "正在组装公司档案", "{0} 条事实 · {1} 份来源".format(payload.get("claim_count") or 0, payload.get("source_count") or 0))
        return row("synthesis", "公司档案结构已生成", "写入 {0} 个有效字段 · {1} 个未决问题".format(payload.get("sections") or 0, payload.get("open_questions") or 0))
    if event_type == "disconfirmation":
        return row("evidence", "反方证据与失效条件已检查", "没有证据的项目继续保留 UNKNOWN")
    if event_type == "coverage_check":
        passed = int(payload.get("passed_count") or 0)
        total = int(payload.get("checked_count") or 0)
        gaps = (payload.get("missing_labels") or []) + (payload.get("attempted_unavailable_labels") or [])
        detail = "{0}/{1} 项通过".format(passed, total)
        if gaps:
            detail += " · 待补：" + "、".join(str(value) for value in gaps[:6])
        return row(
            "evidence",
            "覆盖验收：{0} · {1}".format(payload.get("mode") or "研究", payload.get("status") or "PARTIAL"),
            detail,
        )
    if event_type == "research_memory":
        return row("memory", "公司研究记忆已保存", "同步 {0} 份来源到长期档案".format(payload.get("source_count") or 0))
    if event_type == "claims":
        return row("evidence", "已提取 {0} 条可引用事实".format(payload.get("count") or 0), "事实保留来源关系，搜索摘要不算证据")
    if event_type == "synthesis":
        return row("synthesis", "研究报告草稿已生成", "正式结论：{0}".format("是" if payload.get("formal") else "否，仍是可更新草稿"))
    if event_type in ("done", "skill_selected"):
        return None
    if event_type == "planner":
        return row("plan", "Planner 输出未通过安全校验", payload.get("error_code") or "PLANNER_FAILED")
    return None


def _pattern_hit(message: str, row: dict) -> bool:
    blob = "{0} {1}".format(row.get("summary") or "", row.get("pattern_key") or "")
    if "追高" in message and ("追高" in blob or "FOMO" in blob.upper()):
        return True
    return "重复" in message and "重复" in blob


def _rule_hit(message: str, text: str) -> bool:
    if "追高" in message and ("FOMO" in text or "追高" in text):
        return True
    return "超仓" in message and "仓" in text


def _scrub(text: str) -> str:
    cleaned = text or ""
    for token in _BANNED:
        cleaned = cleaned.replace(token, "［已略］")
    return cleaned


def create_goal(store: Store, **kwargs) -> dict:
    session = main_session(store)
    return goals.create(store, session_id=session["id"], **kwargs)
