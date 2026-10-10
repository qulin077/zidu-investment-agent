"""LLM 适配。业务层只依赖 generate_structured，不直接绑供应商。"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional, Protocol

from core.http import FetchError, HttpClient


class LLMError(RuntimeError):
    pass


class LLMClient(Protocol):
    name: str

    def generate_structured(
        self,
        system: str,
        user: str,
        schema: dict,
        temperature: float = 0,
        timeout: int = 30,
    ) -> str:
        ...


@dataclass
class MockLLM:
    """测试夹具。payload 是要返回的 JSON 对象或字符串。"""

    payload: Any
    name: str = "mock"

    def generate_structured(self, system, user, schema, temperature=0, timeout=30) -> str:
        if callable(self.payload):
            data = self.payload(system, user)
        else:
            data = self.payload
        if isinstance(data, str):
            return data
        return json.dumps(data, ensure_ascii=False)


class OpenAICompatibleClient:
    def __init__(
        self,
        api_key: str = "",
        base_url: str = "",
        model: str = "",
        reasoning_effort: str = "",
        http: Optional[HttpClient] = None,
    ) -> None:
        self.api_key = api_key or os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY") or ""
        self.base_url = (
            base_url or os.environ.get("LLM_BASE_URL") or os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1"
        ).rstrip("/")
        self.model = model or os.environ.get("LLM_MODEL") or "gpt-4o-mini"
        self.reasoning_effort = reasoning_effort or os.environ.get("LLM_REASONING_EFFORT") or ""
        self.name = self.model
        self.calls = 0
        self.last_usage = None
        self._http = http or HttpClient(referer="")

    def generate_structured(self, system, user, schema, temperature=0, timeout=30) -> str:
        if not self.api_key:
            raise LLMError("未配置 OPENAI_API_KEY / LLM_API_KEY")
        self.calls += 1
        body = {
            "model": self.model,
            "temperature": temperature,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "response_format": {"type": "json_object"},
        }
        if self.reasoning_effort:
            body["reasoning_effort"] = self.reasoning_effort
        url = "{0}/chat/completions".format(self.base_url)
        try:
            data = self._http.post_json(
                url,
                json_body=body,
                headers={
                    "Authorization": "Bearer {0}".format(self.api_key),
                    "Content-Type": "application/json",
                },
                timeout=timeout,
                attempts=2,
                cache_ttl=0,
            )
        except FetchError as exc:
            raise LLMError(str(exc)) from exc
        self.last_usage = data.get("usage") if isinstance(data, dict) else None
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError("模型响应缺少 content") from exc


class FixtureProvider:
    """离线占位。研究循环使用 FixtureResearchLLM，这里保证不会发请求。"""

    name = "fixture"
    last_usage = None

    def generate_structured(self, system, user, schema, temperature=0, timeout=30) -> str:
        raise LLMError("FixtureProvider 不连接远程模型。")


OpenAICompatibleProvider = OpenAICompatibleClient


def default_client() -> LLMClient:
    """有 key 用远程模型；否则用受限启发式，Eval 和本地开发都能跑。"""
    if os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY"):
        return OpenAICompatibleClient()
    from core.review.recorder.heuristic import HeuristicLLM
    return HeuristicLLM()
