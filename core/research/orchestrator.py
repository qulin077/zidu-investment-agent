"""一个 Research Agent。Skill 定步骤，Harness 限动作和预算，模型只推理。"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from core.config import ROOT
from core.research import industry, prompts, skills, tools
from core.research.claim_extractor import review as review_claims
from core.research.env import load_local_env
from core.research.planner import build as build_plan
from core.research.prompts import VERSIONS
from core.research.render import render
from core.research.state import ResearchState, choose_next_task, research_action
from core.research import store as rstore
from core.research.tools.fixture_search import FixtureSearchTool
from core.research.types import PROMPT_TEMPERATURE
from core.research.validator import validate
from core.store import STORE, Store


class BudgetExceeded(RuntimeError):
    pass


class IterationBudget(RuntimeError):
    pass


def _strip_bodies(draft: dict) -> str:
    copied = json.loads(json.dumps(draft, ensure_ascii=False))
    for source in copied.get("sources") or []:
        body = source.get("body") or ""
        source["body"] = "[omitted {0} chars]".format(len(body))
    return json.dumps(copied, ensure_ascii=False)


def _resolve_mode(mode: str) -> str:
    if mode in ("fixture", "remote_shadow", "remote_primary"):
        return mode
    if mode == "remote":
        return "remote_shadow"
    from core.review import flags
    return flags.research_llm_mode()


def _fail(store: Store, run_id: str, status: str, code: str, message: str, **extra) -> dict:
    rstore.finish_run(
        store, run_id, status=status, error_code=code, error_message=message, **extra,
    )
    return {
        "ok": False,
        "status": status,
        "error_code": code,
        "error_message": message,
        "errors": extra.get("errors") or [],
        "run_id": run_id,
        "project_id": "",
        "thesis_id": "",
        "thesis_version": 0,
    }


def run(
    question: str = "",
    *,
    as_of: str = "",
    market_scope=None,
    industry_or_theme: str = "",
    depth: str = "deep",
    user_context: str = "",
    mode: str = "fixture",
    fixture: Optional[dict] = None,
    llm=None,
    store: Store = STORE,
    output_dir: Optional[Path] = None,
    load_env: bool = True,
    max_iterations: Optional[int] = None,
    max_llm_calls: Optional[int] = None,
) -> dict:
    from core.review import flags

    resolved = _resolve_mode(mode)
    if resolved != "fixture" and load_env:
        load_local_env()
    if fixture is not None:
        question = question or fixture.get("research_question") or ""
        as_of = as_of or fixture.get("as_of") or ""
        industry_or_theme = industry_or_theme or fixture.get("industry_or_theme") or ""
        market_scope = market_scope if market_scope is not None else fixture.get("market_scope")
    if len(user_context or "") > 500:
        return {
            "ok": False, "status": "failed", "error_code": "CONTEXT_TOO_LONG",
            "error_message": "user_context 超过 500 字。不要把整段聊天塞进研究。",
            "run_id": "", "project_id": "",
        }
    if not flags.research_enabled():
        return {
            "ok": False, "status": "failed", "error_code": "RESEARCH_DISABLED",
            "error_message": "研究开关是关的。", "run_id": "", "project_id": "",
        }
    skill_name = skills.select(question)
    if skill_name not in ("industry-research", "company-research"):
        return {
            "ok": False, "status": "failed", "error_code": "SKILL_NOT_SELECTED",
            "error_message": "这句话没有落到 industry-research 或 company-research。",
            "run_id": "", "project_id": "",
        }
    budget = flags.research_budget()
    limit_iterations = budget["max_iterations"] if max_iterations is None else max_iterations
    limit_calls = budget["max_llm_calls"] if max_llm_calls is None else max_llm_calls
    if skill_name == "company-research":
        from core.research.planner import company_plan
        plan = company_plan(question, industry_or_theme or question, as_of, market_scope or [], depth)
        if fixture is None and resolved == "fixture" and ("麦格米特" in question or "002851" in question):
            from core.research.company_demo import draft as company_draft
            fixture = company_draft(as_of or "2026-09-27T23:59:59+08:00", store)
            as_of = as_of or fixture.get("as_of") or ""
    else:
        plan = build_plan(question, industry_or_theme, as_of, market_scope or [], depth)
    state = ResearchState(
        question,
        skill=skill_name,
        as_of=as_of,
        max_iterations=limit_iterations,
        max_llm_calls=limit_calls,
    )
    state.plan = list(plan.get("tasks") or [])
    model = "fixture" if resolved == "fixture" else (getattr(llm, "name", "") or os.environ.get("LLM_MODEL") or "")
    run_id = rstore.start_run(
        store, question, skill_name, resolved, plan, "", model, prompts.versions_json(),
    )
    state.run_id = run_id
    if resolved == "remote_primary" and not flags.research_remote_primary_allowed():
        return _fail(
            store, run_id, "blocked", "PRIMARY_DISABLED",
            "Eval Gate 通过之前，不能把远程结果写成正式 Thesis。",
            llm_mode=resolved, llm_calls=0, iterations=0, estimated_cost=0,
        )

    tool_log = []
    llm_calls = 0
    input_tokens = 0
    output_tokens = 0

    def charge() -> None:
        nonlocal llm_calls
        if llm_calls >= limit_calls:
            raise BudgetExceeded()
        llm_calls += 1
        state.llm_calls = llm_calls

    def tick(action: str) -> dict:
        state.iteration += 1
        payload = research_action(action, "LOOP", question, "固定动作。", action)
        state.current_task = payload
        if state.iteration > limit_iterations:
            raise IterationBudget()
        state.completed_tasks.append(payload)
        tool_log.append({"tool": action, "ok": True})
        return payload

    def usage_of(client) -> None:
        nonlocal input_tokens, output_tokens
        usage = getattr(client, "last_usage", None) or {}
        input_tokens += int(usage.get("prompt_tokens") or 0)
        output_tokens += int(usage.get("completion_tokens") or 0)
        if input_tokens > budget["max_input_tokens"] or output_tokens > budget["max_output_tokens"]:
            raise BudgetExceeded()

    try:
        if resolved != "fixture" and fixture is None:
            tick("SEARCH")
            hits = tools.search_repo(question)
            web = tools.search_web(question)
            tool_log.append({"tool": "search_repo", "ok": bool(hits), "n": len(hits)})
            tool_log.append({"tool": "search_web", "ok": bool(web.get("ok")), "error_code": web.get("error_code") or ""})
            if not hits and not web.get("ok"):
                return _fail(
                    store, run_id, "unavailable", web.get("error_code") or "SOURCE_UNAVAILABLE",
                    web.get("message") or "没有读到正文。",
                    tool_calls=len(tool_log), tool_log_json=json.dumps(tool_log, ensure_ascii=False),
                    llm_calls=0, llm_mode=resolved, iterations=state.iteration,
                )
            has_key = bool(os.environ.get("OPENAI_API_KEY") or os.environ.get("LLM_API_KEY"))
            if llm is None and not has_key:
                return _fail(
                    store, run_id, "unavailable", "LLM_UNAVAILABLE",
                    "没有远程模型。研究不会用启发式假装做完。",
                    llm_calls=0, llm_mode=resolved, iterations=state.iteration,
                )
            return _fail(
                store, run_id, "blocked", "LIVE_SEARCH_NOT_IN_V1",
                "这一版远程对照使用固定来源。不稳定的现搜还没打开。",
                llm_calls=0, llm_mode=resolved, iterations=state.iteration,
            )

        draft = dict(fixture or {})
        draft["as_of"] = as_of or draft.get("as_of") or ""
        draft["research_question"] = question
        draft["user_context"] = user_context
        state.status = "RUNNING"
        charge()
        usage_of(llm)
        tick("SEARCH")
        found = FixtureSearchTool(draft.get("sources") or []).search(question)
        if not found:
            return _fail(
                store, run_id, "unavailable", "SEARCH_FAILED", "夹具里没有来源。",
                llm_calls=llm_calls, llm_mode=resolved, iterations=state.iteration,
                tool_calls=len(tool_log), tool_log_json=json.dumps(tool_log, ensure_ascii=False),
            )
        state.sources = list(draft.get("sources") or [])
        tick("READ_SOURCE")
        tick("EXTRACT_CLAIMS")
        charge()
        usage_of(llm)
        state.claims = list(draft.get("claims") or [])
        errors = review_claims(draft) + validate(draft)
        if errors:
            return _fail(
                store, run_id, "blocked", "WRITE_BLOCKED",
                "；".join(item["message"] for item in errors[:6]),
                errors=errors,
                tool_calls=len(tool_log),
                tool_log_json=json.dumps(tool_log, ensure_ascii=False),
                llm_calls=llm_calls,
                llm_mode=resolved,
                iterations=state.iteration,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                estimated_cost=0,
                raw_output=_strip_bodies(draft),
                parsed_output=json.dumps({"errors": errors}, ensure_ascii=False),
            )
        tick("RESOLVE_GAP")
        state.open_questions = list(draft.get("open_questions") or [])
        state.critical_gaps = []
        tick("BUILD_SECTION")
        sections = industry.build_model(draft)
        state.value_chain = sections["value_chain"]
        state.company_mappings = sections["company_exposure"]
        state.conflicts = list(draft.get("conflicts") or [])
        state.thesis_ready = True
        tick("FINISH")
        charge()
        usage_of(llm)
    except BudgetExceeded:
        return _fail(
            store, run_id, "stopped", "BUDGET_EXCEEDED",
            "这一轮的模型或 token 预算用完了。已停下，不继续编结论。",
            llm_calls=llm_calls, llm_mode=resolved, iterations=state.iteration,
            input_tokens=input_tokens, output_tokens=output_tokens, estimated_cost=0,
            tool_calls=len(tool_log), tool_log_json=json.dumps(tool_log, ensure_ascii=False),
            plan_json=json.dumps(plan, ensure_ascii=False),
        )
    except IterationBudget:
        return _fail(
            store, run_id, "stopped", "ITERATION_BUDGET",
            "研究轮次到了上限。已停下，不把半成品写成 Thesis。",
            llm_calls=llm_calls, llm_mode=resolved, iterations=state.iteration,
            tool_calls=len(tool_log), tool_log_json=json.dumps(tool_log, ensure_ascii=False),
            plan_json=json.dumps(plan, ensure_ascii=False),
        )

    raw_text = _strip_bodies(draft)
    formal = resolved == "fixture" or resolved == "remote_primary"
    if not formal:
        rstore.finish_run(
            store, run_id,
            status="shadow",
            model=model,
            llm_mode=resolved,
            temperature=PROMPT_TEMPERATURE,
            tool_calls=len(tool_log),
            tool_log_json=json.dumps(tool_log, ensure_ascii=False),
            llm_calls=llm_calls,
            iterations=state.iteration,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost=0,
            raw_output=raw_text,
            parsed_output=json.dumps({"formal": False, "state": state.snapshot()}, ensure_ascii=False),
            prompt_versions=json.dumps(VERSIONS, ensure_ascii=False),
            error_code="SHADOW_NOT_FORMAL",
            error_message="远程对照不能写成正式 Thesis。",
            plan_json=json.dumps(plan, ensure_ascii=False),
        )
        return {
            "ok": False,
            "status": "shadow",
            "error_code": "SHADOW_NOT_FORMAL",
            "error_message": "远程对照不能写成正式 Thesis。",
            "errors": [],
            "run_id": run_id,
            "project_id": "",
            "thesis_id": "",
            "thesis_version": 0,
            "plan": plan,
            "state": state.snapshot(),
        }
    try:
        saved = rstore.persist_project(store, draft, run_id, plan)
    except Exception as exc:  # noqa: BLE001
        return _fail(store, run_id, "failed", "WRITE_BLOCKED", str(exc), raw_output=raw_text, llm_mode=resolved)
    state.project_id = saved["project_id"]
    state.status = "FINISHED"
    view = rstore.project_view(store, saved["project_id"])
    base = output_dir if output_dir is not None else (ROOT / "data" / "research")
    target = base / saved["project_id"]
    target.mkdir(parents=True, exist_ok=True)
    markdown_path = target / "research_output.md"
    markdown_path.write_text(render(view or {}), encoding="utf-8")
    rstore.finish_run(
        store, run_id,
        project_id=saved["project_id"],
        question_id=saved.get("question_id") or "",
        status="succeeded",
        model=model,
        llm_mode=resolved,
        temperature=PROMPT_TEMPERATURE,
        tool_calls=len(tool_log),
        tool_log_json=json.dumps(tool_log, ensure_ascii=False),
        llm_calls=llm_calls,
        iterations=state.iteration,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        estimated_cost=0,
        raw_output=raw_text,
        parsed_output=json.dumps({"thesis_id": saved["thesis_id"], "version": 1}, ensure_ascii=False),
        prompt_versions=json.dumps(VERSIONS, ensure_ascii=False),
        plan_json=json.dumps(plan, ensure_ascii=False),
    )
    output = rstore.public_output(store, saved["project_id"])
    return {
        "ok": True,
        "status": "succeeded",
        "error_code": "",
        "error_message": "",
        "errors": [],
        "run_id": run_id,
        "project_id": saved["project_id"],
        "thesis_id": saved["thesis_id"],
        "thesis_version": 1,
        "plan": plan,
        "skill": skill_name,
        "output": output,
        "markdown_path": str(markdown_path),
        "state": state.snapshot(),
    }
