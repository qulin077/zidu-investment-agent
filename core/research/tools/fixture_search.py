"""用预先放好的来源回答搜索。不访问网络。"""
from __future__ import annotations

from core.research.tools.contract import to_tool_result


class FixtureSearchTool:
    def __init__(self, sources: list) -> None:
        self.sources = list(sources or [])

    def search(self, query: str) -> list:
        del query
        return [to_tool_result(row) for row in self.sources]
