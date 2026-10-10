"""Explicit outer-tool registry and permission boundary for the Agent harness."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict

from core.agent.skill_registry import get as get_skill

READ_ONLY = "READ_ONLY"
WRITE_DRAFT = "WRITE_DRAFT"
USER_CONFIRM = "USER_CONFIRM"


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: dict


@dataclass
class ToolSpec:
    name: str
    handler: Callable[[ToolCall], dict]
    permission: str = READ_ONLY
    description: str = ""
    confirmation_intents: tuple = ()
    internal: bool = False


class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if not spec.name or spec.name in self._tools:
            raise ValueError("重复或空的 Agent Tool：{0}".format(spec.name or "<empty>"))
        self._tools[spec.name] = spec

    def names(self) -> tuple:
        return tuple(self._tools)

    def descriptions(self, include_internal: bool = False) -> list:
        return [
            {
                "name": spec.name,
                "description": spec.description or spec.name,
                "permission": spec.permission,
            }
            for spec in self._tools.values()
            if include_internal or not spec.internal
        ]

    def execute(self, call: ToolCall) -> dict:
        spec = self._tools.get(call.name)
        if spec is None:
            return {
                "ok": False, "status": "DENIED", "error_code": "TOOL_NOT_REGISTERED",
                "answer": "这个动作不在当前 Agent 的工具白名单里。",
            }
        if call.name != "conversation" and not spec.internal:
            skill = get_skill(call.name)
            if not skill:
                return {
                    "ok": False, "status": "DENIED", "error_code": "SKILL_NOT_REGISTERED",
                    "answer": "这个 Skill 没有注册，不能执行。",
                }
            if bool(skill.get("write_action")) and spec.permission == READ_ONLY:
                return {
                    "ok": False, "status": "DENIED", "error_code": "WRITE_PERMISSION_MISMATCH",
                    "answer": "这个写入动作没有通过权限配置。",
                }
        intent = ((call.arguments.get("route") or {}).get("intent") or "")
        needs_confirmation = spec.permission == USER_CONFIRM or intent in spec.confirmation_intents
        if needs_confirmation and not bool(call.arguments.get("confirmed")):
            return {
                "ok": False, "status": "AWAITING_APPROVAL", "error_code": "USER_CONFIRM_REQUIRED",
                "answer": "这个动作需要你明确确认后才能执行。",
            }
        result = spec.handler(call)
        if not isinstance(result, dict):
            return {
                "ok": False, "status": "FAILED", "error_code": "INVALID_TOOL_RESULT",
                "answer": "工具没有返回有效结果。",
            }
        result.setdefault("ok", True)
        result.setdefault("status", "COMPLETED")
        return result
