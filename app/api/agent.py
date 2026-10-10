"""Investment Agent 主对话。事实写入仍走原来的研究、决策和记忆模块。"""
from __future__ import annotations

import json
import queue
import threading
from typing import List

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from core.agent.artifacts import get_artifact, rebuild
from core.agent.home import panel
from core.agent.journal import list_entries
from core.agent.metrics import snapshot
from core.agent.prompts import INVESTMENT_AGENT_PROMPT_VERSION
from core.agent.personal_context import create_strategy, list_strategies, set_active_strategy
from core.agent.store import get_session, list_activity, list_messages, main_session
from core.agent.runtime import get_turn, list_turns
from core.agent.turn import create_goal, handle
from core.store import STORE

router = APIRouter()


class MessageIn(BaseModel):
    message: str = Field(min_length=1, max_length=500)
    network: str = "replay"
    use_llm: bool = True
    llm_mode: str = "auto"


class GoalIn(BaseModel):
    title: str = Field(min_length=1, max_length=80)
    goal_type: str = "RESEARCH"
    description: str = ""
    project_ids: List[str] = Field(default_factory=list)
    pattern_ids: List[str] = Field(default_factory=list)


class StrategyIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    description: str = Field(default="", max_length=300)
    time_horizon: str = Field(default="", max_length=40)
    style: str = Field(default="", max_length=60)
    research_preferences: dict = Field(default_factory=dict)
    decision_preferences: dict = Field(default_factory=dict)
    review_preferences: dict = Field(default_factory=dict)
    risk_constraints: dict = Field(default_factory=dict)
    activate: bool = True


def _session_view(session: dict) -> dict:
    return {
        "id": session.get("id") or "",
        "title": session.get("title") or "",
        "status": session.get("status") or "",
        "active_goal_id": session.get("active_goal_id") or "",
        "active_project_id": session.get("active_project_id") or "",
        "active_decision_id": session.get("active_decision_id") or "",
        "active_strategy_id": session.get("active_strategy_id") or "",
        "current_domain": session.get("current_domain") or "GENERAL",
        "summary": session.get("summary") or {},
    }


@router.get("/api/agent/home")
def agent_home():
    session = main_session(STORE)
    return {
        "prompt_version": INVESTMENT_AGENT_PROMPT_VERSION,
        "session": _session_view(session),
        "messages": list_messages(STORE, session["id"]),
        "panel": panel(STORE, session),
        "metrics": snapshot(STORE),
    }


@router.get("/api/agent/health")
def agent_health():
    from core.agent.runtime import health
    return health()


@router.get("/api/agent/runtime/turns")
def agent_runtime_turns(session_id: str = "", limit: int = 20):
    session = main_session(STORE)
    return {"turns": list_turns(STORE, session_id or session["id"], limit=limit)}


@router.get("/api/agent/runtime/turns/{turn_id}")
def agent_runtime_turn(turn_id: str):
    turn = get_turn(STORE, turn_id)
    if not turn:
        raise HTTPException(status_code=404, detail="没有这个 Agent turn")
    return turn


@router.post("/api/agent/messages")
def agent_message(body: MessageIn):
    network = body.network if body.network in ("live", "replay") else "replay"
    enabled = body.llm_mode != "off" and (body.use_llm or body.llm_mode == "auto")
    return handle(STORE, body.message, network=network, use_llm=enabled)


@router.post("/api/agent/messages/stream")
def agent_message_stream(body: MessageIn):
    """Stream public execution milestones, never private model reasoning."""
    network = body.network if body.network in ("live", "replay") else "replay"
    enabled = body.llm_mode != "off" and (body.use_llm or body.llm_mode == "auto")

    def events():
        channel = queue.Queue()

        def progress(event: dict) -> None:
            channel.put(("progress", event))

        def run() -> None:
            try:
                result = handle(
                    STORE,
                    body.message,
                    network=network,
                    use_llm=enabled,
                    progress=progress,
                )
                channel.put(("result", result))
            except Exception:
                channel.put(("error", {"message": "这轮执行失败了，请稍后重试。"}))

        threading.Thread(target=run, daemon=True).start()
        while True:
            event_name, payload = channel.get()
            yield "event: {0}\ndata: {1}\n\n".format(
                event_name,
                json.dumps(payload, ensure_ascii=False),
            )
            if event_name in ("result", "error"):
                break

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/api/agent/activity")
def agent_activity(session_id: str = "", project_id: str = ""):
    return {"activities": list_activity(STORE, session_id=session_id, project_id=project_id)}


@router.get("/api/agent/goals")
def agent_goals():
    session = main_session(STORE)
    return {"goals": panel(STORE, session).get("goals") or []}


@router.get("/api/agent/journal")
def agent_journal(day: str = "", limit: int = 20):
    session = main_session(STORE)
    return {"entries": list_entries(STORE, day=day, session_id=session["id"], limit=limit)}


@router.post("/api/agent/goals")
def agent_goal_create(body: GoalIn):
    return create_goal(
        STORE, title=body.title, goal_type=body.goal_type, description=body.description,
        project_ids=body.project_ids, pattern_ids=body.pattern_ids,
    )


@router.get("/api/agent/strategies")
def agent_strategies():
    session = main_session(STORE)
    return {
        "active_strategy_id": session.get("active_strategy_id") or "",
        "strategies": list_strategies(STORE),
    }


@router.post("/api/agent/strategies")
def agent_strategy_create(body: StrategyIn):
    strategy = create_strategy(
        STORE, body.name, description=body.description,
        time_horizon=body.time_horizon, style=body.style,
        research_preferences=body.research_preferences,
        decision_preferences=body.decision_preferences,
        review_preferences=body.review_preferences,
        risk_constraints=body.risk_constraints,
    )
    if body.activate:
        session = main_session(STORE)
        set_active_strategy(STORE, session["id"], strategy["id"])
    return {"strategy": strategy, "active": body.activate}


@router.post("/api/agent/strategies/{strategy_id}/activate")
def agent_strategy_activate(strategy_id: str):
    session = main_session(STORE)
    try:
        strategy = set_active_strategy(STORE, session["id"], strategy_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"strategy": strategy, "active": True}


@router.post("/api/agent/artifacts/{artifact_id}/rebuild")
def agent_artifact_rebuild(artifact_id: str):
    row = get_artifact(STORE, artifact_id)
    if not row:
        raise HTTPException(status_code=404, detail="没有这个 Artifact")
    rebuilt = rebuild(STORE, row.get("project_id") or "")
    session = get_session(STORE, main_session(STORE)["id"])
    return {"artifact": rebuilt, "session": _session_view(session)}
