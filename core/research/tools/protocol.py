"""搜索工具的接口。夹具和以后的远程搜索都走同一个形状。"""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class WebSearchTool(Protocol):
    def search(self, query: str) -> list:
        """返回 Tool Result Contract 列表。失败时不编造来源。"""
        ...
