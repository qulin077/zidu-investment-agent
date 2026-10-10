"""研究底稿接口。和原来的 /api/research 简报分开。"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from core.research import skills
from core.research.fixtures import ai_power
from core.research.fixtures.structural import minimal
from core.research.metrics import product_metrics
from core.research.orchestrator import run
from core.research.planner import build as build_plan
from core.research.store import list_projects, now_iso, project_view
from core.review import flags
from core.store import STORE

router = APIRouter()


class ResearchRequest(BaseModel):
    research_question: str = Field(min_length=1, max_length=500)
    as_of: str = ""
    market_scope: List[str] = []
    industry_or_theme: str = ""
    depth: str = "deep"
    mode: str = "fixture"
    user_context: str = ""


def _disabled():
    return {"ok": False, "error_code": "RESEARCH_DISABLED", "error_message": "研究底稿开关是关的。"}


def fixture_for(question: str, theme: str, as_of: str) -> Optional[dict]:
    text = "{0} {1}".format(question or "", theme or "")
    if "电源" in text:
        return ai_power.packet(as_of)
    if "光模块" in text:
        return minimal("光模块", as_of)
    if "半导体" in text:
        return minimal("半导体设备", as_of)
    return None


@router.get("/api/research/plan")
def research_plan(q: str, theme: str = "", as_of: str = "", depth: str = "deep", skill: str = ""):
    if not flags.research_enabled():
        return _disabled()
    routed = skills.route(q)
    chosen = skill if skill in ("industry-research", "company-research") else routed.get("skill") or ""
    if not chosen:
        return {
            "ok": False,
            "error_code": "SKILL_NOT_SELECTED",
            "error_message": "这句分不清是行业研究还是公司研究。",
            "route": routed,
        }
    if chosen == "company-research":
        from core.research.planner import company_plan
        plan = company_plan(q, theme or q, as_of, [], depth)
    else:
        plan = build_plan(q, theme, as_of, [], depth)
    return {"ok": True, "skill": chosen, "route": routed, "plan": plan}


@router.get("/api/research/projects")
def research_projects():
    if not flags.research_enabled():
        return _disabled()
    return {"ok": True, "rows": list_projects()}


@router.get("/api/research/playbooks")
def research_playbooks():
    """Expose the five industry lenses shown in the Research library."""
    if not flags.research_enabled():
        return _disabled()
    from core.research import industry_playbooks
    return {"ok": True, "rows": industry_playbooks.catalog()}


@router.get("/api/research/projects/{project_id}")
def research_project(project_id: str):
    if not flags.research_enabled():
        return _disabled()
    view = project_view(STORE, project_id)
    if view is None:
        raise HTTPException(status_code=404, detail="没有这个研究项目")
    view["metrics"] = product_metrics(STORE)
    return view


@router.post("/api/research/projects")
def research_create(body: ResearchRequest):
    if not flags.research_enabled():
        return _disabled()
    as_of = body.as_of or now_iso()
    fixture = None
    routed = skills.route(body.research_question)
    if body.mode == "fixture" and routed.get("skill") != "company-research":
        fixture = fixture_for(body.research_question, body.industry_or_theme, as_of)
        if fixture is None:
            return {
                "ok": False,
                "error_code": "FIXTURE_NOT_FOUND",
                "error_message": "这个主题没有仓库夹具。远程模型不可用时不会拿别的行业顶上。",
            }
    if body.mode == "fixture" and routed.get("skill") == "company-research":
        if "麦格米特" not in body.research_question and "002851" not in body.research_question:
            return {
                "ok": False,
                "error_code": "FIXTURE_NOT_FOUND",
                "error_message": "这轮公司夹具只准备了麦格米特。别的公司不会用行业夹具顶上。",
            }
    return run(
        body.research_question,
        as_of=as_of,
        market_scope=body.market_scope,
        industry_or_theme=body.industry_or_theme,
        depth=body.depth,
        user_context=body.user_context,
        mode=body.mode,
        fixture=fixture,
        load_env=body.mode != "fixture",
    )


class SessionCreate(BaseModel):
    message: str = Field(min_length=1, max_length=500)
    depth: str = "standard"
    mode: str = "remote_shadow"
    search_provider: str = "ddgs"
    network: str = ""
    inline: bool = False
    as_of: str = ""
    skill: str = ""


class SessionMessage(BaseModel):
    message: str = Field(min_length=1, max_length=500)
    depth: str = ""
    mode: str = ""
    search_provider: str = ""
    network: str = ""
    inline: bool = False
    as_of: str = ""


def _start(message: str, *, session_id: str = "", mode: str, network: str, search_provider: str, depth: str, as_of: str, inline: bool, skill: str = ""):
    from core.research import sessions
    from core.research import workspace
    from core.research.netread import network_mode
    from core.research.worker import submit

    chosen_network = network or network_mode()
    opened = workspace.open_turn(
        STORE, message, session_id=session_id, mode=mode or "remote_shadow",
        network=chosen_network, search_provider=search_provider or "ddgs",
        depth=depth or "standard", as_of=as_of or "",
    )
    if not opened.get("ok"):
        return opened
    if inline:
        result = workspace.execute(
            STORE, opened["session_id"], opened["run_id"],
            use_llm=mode in ("remote_shadow", "remote_primary"),
            skill=skill,
        )
        return {"session_id": result["session_id"], "run_id": result["run_id"], "status": result["status"]}
    submit(opened["session_id"], opened["run_id"], skill=skill)
    return {"session_id": opened["session_id"], "run_id": opened["run_id"], "status": "running"}


@router.post("/api/research/sessions")
def create_research_session(body: SessionCreate):
    if not flags.research_enabled():
        return _disabled()
    if body.mode not in ("fixture", "remote_shadow", "remote_primary"):
        return {"ok": False, "error_code": "MODE", "error_message": "mode 只能是 fixture、remote_shadow 或 remote_primary。"}
    return _start(
        body.message, mode=body.mode, network=body.network,
        search_provider=body.search_provider, depth=body.depth,
        as_of=body.as_of, inline=body.inline,
        skill=body.skill if body.skill in ("company-research", "industry-research", "event-impact") else "",
    )


@router.get("/api/research/sessions")
def research_sessions():
    from core.research import sessions
    if not flags.research_enabled():
        return _disabled()
    return {"ok": True, "rows": sessions.list_sessions(STORE)}


@router.get("/api/research/library")
def research_library(subject_type: str = "company"):
    from core.research import sessions
    if not flags.research_enabled():
        return _disabled()
    sessions.reap_stale(STORE)
    return {"ok": True, "rows": sessions.research_library(STORE, subject_type)}


@router.get("/api/research/sessions/{session_id}")
def research_session(session_id: str):
    from core.research import sessions
    if not flags.research_enabled():
        return _disabled()
    sessions.reap_stale(STORE)
    view = sessions.bundle(STORE, session_id)
    if view is None:
        raise HTTPException(status_code=404, detail="没有这个研究会话")
    return view


@router.post("/api/research/sessions/{session_id}/messages")
def research_session_message(session_id: str, body: SessionMessage):
    from core.research import sessions
    if not flags.research_enabled():
        return _disabled()
    session = sessions.get_session(STORE, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="没有这个研究会话")
    options = (session.get("summary") or {}).get("options") or {}
    return _start(
        body.message, session_id=session_id,
        mode=body.mode or options.get("mode") or "remote_shadow",
        network=body.network or options.get("network") or "",
        search_provider=body.search_provider or options.get("search_provider") or "ddgs",
        depth=body.depth or options.get("depth") or "standard",
        as_of=body.as_of or options.get("as_of") or "",
        inline=body.inline,
        skill=session.get("skill") or "",
    )


@router.get("/api/research/update-candidates")
def research_update_candidates(status: str = "PENDING", limit: int = 30):
    from core.research.daily_updates import list_candidates, pending_count
    return {"ok": True, "pending_count": pending_count(STORE), "rows": list_candidates(STORE, status=status, limit=limit)}


@router.post("/api/research/update-candidates/scan")
def scan_research_update_candidates():
    from core.research.daily_updates import scan_news
    return scan_news(STORE, limit=1000)


@router.post("/api/research/update-candidates/{candidate_id}/accept")
def accept_research_update_candidate(candidate_id: str):
    from core.research.daily_updates import get_candidate, set_status
    row = get_candidate(STORE, candidate_id)
    if row is None:
        raise HTTPException(status_code=404, detail="没有这个更新候选")
    if row.get("status") != "PENDING":
        raise HTTPException(status_code=409, detail="这个候选已经处理过")
    target_type = row.get("target_type") or "new_event"
    forced_skill = {
        "company": "company-research", "industry": "industry-research",
        "event": "event-impact", "new_event": "event-impact",
    }.get(target_type, "event-impact")
    prompt = (
        "这是每日看板发现的候选线索，不要把标题或摘要当成证据。"
        "请先打开原文，并继续搜索一手来源和反证；核对它是否真的改变现有档案。"
        "若可靠正文和覆盖检查通过，追加一个新版本；否则保留为待核对且不要修改原判断。\n"
        "候选标题：{title}\n来源：{source}\n发布时间：{published}\n链接：{url}"
    ).format(
        title=row.get("news_title") or "", source=row.get("news_source") or "",
        published=row.get("published_at") or "", url=row.get("news_url") or "",
    )
    opened = _start(
        prompt, session_id=row.get("target_session_id") or "",
        mode="remote_shadow", network="live", search_provider="ddgs",
        depth="standard", as_of="", inline=False, skill=forced_skill,
    )
    if not opened.get("session_id") or not opened.get("run_id"):
        raise HTTPException(status_code=503, detail=opened.get("error_message") or "研究任务未能启动")
    set_status(
        STORE, candidate_id, "ACCEPTED",
        run_id=opened.get("run_id") or "", session_id=opened.get("session_id") or "",
    )
    return {"ok": True, "candidate_id": candidate_id, **opened}


@router.post("/api/research/update-candidates/{candidate_id}/dismiss")
def dismiss_research_update_candidate(candidate_id: str):
    from core.research.daily_updates import get_candidate, set_status
    row = get_candidate(STORE, candidate_id)
    if row is None:
        raise HTTPException(status_code=404, detail="没有这个更新候选")
    if row.get("status") != "PENDING":
        raise HTTPException(status_code=409, detail="这个候选已经处理过")
    set_status(STORE, candidate_id, "DISMISSED")
    return {"ok": True, "candidate_id": candidate_id, "status": "DISMISSED"}


@router.get("/api/research/sessions/{session_id}/events")
def research_session_events(session_id: str, after_seq: int = 0):
    from core.research import sessions
    if sessions.get_session(STORE, session_id) is None:
        raise HTTPException(status_code=404, detail="没有这个研究会话")

    def gen():
        for chunk in sessions.iter_sse(STORE, session_id, after_seq, wait=True):
            yield chunk

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})
