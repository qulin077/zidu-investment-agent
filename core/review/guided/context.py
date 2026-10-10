"""Review Context builder。只允许 Decision 链上的事实，不加载新闻/研报。"""
from core.review.guided.facts import build_context

__all__ = ["build_context"]
