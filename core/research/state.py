"""一次研究运行的状态。循环次数有上限，动作只有六种。"""
from __future__ import annotations

from typing import List, Optional

ACTIONS = (
    "SEARCH",
    "READ_SOURCE",
    "EXTRACT_CLAIMS",
    "RESOLVE_GAP",
    "BUILD_SECTION",
    "FINISH",
)


class ResearchState:
    def __init__(
        self,
        question: str,
        *,
        project_id: str = "",
        skill: str = "industry-research",
        as_of: str = "",
        max_iterations: int = 8,
        max_llm_calls: int = 20,
    ) -> None:
        self.run_id = ""
        self.project_id = project_id
        self.question = question
        self.skill = skill
        self.as_of = as_of
        self.status = "PLANNING"
        self.plan: List[dict] = []
        self.completed_tasks: List[dict] = []
        self.current_task: Optional[dict] = None
        self.sources: List[dict] = []
        self.claims: List[dict] = []
        self.conflicts: List[dict] = []
        self.value_chain: List[dict] = []
        self.company_mappings: List[dict] = []
        self.open_questions: List[str] = []
        self.critical_gaps: List[str] = []
        self.iteration = 0
        self.max_iterations = max_iterations
        self.max_llm_calls = max_llm_calls
        self.llm_calls = 0
        self.thesis_ready = False
        self.task_graph: List[dict] = []
        self.pending_tasks: List[dict] = []
        self.search_queries_used: List[str] = []
        self.read_source_ids: List[str] = []
        self.claim_graph: List[dict] = []
        self.critical_claim_ids: List[str] = []
        self.disconfirmation_tasks: List[dict] = []
        self.coverage: dict = {}
        self.completion_score = 0
        self.wave = 0
        self.max_waves = 4

    def snapshot(self) -> dict:
        return {
            "run_id": self.run_id,
            "project_id": self.project_id,
            "question": self.question,
            "skill": self.skill,
            "as_of": self.as_of,
            "status": self.status,
            "plan": self.plan,
            "completed_tasks": self.completed_tasks,
            "current_task": self.current_task,
            "sources": [_public_source(row) for row in self.sources],
            "claims": self.claims,
            "conflicts": self.conflicts,
            "value_chain": self.value_chain,
            "company_mappings": self.company_mappings,
            "open_questions": self.open_questions,
            "critical_gaps": self.critical_gaps,
            "iteration": self.iteration,
            "max_iterations": self.max_iterations,
            "thesis_ready": self.thesis_ready,
            "llm_calls": self.llm_calls,
            "task_graph": self.task_graph,
            "pending_tasks": self.pending_tasks,
            "search_queries_used": self.search_queries_used,
            "read_source_ids": self.read_source_ids,
            "claim_graph": self.claim_graph,
            "critical_claim_ids": self.critical_claim_ids,
            "disconfirmation_tasks": self.disconfirmation_tasks,
            "coverage": self.coverage,
            "completion_score": self.completion_score,
            "wave": self.wave,
            "max_waves": self.max_waves,
        }


def _public_source(row: dict) -> dict:
    copied = dict(row)
    body = copied.get("body") or copied.get("content") or ""
    copied["body"] = "[omitted {0} chars]".format(len(body))
    copied.pop("content", None)
    return copied


def research_action(action: str, task_id: str, query: str = "", reason: str = "", expected_output: str = "") -> dict:
    if action not in ACTIONS:
        raise ValueError("ACTION_NOT_ALLOWED")
    return {
        "action": action,
        "task_id": task_id,
        "query": query,
        "reason": reason,
        "expected_output": expected_output,
    }


def choose_next_task(state: ResearchState) -> dict:
    done = [item.get("action") for item in state.completed_tasks]
    for action in ACTIONS:
        if action not in done:
            return research_action(
                action,
                "LOOP",
                state.question,
                "Harness 只允许固定动作，不接受自由生成的下一步。",
                action,
            )
    return research_action("FINISH", "LOOP", state.question, "计划内动作已经走完。", "thesis")


def loop_finished(state: ResearchState) -> bool:
    return any(item.get("action") == "FINISH" for item in state.completed_tasks)
