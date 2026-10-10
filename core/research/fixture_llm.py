"""夹具模型。按任务类型返回事先写好的 JSON，不发网络请求。"""
from __future__ import annotations

import json
from pathlib import Path

from core.config import ROOT
from core.research.tools import read_research_note

FIXTURE_ROOT = ROOT / "evals" / "research" / "fixtures"
_FILES = {
    "PLANNER": "planner.json",
    "CLAIM_EXTRACTION": "claims.json",
    "THESIS": "thesis.json",
}


def case_for(question: str = "", theme: str = "") -> str:
    text = "{0} {1}".format(question or "", theme or "")
    if "光模块" in text:
        return "optical_module"
    if "半导体" in text:
        return "semiconductor_equipment"
    if any(token in text for token in ("电源", "Rubin", "供电")):
        return "ai_power"
    return ""


class FixtureResearchLLM:
    name = "fixture"
    last_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    def __init__(self, case: str) -> None:
        self.case = case

    def complete(self, task_type: str) -> dict:
        filename = _FILES.get(task_type)
        if not filename:
            raise KeyError("未知研究任务：{0}".format(task_type))
        path = FIXTURE_ROOT / self.case / filename
        return json.loads(path.read_text(encoding="utf-8"))

    def generate_structured(self, system: str, user: str, schema: dict, temperature: float = 0, timeout: int = 30) -> str:
        task = "PLANNER"
        if "摘录" in (system or "") or "CLAIM" in (system or ""):
            task = "CLAIM_EXTRACTION"
        elif "Thesis" in (system or "") or "起草" in (system or ""):
            task = "THESIS"
        return json.dumps(self.complete(task), ensure_ascii=False)


def load_case(case: str, as_of: str = "") -> dict:
    """把夹具 JSON 和笔记正文拼成一份可校验的研究草稿。"""
    base = FIXTURE_ROOT / case
    sources_doc = json.loads((base / "sources.json").read_text(encoding="utf-8"))
    claims_doc = json.loads((base / "claims.json").read_text(encoding="utf-8"))
    thesis_doc = json.loads((base / "thesis.json").read_text(encoding="utf-8"))
    sources = []
    for row in sources_doc.get("sources") or []:
        item = dict(row)
        if not item.get("body"):
            path = item.get("path") or item.get("url") or ""
            note = read_research_note(path)
            if not note.get("ok"):
                raise RuntimeError(note.get("message") or path)
            item["body"] = note["body"]
        sources.append(item)
    by_source = {row.get("local_id"): row.get("body") or "" for row in sources}
    for item in claims_doc.get("evidence") or []:
        body = by_source.get(item.get("source_local_id")) or ""
        span = item.get("evidence_text") or ""
        if span and span not in body:
            raise RuntimeError("夹具引文不在来源正文里：{0}".format(span))
    draft = dict(thesis_doc)
    if draft.get("market_scope") is None:
        draft["market_scope"] = []
    draft["sources"] = sources
    draft["claims"] = list(claims_doc.get("claims") or [])
    draft["evidence"] = list(claims_doc.get("evidence") or [])
    if as_of:
        draft["as_of"] = as_of
    return draft


def cases() -> tuple:
    return tuple(
        path.name for path in sorted(FIXTURE_ROOT.iterdir())
        if path.is_dir() and (path / "planner.json").is_file()
    )
