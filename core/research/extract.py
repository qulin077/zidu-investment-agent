"""Claim 只能从已打开的正文里来。搜索摘要不是证据。"""
from __future__ import annotations

import re

from core.research.source_guard import line_is_injection
from core.research.types import FORBIDDEN_PHRASES

# A broker's published target price, rating or revision is evidence about
# market expectations.  It is not the product issuing a recommendation.  Keep
# direct prescriptive language out of evidence while allowing the expectation
# itself to enter the claim/trace pipeline.
_EVIDENCE_ACTION_PHRASES = tuple(
    token for token in FORBIDDEN_PHRASES if token != "目标价"
)

def check_claim(claim: dict, source_text: str, known_ids=None) -> str:
    kind = (claim.get("claim_type") or "").upper()
    evidence = claim.get("evidence_text") or ""
    known = set(known_ids or [])
    if kind == "INFERENCE":
        premises = [item for item in (claim.get("premise_claim_ids") or []) if item]
        if not premises or any(item not in known for item in premises):
            return "INFERENCE_INVALID"
    if kind == "FACT" and (not evidence or evidence not in (source_text or "")):
        return "GROUNDING_FAILED"
    if evidence and evidence not in (source_text or ""):
        return "GROUNDING_FAILED"
    return ""


def claims_from_text(text: str, *, snippet: str = "", pages=None, limit: int = 6) -> list:
    body = text or ""
    spans = _candidates(body)
    ranked = sorted(spans, key=lambda item: (
        0 if any(token in item for token in ("公司是一家", "公司产品涵盖", "主要业务")) else 1,
        0 if "收入" in item else 1,
        0 if ("亿" in item or "%" in item) else 1,
        len(item),
    ))
    rows = []
    seen = set()
    for span in ranked:
        if span in seen:
            continue
        if snippet and span == snippet and snippet not in body:
            continue
        if span not in body:
            continue
        if _skip_span(span):
            continue
        seen.add(span)
        rows.append({
            "claim_type": "FACT",
            "text": span,
            "evidence_text": span,
            "premise_claim_ids": [],
            "location": _locate(span, pages),
        })
        if len(rows) >= limit:
            break
    return rows


def structured_claims_from_text(text: str, *, pages=None) -> list:
    """补足 PDF 表格里被换行拆开的关键财务行。evidence 仍是正文连续原文。"""
    body = text or ""
    patterns = (
        r"营业收入（元）\s+[-0-9,.]+\s+[-0-9,.]+\s+[-0-9,.]+%\s+[-0-9,.]+",
        r"归属于上市公司股东的\s*净利润（元）\s+[-0-9,.]+\s+[-0-9,.]+\s+[-0-9,.]+%\s+[-0-9,.]+",
        r"经营活动产生的现金流\s*量净额（元）\s+[-0-9,.]+\s+[-0-9,.]+\s+[-0-9,.]+%\s+[-0-9,.]+",
        r"公司是一家[^。]{10,220}。",
        r"公司产品涵盖[^。]{10,220}。",
    )
    rows = []
    for pattern in patterns:
        match = re.search(pattern, body)
        if not match:
            continue
        evidence = match.group(0).strip()
        rows.append({
            "claim_type": "FACT",
            "text": re.sub(r"\s+", " ", evidence),
            "evidence_text": evidence,
            "premise_claim_ids": [],
            "location": _locate(evidence, pages),
            "structured": True,
        })
    return rows


def broker_expectation_claims_from_text(
    text: str, *, title: str = "", limit: int = 4,
) -> list:
    """Normalize explicit broker target-price revisions from a read excerpt.

    This is deliberately narrower than semantic claim extraction.  The model
    still reads and analyses the document; this adapter only prevents an
    auditable ``from X to Y`` datapoint from being lost when the model spends
    its claim budget on the surrounding thesis and earnings assumptions.
    """
    body = text or ""
    if "目标价" not in body:
        return []
    brokers = (
        "花旗银行", "花旗", "美国银行", "美银", "高盛", "瑞银", "摩根士丹利",
        "摩根大通", "汇丰", "野村", "东方证券", "开源证券", "上海证券",
        "东吴证券", "华金证券", "国盛证券", "长江证券", "中信证券", "中金公司",
        "BofA Securities", "BofA", "Citi", "Goldman Sachs", "UBS",
    )
    rows = []
    seen = set()
    cursor = 0
    for sentence in re.findall(r"[^。\n]+(?:。|$)", body):
        position = body.find(sentence, cursor)
        if position >= 0:
            cursor = position + len(sentence)
        if "目标价" not in sentence or not any(
            token in sentence for token in ("上调", "下调", "调整", "提升", "推升")
        ):
            continue
        match = re.search(
            r"目标价.{0,24}?(?:从|由)\s*([0-9]+(?:\.[0-9]+)?)\s*元"
            r".{0,36}?(上调|下调|调整|提升|推升).{0,16}?(?:至|到)\s*"
            r"([0-9]+(?:\.[0-9]+)?)\s*元",
            sentence,
        )
        if not match:
            continue
        old_value, direction, new_value = match.group(1), match.group(2), match.group(3)
        key = (old_value, new_value)
        if key in seen:
            continue
        seen.add(key)
        context_start = max(0, position - 600) if position >= 0 else 0
        context = " ".join((title or "", body[context_start:max(cursor, 0)]))
        estimator = next((name for name in brokers if name.lower() in context.lower()), "来源机构待确认")
        if estimator == "花旗银行":
            estimator = "花旗"
        elif estimator in ("美国银行", "BofA Securities", "BofA"):
            estimator = "美银/美国银行（BofA）"
        evidence = sentence.strip()
        rows.append({
            "claim_type": "ESTIMATE",
            "text": "{0}将目标价从{1}元{2}至{3}元。".format(
                estimator, old_value, direction, new_value,
            ),
            "evidence_text": evidence,
            "premise_claim_ids": [],
            "location": "卖方目标价修订",
            "estimator": estimator,
            "period": "",
            "comparison_basis": "目标价从{0}元{1}至{2}元".format(
                old_value, direction, new_value,
            ),
            "structured": True,
        })
        if len(rows) >= limit:
            break
    return rows


def _candidates(text: str) -> list:
    found = []
    raw = text or ""
    if "<" in raw and ">" in raw:
        raw = re.sub(r"<[^>]+>", " ", raw)
        raw = re.sub(r"[ \t]+", " ", raw)
    for line in raw.splitlines():
        if "|" in line:
            parts = [part.strip() for part in line.strip().strip("|").split("|")]
        else:
            parts = [line.strip()]
        for part in parts:
            cleaned = re.sub(r"\*\*", "", part).strip()
            cleaned = re.sub(r"^[-*]\s*", "", cleaned).strip()
            cleaned = re.sub(r"^真[:：]\s*", "", cleaned).strip()
            for piece in re.split(r"[。\n]+|(?<=\.)\s+", cleaned):
                piece = piece.strip()
                if piece:
                    found.append(piece)
    return found


def accept_span(span: str) -> bool:
    return not _skip_span(span or "")


def accept_research_span(span: str, research_kind: str = "company") -> bool:
    """Accept grounded evidence for the selected research object.

    The legacy company filter intentionally requires Chinese operating or
    financial vocabulary.  Applying it to an industry/theme silently rejected
    official English policies even after the page had been opened and the
    quote had been grounded.  Non-company research keeps the same injection,
    forbidden-language and length guards, but uses domain vocabulary in either
    Chinese or English.
    """
    if research_kind == "company":
        if accept_span(span):
            return True
        # Sell-side/news excerpts often keep the attribution, revision basis
        # and forecast table in one continuous paragraph. The generic company
        # guard caps spans at 180 characters to suppress filing boilerplate;
        # applying that cap here discarded exactly the institution/date/from-
        # to evidence needed for expectation tracking.
        value = (span or "").strip()
        expectation_tokens = (
            "目标价", "盈利预测", "一致预期", "评级", "上调", "下调",
            "EPS", "PE", "分析师", "券商", "证券研究",
        )
        if len(value) < 10 or len(value) > 600:
            return False
        if value.startswith("#") or set(value) <= set("-| "):
            return False
        if line_is_injection(value):
            return False
        if any(token in value for token in _EVIDENCE_ACTION_PHRASES):
            return False
        if any(token in value for token in ("继续阅读", "查看全文")):
            return False
        return (
            len(re.findall(r"[\u4e00-\u9fff]", value)) >= 6
            and any(token in value for token in expectation_tokens)
        )
    value = (span or "").strip()
    if len(value) < 10 or len(value) > 420:
        return False
    if value.startswith("#") or set(value) <= set("-| "):
        return False
    if line_is_injection(value):
        return False
    if any(token in value for token in _EVIDENCE_ACTION_PHRASES):
        return False
    if any(token in value for token in ("继续阅读", "查看全文")):
        return False
    lowered = value.lower()
    vocabulary = (
        # Cross-industry / event evidence.
        "政策", "规则", "监管", "框架", "风险", "安全", "治理", "实施", "发布",
        "影响", "产业链", "供给", "需求", "成本", "价格", "产能", "技术", "市场",
        "预期", "里程碑", "时间表", "生效", "评测", "红队", "越狱", "对齐", "防护",
        "policy", "framework", "risk", "safety", "security", "governance", "alignment",
        "evaluation", "safeguard", "jailbreak", "deployment", "capability", "regulation",
        "standard", "incident", "timeline", "deadline", "market", "cost", "demand", "supply",
    )
    if not any(token in lowered for token in vocabulary):
        return False
    chinese = len(re.findall(r"[\u4e00-\u9fff]", value))
    english_words = len(re.findall(r"\b[A-Za-z][A-Za-z'-]{2,}\b", value))
    return chinese >= 6 or english_words >= 5


def _skip_span(span: str) -> bool:
    if len(span) < 6 or len(span) > 180:
        return True
    if span.startswith("#") or set(span) <= set("-| "):
        return True
    if line_is_injection(span):
        return True
    if "继续阅读" in span or "查看全文" in span:
        return True
    if "下滑" in span and "<" in span:
        return True
    if len(re.findall(r"[\u4e00-\u9fff]", span)) < 6:
        return True
    if any(token in span for token in _EVIDENCE_ACTION_PHRASES):
        return True
    # 年报中这些句子虽然包含“收入/%”，但只是审计或内控口径，不是公司经营事实。
    # 把它们当作核心 Claim 会制造一种“有引用但答非所问”的假严谨。
    if any(token in span for token in (
        "一般缺陷", "重要缺陷", "重大缺陷", "财务报表营业收入的比例",
        "超过营业收入的 1%", "超过营业收入的1%", "小于 2%", "小于2%",
    )):
        return True
    if span.startswith(("业收入的", "果超过营业收入", "重要缺陷；如果")):
        return True
    if span.endswith(("同比增", "则为", "；如")):
        return True
    useful = any(token in span for token in (
        "亿", "%", "收入", "利润", "毛利", "销量", "订单", "客户", "产能",
        "资本开支", "市场份额", "送样", "认证", "量产", "主要业务", "公司产品",
        "生产和销售", "出货", "预期", "预测", "上调", "下调", "验证",
        "NPO", "CPO", "可插拔", "FCC", "限制", "美国制造", "BOM",
        "光芯片", "DSP", "光引擎", "FAU", "价值量",
    ))
    return not useful


def _locate(span: str, pages) -> str:
    for page in pages or []:
        if span and span in (page.get("text") or ""):
            return "page {0}".format(page.get("page"))
    return ""
