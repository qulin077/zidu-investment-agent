"""工作台读接口。

只读，不含任何交易判定逻辑。买前 Gate 与人设属于后续阶段，
刻意不在这一层暴露，避免未经校验的建议提前进入界面。

启动：
    python3 -m uvicorn app.api.main:app --reload --port 8787
"""
from __future__ import annotations

import os
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.api import services
from app.api.agent import router as agent_router
from app.api.research_os import router as research_os_router
from app.api.review import router as review_router
from core.review import migrate
from core.research.env import load_local_env
from core.research import sessions as research_sessions
from core.store import STORE
from core import chain_brief

app = FastAPI(
    title="个人量化工作台 API",
    version="0.1.0",
    description="研究框架，非投资建议。数据采集与看板只读接口。",
)

def _cors_origins() -> list[str]:
    configured = os.getenv("SA_CORS_ORIGINS", "")
    if configured.strip():
        return [origin.strip() for origin in configured.split(",") if origin.strip()]
    return ["http://localhost:3000", "http://127.0.0.1:3000"]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
app.include_router(review_router)
app.include_router(research_os_router)
app.include_router(agent_router)


@app.on_event("startup")
def _startup() -> None:
    load_local_env()
    STORE.init_schema()
    migrate.apply_all(STORE)
    # A development reload or process crash cannot leave the UI permanently in
    # “研究中”.  Any RUNNING row that predates this fresh process is stale by
    # definition; active runs only exist inside the old process.
    research_sessions.reap_stale(STORE, stale_seconds=0)


@app.get("/api/health", summary="各数据集契约状态")
def health():
    return services.dataset_health()


@app.get("/api/board", summary="看板首屏聚合")
def board():
    return services.board()


@app.get("/api/instruments", summary="股票池与最新行情")
def instruments():
    return {"rows": services.instruments()}


@app.get("/api/quotes/{code}", summary="单只标的日线序列")
def quotes(code: str, days: int = Query(120, ge=5, le=1000)):
    payload = services.quote_series(code, days=days)
    if not payload["rows"]:
        raise HTTPException(status_code=404, detail="无该标的行情：{0}".format(code))
    return payload


@app.get("/api/movers", summary="池内涨跌排行")
def movers(limit: int = Query(10, ge=1, le=50)):
    return services.movers(limit=limit)


@app.get("/api/sectors", summary="板块当日波动")
def sectors():
    return services.sector_performance()


@app.get("/api/positions", summary="最新持仓快照")
def positions():
    return services.positions()


@app.get("/api/account", summary="账户权益曲线")
def account(limit: int = Query(180, ge=1, le=1000)):
    return services.account_curve(limit=limit)


@app.get("/api/news", summary="新闻流")
def news(
    source: Optional[str] = None,
    limit: int = Query(50, ge=1, le=300),
):
    return services.news(source=source, limit=limit)


@app.get("/api/trades/summary", summary="成交概览与字段填充率")
def trades_summary():
    return services.trade_summary()


@app.get("/api/frameworks", summary="研究框架文档索引")
def frameworks():
    return {"rows": services.frameworks()}


@app.get("/api/frameworks/content", summary="读取框架文档正文")
def framework_content(path: str = Query(..., min_length=3)):
    try:
        return services.read_framework(path)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except (FileNotFoundError, OSError):
        raise HTTPException(status_code=404, detail="文档不存在：{0}".format(path))


@app.get("/api/chains", summary="已定义产业链")
def chains():
    return {"rows": chain_brief.list_chain_meta()}


@app.get("/api/chains/resolve", summary="把问题收成链/公司/新闻简报")
def chains_resolve(q: str = Query(..., min_length=1, max_length=200)):
    return chain_brief.resolve(q)


@app.get("/api/chains/{chain_id}", summary="单条产业链持仓语境简报")
def chain_detail(chain_id: str):
    try:
        return chain_brief.brief(chain_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.get("/api/replay", summary="复盘房间：交割、感知账、执行账")
def replay(date: Optional[str] = Query(None)):
    return services.replay(date)


@app.get("/api/personas", summary="交易模式透镜")
def personas():
    return services.personas()


@app.get("/api/research/quick-brief", summary="LEGACY_QUICK_BRIEF", deprecated=True)
def research_quick_brief(q: str = Query(..., min_length=1, max_length=200)):
    packet = services.research(q)
    if isinstance(packet, dict):
        packet["legacy"] = "LEGACY_QUICK_BRIEF"
    return packet


@app.get("/api/research", summary="已退役的简报入口", deprecated=True)
def research():
    return {
        "ok": False,
        "legacy": "LEGACY_QUICK_BRIEF",
        "error_code": "USE_RESEARCH_SESSION",
        "error_message": "主入口已改为研究会话。兼容简报在 /api/research/quick-brief。",
    }


@app.get("/api/dialogue", summary="旧总控一轮：意图、下一槽、工作记忆", deprecated=True)
def dialogue(
    q: str = Query(..., min_length=1, max_length=400),
    persist: bool = Query(True),
):
    return services.dialogue(q, persist=persist)


class DialogueIn(BaseModel):
    q: str = ""
    persist: bool = True
    image_base64: Optional[str] = None
    mime: Optional[str] = None


@app.post("/api/dialogue", summary="旧总控一轮（可带交割截图）", deprecated=True)
def dialogue_post(body: DialogueIn):
    if not (body.q or "").strip() and not body.image_base64:
        raise HTTPException(status_code=400, detail="请说话或贴交割截图")
    return services.dialogue(
        body.q or "",
        persist=body.persist,
        image_base64=body.image_base64,
        mime=body.mime,
    )


@app.get("/api/session", summary="旧复盘会话（含历史）", deprecated=True)
def session():
    return services.dialogue_session()


@app.post("/api/session/reset", summary="清空旧会话槽位", deprecated=True)
def session_reset():
    return services.dialogue_reset()


@app.get("/api/tools", summary="旧运行时 Tool 白名单", deprecated=True)
def tools():
    return services.tools_catalog()


@app.get("/api/tools/{name}", summary="调用旧白名单 Tool（compact）", deprecated=True)
def tools_call(
    name: str,
    q: Optional[str] = Query(None),
    date: Optional[str] = Query(None),
    compact: bool = Query(True),
):
    try:
        args = {}
        if q is not None:
            args["q"] = q
        if date is not None:
            args["date"] = date
        return services.tools_call(name, args, compact=compact)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
