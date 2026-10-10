"""研究模型的提示词版本。提示词不是事实来源。"""
from __future__ import annotations

import json

from core.research.types import (
    CLAIM_EXTRACTOR_PROMPT_VERSION,
    RESEARCH_PLANNER_PROMPT_VERSION,
    THESIS_PROMPT_VERSION,
)

VERSIONS = {
    "planner": RESEARCH_PLANNER_PROMPT_VERSION,
    "extractor": CLAIM_EXTRACTOR_PROMPT_VERSION,
    "thesis": THESIS_PROMPT_VERSION,
}

EXTRACT_SYSTEM = """你是行业研究摘录员。只根据用户给出的正文摘录输出 JSON。
规则：
- 引文必须是摘录中的连续原文。
- FACT / ESTIMATE / INFERENCE / OPINION 分开。
- 券商预测是 ESTIMATE。推断必须带 premise_claim_ids。
- 不知道就写 open_questions，不要编数字、客户、份额。
- 不要写买入、卖出、目标价、仓位。
- 两个数字冲突时并列写出，不要取平均。
"""

THESIS_SYSTEM = """你是行业研究起草员。只根据已经给出的 Claim 和 Evidence 写 Thesis JSON。
每条判断放进 evidence_refs。没有证据的点放进 open_questions，值用 UNKNOWN。
不要写买入、卖出、目标价、仓位，不要把公司暴露写成推荐名单。
"""


def versions_json() -> str:
    return json.dumps(VERSIONS, ensure_ascii=False)
