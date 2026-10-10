"""Long-lived event research policy.

Events are versioned hypotheses, not news cards.  The policy verifies the
event, establishes the pre-event baseline, maps the causal transmission, and
keeps checking milestones until the impact is realized, fades, or is invalidated.
"""
from __future__ import annotations

import re

from core.research import topic_playbooks


REQUIRED_EVIDENCE = (
    "EVENT_DEFINITION",
    "BASELINE",
    "STATUS_STAGE",
    "WHAT_CHANGED",
    "CAUSAL_CHAIN",
    "ECONOMIC_VARIABLES",
    "AFFECTED_NODES",
    "EXPECTATION_DELTA",
    "SCENARIOS",
    "MILESTONES",
    "EARNINGS_LINK",
    "RISK_INVALIDATION",
)

THEME_REQUIRED_EVIDENCE = (
    "DEFINITION_SCOPE",
    "ORIGIN_BASELINE",
    "TIMELINE",
    "CURRENT_CATALYSTS",
    "ACTOR_MAP",
    "TECHNICAL_POLICY_TRACKS",
    "CAUSAL_CHAIN",
    "ECONOMIC_VARIABLES",
    "AFFECTED_NODES",
    "MARKET_NARRATIVE",
    "EXPECTATION_DELTA",
    "MILESTONES",
    "RISK_INVALIDATION",
)

EVIDENCE_LABELS = {
    "DEFINITION_SCOPE": "定义与边界",
    "ORIGIN_BASELINE": "起源与历史基线",
    "TIMELINE": "演化时间线",
    "CURRENT_CATALYSTS": "近期直接催化",
    "ACTOR_MAP": "关键主体与行动",
    "TECHNICAL_POLICY_TRACKS": "技术与政策分支",
    "CAUSAL_CHAIN": "逻辑与影响传导",
    "ECONOMIC_VARIABLES": "经济变量",
    "AFFECTED_NODES": "产业与板块影响",
    "MARKET_NARRATIVE": "市场叙事与事实差",
    "EXPECTATION_DELTA": "预期变化",
    "MILESTONES": "下一验证点",
    "RISK_INVALIDATION": "风险、反证与失效条件",
}

ALL_EVIDENCE = tuple(dict.fromkeys(REQUIRED_EVIDENCE + THEME_REQUIRED_EVIDENCE))

EVENT_STATES = (
    "UNVERIFIED", "ANNOUNCED", "DEFINED", "IMPLEMENTING",
    "REALIZED", "FADING", "INVALIDATED",
)

_PATTERNS = {
    "EVENT_DEFINITION": ("宣布", "发布", "公告", "政策", "规则", "协议", "订单", "事件"),
    "BASELINE": ("此前", "原来", "原计划", "基线", "历史", "之前", "旧"),
    "STATUS_STAGE": ("传闻", "征求意见", "正式", "生效", "实施", "量产", "交付", "兑现", "终止", "撤回"),
    "WHAT_CHANGED": ("变化", "新增", "提高", "降低", "上调", "下调", "替代", "限制"),
    "CAUSAL_CHAIN": ("导致", "带动", "影响", "传导", "因此", "从而", "依赖"),
    "ECONOMIC_VARIABLES": ("数量", "出货", "价格", "成本", "价值量", "资本开支", "产能", "订单", "毛利", "预算", "支出", "投入", "算力", "罚款", "insurance", "spending", "investment", "compliance cost"),
    "AFFECTED_NODES": ("上游", "中游", "下游", "供应商", "客户", "环节", "产业链", "网络安全", "数据安全", "模型评测", "可观测性", "合规服务", "审计", "保险", "cybersecurity", "observability", "compliance"),
    "EXPECTATION_DELTA": ("预期", "预测", "上调", "下调", "一致预期", "市场认为", "指引"),
    "SCENARIOS": ("情景", "如果", "概率", "基准", "乐观", "悲观", "取决于"),
    "MILESTONES": ("里程碑", "时间表", "截止", "生效日期", "目标日期", "deadline", "roadmap", "by 20"),
    "EARNINGS_LINK": ("收入", "利润", "现金流", "财报", "业绩", "毛利率", "合同负债"),
    "RISK_INVALIDATION": ("风险", "不确定", "失败", "延迟", "取消", "证伪", "失效", "不及预期"),
    "DEFINITION_SCOPE": ("定义", "是指", "范围", "边界", "alignment", "misuse", "model security", "governance"),
    "ORIGIN_BASELINE": ("起源", "最初", "早期", "此前", "历史", "baseline", "2023", "2024"),
    "TIMELINE": ("时间线", "演进", "随后", "之后", "更新", "版本", "发布于", "updated", "launched"),
    "CURRENT_CATALYSTS": ("最新", "近期", "催化", "事故", "事件", "升级", "加强", "更新", "辞职", "警告", "谈判", "倡议", "latest", "incident", "resign", "talks", "warning"),
    "ACTOR_MAP": ("OpenAI", "Anthropic", "DeepMind", "Meta", "NIST", "欧盟", "政府", "监管", "研究机构"),
    "TECHNICAL_POLICY_TRACKS": ("评测", "红队", "越狱", "监控", "防护", "安全标准", "对齐", "模型权重", "网络安全", "生物安全", "jailbreak", "safeguard", "evaluation"),
    "MARKET_NARRATIVE": ("市场叙事", "受益", "承压", "利好", "利空", "估值", "主题投资", "板块", "market narrative"),
}

_EVENT_HINTS = (
    "Rubin", "Blackwell", "AI安全", "美伊战争", "关税", "制裁", "FCC",
    "新规", "政策", "发布会", "新品", "并购", "重组", "订单", "涨价", "停产",
)


def subject_from_question(question: str, fallback: str = "") -> str:
    value = re.sub(r"\s+", " ", (question or "").strip())
    routed = topic_playbooks.route(value)
    if routed:
        return routed.get("canonical_name") or value
    for hint in _EVENT_HINTS:
        if hint.lower() in value.lower():
            # Keep a meaningful phrase around generic event classes.
            if hint in ("政策", "新规", "发布会", "新品", "并购", "重组", "订单", "涨价", "停产"):
                break
            return hint
    match = re.search(r"(?:研究|分析|跟踪|看看|核对)?(?:一下)?(.{2,36}?)(?:这件事|事件|有什么影响|意味着什么|带来什么)", value)
    if match:
        return match.group(1).strip("，。 你帮我请")
    return (fallback or value[:36] or "事件主题").strip()


def object_kind(name: str = "", question: str = "") -> str:
    return "EVOLVING_THEME" if topic_playbooks.is_theme("{0} {1}".format(name, question)) else "DISCRETE_EVENT"


def resolve_event(question: str, previous: dict | None = None, hint: str = "") -> dict:
    current = dict(previous or {})
    raw_name = (hint or subject_from_question(question, current.get("canonical_name") or "")).strip()
    name = topic_playbooks.canonical_name("{0} {1}".format(raw_name, question)) if topic_playbooks.is_theme("{0} {1}".format(raw_name, question)) else raw_name
    return {
        "status": "RESOLVED" if name and name != "事件主题" else "UNVERIFIED",
        "canonical_name": name,
        "ticker": "", "exchange": "", "path": current.get("path") or "",
        "universe_status": "NOT_APPLICABLE", "aliases": [name] if name else [],
        "object_kind": object_kind(name, question),
        "chains": current.get("chains") or [], "verified_source": "",
    }


def search_action(query: str, reason: str, success_condition: str, target_evidence: str = "") -> dict:
    row = {"action": "SEARCH", "query": query.strip(), "reason": reason.strip(), "success_condition": success_condition.strip()}
    if target_evidence:
        row["target_evidence"] = target_evidence
    return row


def finish_action(reason: str) -> dict:
    return {"action": "FINISH", "query": "", "reason": reason or "", "success_condition": ""}


def valid_query(query: str, name: str, ticker: str = "") -> bool:
    value = re.sub(r"\s+", " ", (query or "").strip())
    topic = topic_playbooks.route(name)
    if topic:
        allowed_markers = [
            name,
            topic.get("search_name") or "",
            *(topic.get("actors") or []),
            *(topic.get("source_domains") or []),
        ]
        names_targeted = any(marker and str(marker).lower() in value.lower() for marker in allowed_markers)
    else:
        names_targeted = not name or name in value
    return (
        4 <= len(value) <= 140
        and "\n" not in (query or "")
        and names_targeted
        and not any(token in value.lower() for token in ("system prompt", "developer message", "建议买入", "目标价"))
    )


def plan_tasks(name: str, question: str) -> list[tuple[str, str]]:
    if object_kind(name, question) == "EVOLVING_THEME":
        return [
            ("DEFINITION_SCOPE", "这个主题准确指什么、不包括什么，安全与治理有哪些分支？"),
            ("ORIGIN_BASELINE", "概念从哪里起源，主题升温前的技术和治理基线是什么？"),
            ("TIMELINE", "关键子事件如何按时间演进，哪些是转折点而非重复报道？"),
            ("CURRENT_CATALYSTS", "为什么现在重新升温，直接催化分别来自哪些主体和事件？"),
            ("ACTOR_MAP", "公司、监管、标准组织和研究机构各自采取了什么行动？"),
            ("TECHNICAL_POLICY_TRACKS", "技术风险、评测防护、监管治理等分支分别发展到哪一步？"),
            ("CAUSAL_CHAIN", "能力、风险、事故或规则如何传导到需求、成本和商业行为？"),
            ("ECONOMIC_VARIABLES", "安全投入、合规成本、算力或保险等经济变量如何变化？"),
            ("AFFECTED_NODES", "哪些产业环节直接受益、间接受益或承压，成立条件是什么？"),
            ("MARKET_NARRATIVE", "市场现在交易什么叙事，叙事与已验证事实差在哪里？"),
            ("EXPECTATION_DELTA", "相较此前，技术、政策和商业预期发生了什么修订？"),
            ("MILESTONES", "未来哪些日期、标准、评测或披露可以验证主题继续或衰减？"),
            ("RISK_INVALIDATION", "哪些反证会削弱当前逻辑，哪些只是短期炒作？"),
        ]
    return [
        ("EVENT_DEFINITION", "事件原文、主体、时间和适用范围是什么？"),
        ("BASELINE", "事件发生前的规则、配置、供需或市场预期是什么？"),
        ("STATUS_STAGE", "当前处于传闻、宣布、明确、实施、兑现还是失效阶段？"),
        ("WHAT_CHANGED", "相对基线真正改变了哪个变量？"),
        ("CAUSAL_CHAIN", "变化通过哪些中间变量传到产业链和公司？"),
        ("ECONOMIC_VARIABLES", "数量、价格、成本、价值量和资本开支改变多少？"),
        ("AFFECTED_NODES", "哪些产业链节点直接、间接受益或承压？"),
        ("EXPECTATION_DELTA", "事件前后市场预期如何变化？"),
        ("SCENARIOS", "基准、上行和下行情景的条件分别是什么？"),
        ("MILESTONES", "下一里程碑、日期和核对来源是什么？"),
        ("EARNINGS_LINK", "是否已经兑现到订单、收入、利润或现金流？"),
        ("RISK_INVALIDATION", "什么事实会使影响链失效？"),
    ]


def initial_execution(name: str, question: str, kind: str, ticker: str = "", since: str = "") -> dict:
    if object_kind(name, question) == "EVOLVING_THEME":
        required = THEME_REQUIRED_EVIDENCE
        first_queries = topic_playbooks.gap_queries(name, "DEFINITION_SCOPE")
        query = first_queries[0] if first_queries else f"{name} 定义 起源 范围 官方"
        if kind == "followup":
            latest = topic_playbooks.gap_queries(name, "CURRENT_CATALYSTS")
            query = (latest[0] if latest else f"{name} 最新 进展 官方 变化") + (" " + str(since)[:10] if since else "")
            reason = "先核对上次主题档案后出现的新子事件、官方动作和叙事变化。"
        else:
            reason = "先定义主题边界和分支，再分别建立起源、时间线与影响链，避免把长期主题伪装成一件公告。"
        questions = dict(plan_tasks(name, question))
        return {
            "mode": "THEME_EVIDENCE_CONVERGENCE",
            "object_kind": "EVOLVING_THEME",
            "topic_playbook": topic_playbooks.route(name),
            "hypotheses": [
                {"id": f"TH{index}", "text": questions[key], "evidence": key, "status": "OPEN"}
                for index, key in enumerate(required, start=1)
            ],
            "required_evidence": list(required),
            "next_action": search_action(
                query, reason, "找到主题定义、适用范围和关键分支的一手或权威材料。",
                "CURRENT_CATALYSTS" if kind == "followup" else "DEFINITION_SCOPE",
            ),
            "completed_actions": [], "coverage": {key: False for key in required},
            "stop_conditions": ["主题关键证据已覆盖", "没有安全且不重复的新查询"],
            "stop_reason": "", "ticker": "",
        }
    if kind == "followup":
        query = f"{name} 最新进展 官方 里程碑 实施 兑现 风险 {str(since)[:10]}".strip()
        reason = "先核对上次档案后，事件状态、时间表和兑现证据是否变化。"
    else:
        query = f"{name} 官方 原文 公告 时间表 适用范围".strip()
        reason = "先确认事件本身、来源和当前状态，不从市场叙事直接推演。"
    hypotheses = [
        ("事件定义、主体、时间和适用范围可以由原文确认。", "EVENT_DEFINITION"),
        ("事件前的基线可以明确。", "BASELINE"),
        ("事件当前处于传闻、宣布、实施还是兑现阶段。", "STATUS_STAGE"),
        ("相对基线真正改变的变量可以被识别。", "WHAT_CHANGED"),
        ("影响链条包含可验证的中间变量。", "CAUSAL_CHAIN"),
        ("数量、价格、成本、价值量或资本开支至少一项可量化。", "ECONOMIC_VARIABLES"),
        ("受影响的产业链节点可以被定位。", "AFFECTED_NODES"),
        ("事件前后市场预期的差异可以被记录。", "EXPECTATION_DELTA"),
        ("基准、上行和下行情景的条件可以被区分。", "SCENARIOS"),
        ("下一里程碑、日期和核对来源可以被列出。", "MILESTONES"),
        ("事件能否兑现到订单、收入、利润或现金流可以被跟踪。", "EARNINGS_LINK"),
        ("至少一个失效条件可以被明确。", "RISK_INVALIDATION"),
    ]
    return {
        "mode": "EVENT_EVIDENCE_CONVERGENCE",
        "object_kind": "DISCRETE_EVENT",
        "hypotheses": [
            {"id": f"EH{index}", "text": text, "evidence": evidence, "status": "OPEN"}
            for index, (text, evidence) in enumerate(hypotheses, start=1)
        ],
        "required_evidence": list(REQUIRED_EVIDENCE),
        "next_action": search_action(query, reason, "找到事件原始公告、规则、发布材料或权威原文。"),
        "completed_actions": [], "coverage": {key: False for key in REQUIRED_EVIDENCE},
        "stop_conditions": ["关键证据已覆盖", "没有安全且不重复的新查询"],
        "stop_reason": "", "ticker": "",
    }


def evidence_coverage(claims: list) -> dict:
    blob = "\n".join(f"{row.get('text') or ''} {row.get('evidence_text') or ''}" for row in claims or [])
    coverage = {key: any(token.lower() in blob.lower() for token in tokens) for key, tokens in _PATTERNS.items()}
    # “验证” is common in generic prose and previously made the product claim
    # that a milestone existed when no date or target had been found.
    coverage["MILESTONES"] = coverage.get("MILESTONES", False) and bool(
        re.search(r"(?:20\d{2}[年\-/]\d{1,2}|\d{1,2}月\d{1,2}日|截止|生效日期|目标日期|deadline|roadmap|by 20)", blob, re.I)
    )
    return coverage


def missing_evidence(coverage: dict, required=None) -> list:
    return [key for key in (required or REQUIRED_EVIDENCE) if not coverage.get(key)]


def update_execution(execution: dict, claims: list) -> dict:
    coverage = evidence_coverage(claims)
    required = execution.get("required_evidence") or REQUIRED_EVIDENCE
    execution["coverage"] = {key: bool(coverage.get(key)) for key in required}
    for hypothesis in execution.get("hypotheses") or []:
        hypothesis["status"] = "SUPPORTED" if coverage.get(hypothesis.get("evidence") or "") else "OPEN"
    return execution["coverage"]


def deterministic_next(name: str, coverage: dict, used_queries: list, question: str = "") -> dict:
    if object_kind(name, question) == "EVOLVING_THEME":
        fallback = {
            "DEFINITION_SCOPE": f"{name} 定义 范围 对齐 滥用 模型安全 治理",
            "ORIGIN_BASELINE": f"{name} 起源 历史 基线 早期框架",
            "TIMELINE": f"{name} 时间线 演进 关键事件 更新",
            "CURRENT_CATALYSTS": f"{name} 最新 催化 OpenAI Anthropic 事件",
            "ACTOR_MAP": f"{name} OpenAI Anthropic DeepMind NIST 欧盟 行动",
            "TECHNICAL_POLICY_TRACKS": f"{name} 评测 红队 越狱 监控 防护 监管",
            "CAUSAL_CHAIN": f"{name} 能力 风险 防护 合规 影响机制",
            "ECONOMIC_VARIABLES": f"{name} 安全投入 合规成本 算力 保险 市场规模",
            "AFFECTED_NODES": f"{name} 网络安全 数据安全 模型评测 可观测性 合规 产业链",
            "MARKET_NARRATIVE": f"{name} 市场叙事 受益 承压 板块 条件",
            "EXPECTATION_DELTA": f"{name} 旧预期 新预期 政策 技术 商业 修订",
            "MILESTONES": f"{name} roadmap deadline 生效日期 评测标准 里程碑",
            "RISK_INVALIDATION": f"{name} 反证 局限 监管回撤 风险 失效",
        }
        purposes = {
            "DEFINITION_SCOPE": "先界定主题，避免把网络安全、模型对齐和监管治理混为一谈。",
            "ORIGIN_BASELINE": "建立主题升温前的历史基线。",
            "TIMELINE": "把独立子事件串成可核对的时间线。",
            "CURRENT_CATALYSTS": "确认近期升温究竟由哪些新事实触发。",
            "ACTOR_MAP": "核对关键主体的真实行动和立场。",
            "TECHNICAL_POLICY_TRACKS": "拆开技术风险、防护和治理分支。",
            "CAUSAL_CHAIN": "补齐主题到产业需求之间的中间变量。",
            "ECONOMIC_VARIABLES": "量化安全投入和合规成本等经济变量。",
            "AFFECTED_NODES": "定位直接、间接受益和承压环节及条件。",
            "MARKET_NARRATIVE": "区分市场正在交易的叙事与已验证事实。",
            "EXPECTATION_DELTA": "记录旧预期和新预期的变化。",
            "MILESTONES": "明确未来可验证日期、标准和披露。",
            "RISK_INVALIDATION": "主动寻找反证和主题失效条件。",
        }
        used = {re.sub(r"\s+", " ", item).strip() for item in used_queries or []}
        for category in THEME_REQUIRED_EVIDENCE:
            if coverage.get(category):
                continue
            queries = topic_playbooks.gap_queries(name, category) or [fallback[category]]
            for query in queries:
                if query not in used:
                    return search_action(
                        query, purposes[category],
                        "找到带主体、时间和口径的可引用正文，或确认该分支暂无公开证据。",
                        category,
                    )
        return finish_action("主题证据仍有缺口；当前安全且不重复的查询已用尽，缺项保留待核对。")
    candidates = [
        ("EVENT_DEFINITION", f"{name} 官方 原文 公告 主体 时间 适用范围", "确认事件定义与一手来源。"),
        ("BASELINE", f"{name} 此前 基线 原计划 原规则 原配置", "建立事件前基线。"),
        ("STATUS_STAGE", f"{name} 传闻 正式 生效 实施 进展 最新", "确认事件当前阶段。"),
        ("WHAT_CHANGED", f"{name} 新增 变化 对比 原来", "确认相对基线的增量。"),
        ("CAUSAL_CHAIN", f"{name} 影响机制 产业链 传导 约束", "补齐因果链的中间变量。"),
        ("ECONOMIC_VARIABLES", f"{name} 数量 价格 成本 价值量 资本开支 订单", "量化经济变量。"),
        ("AFFECTED_NODES", f"{name} 上游 下游 供应商 客户 产业链 环节", "定位影响节点。"),
        ("EXPECTATION_DELTA", f"{name} 原预期 新预期 预测 上调 下调 分歧", "记录预期变化。"),
        ("SCENARIOS", f"{name} 基准情景 上行情景 下行情景 条件", "建立条件化情景。"),
        ("MILESTONES", f"{name} 时间表 里程碑 批准 验证 交付 量产", "确认下一验证节点。"),
        ("EARNINGS_LINK", f"{name} 订单 收入 利润 现金流 财报 兑现", "核对财务兑现。"),
        ("RISK_INVALIDATION", f"{name} 延迟 取消 失败 风险 证伪", "主动寻找反证。"),
    ]
    used = {re.sub(r"\s+", " ", item).strip() for item in used_queries or []}
    for category, query, purpose in candidates:
        if coverage.get(category) or query in used:
            continue
        return search_action(query, purpose, "找到带时间、主体和口径的可引用正文，或确认该项暂无公开证据。")
    return finish_action("事件证据仍有缺口；当前安全且不重复的查询已用尽，缺项保留待核对。")


def _items(claims: list, category: str, limit: int = 6) -> list:
    result = []
    for row in claims or []:
        body = f"{row.get('text') or ''} {row.get('evidence_text') or ''}"
        if not any(token.lower() in body.lower() for token in _PATTERNS[category]):
            continue
        result.append({
            "text": row.get("text") or row.get("evidence_text") or "",
            "claim_id": row.get("local_id") or "", "source_id": row.get("source_id") or "",
            "claim_type": row.get("claim_type") or "", "period": row.get("period") or "",
        })
        if len(result) >= limit:
            break
    return result


def infer_state(claims: list) -> str:
    blob = " ".join(f"{row.get('text') or ''} {row.get('evidence_text') or ''}" for row in claims or [])
    if any(token in blob for token in ("取消", "撤回", "终止", "证伪")):
        return "INVALIDATED"
    if any(token in blob for token in ("收入确认", "已交付", "规模收入", "兑现")):
        return "REALIZED"
    if any(token in blob for token in ("实施", "执行", "量产", "建设中")):
        return "IMPLEMENTING"
    if any(token in blob for token in ("正式规则", "最终规则", "明确适用", "技术规格已明确", "合同已生效")):
        return "DEFINED"
    if any(token in blob for token in ("宣布", "公告", "发布")):
        return "ANNOUNCED"
    return "UNVERIFIED"


def infer_theme_stage(claims: list) -> str:
    blob = " ".join(f"{row.get('text') or ''} {row.get('evidence_text') or ''}" for row in claims or []).lower()
    if any(token in blob for token in ("降温", "撤回", "回滚", "fading", "rollback")):
        return "FADING"
    if any(token in blob for token in ("生效", "监管", "标准", "framework", "policy", "治理", "合规")):
        return "INSTITUTIONALIZING"
    if any(token in blob for token in ("商业化", "采购", "合同", "预算", "保险", "规模部署")):
        return "COMMERCIALIZING"
    if any(token in blob for token in ("最新", "升级", "事故", "加强", "热点", "accelerat")):
        return "ACCELERATING"
    return "EMERGING" if claims else "UNVERIFIED"


def _impact_map(rows: list) -> dict:
    result = {"positive": [], "negative": [], "conditional": []}
    for row in rows or []:
        text = row.get("text") or ""
        lowered = text.lower()
        if any(token in lowered for token in (
            "受益", "利好", "需求增加", "需求增长", "支出增加", "投入增加", "采购要求",
            "要求证明", "证据包", "认证需求", "rpf", "rfp", "demand", "spending growth",
        )):
            result["positive"].append(row)
        elif any(token in lowered for token in (
            "承压", "利空", "成本增加", "限制", "禁止", "责任增加", "罚款", "推迟", "延期",
            "竞争", "回报仍不明确", "compliance burden", "penalty", "delay", "restrict",
        )):
            result["negative"].append(row)
        else:
            result["conditional"].append(row)
    return result


def build_dossier(name: str, claims: list, sources: list, delta: dict, execution: dict, previous: dict | None = None) -> dict:
    coverage = evidence_coverage(claims)
    source_numbers = {row.get("local_id"): index for index, row in enumerate(sources or [], start=1)}
    required = tuple(execution.get("required_evidence") or REQUIRED_EVIDENCE)
    sections = {key.lower(): _items(claims, key) for key in required}
    for rows in sections.values():
        for row in rows:
            row["source_number"] = source_numbers.get(row.get("source_id"))
    added = {row.get("id") if isinstance(row, dict) else row for row in ((delta or {}).get("added_claims") or [])}
    changes = [row for row in claims or [] if row.get("local_id") in added]
    source_rows = [{
        "number": index, "id": row.get("local_id") or "", "title": row.get("title") or "来源",
        "url": row.get("url") or "", "published_at": row.get("published_at") or row.get("available_at") or "",
        "source_type": row.get("source_type") or "", "source_label": row.get("source_label") or "",
    } for index, row in enumerate(sources or [], start=1)]
    if execution.get("object_kind") == "EVOLVING_THEME" or object_kind(name) == "EVOLVING_THEME":
        affected = sections.get("affected_nodes") or []
        narrative = sections.get("market_narrative") or []
        stage = infer_theme_stage(claims)
        return {
            "name": name,
            "object_kind": "EVOLVING_THEME",
            "state": stage,
            "state_history": list((previous or {}).get("state_history") or []) + ([stage] if claims else []),
            "playbook": execution.get("topic_playbook") or topic_playbooks.route(name),
            "one_line_view": (
                (sections.get("current_catalysts") or [{}])[0].get("text")
                or (sections.get("definition_scope") or [{}])[0].get("text")
                or "主题边界和近期催化仍待一手来源核对。"
            ),
            "definition_scope": sections.get("definition_scope") or [],
            "origin_baseline": sections.get("origin_baseline") or [],
            "timeline": sections.get("timeline") or [],
            "current_catalysts": sections.get("current_catalysts") or [],
            "actor_map": sections.get("actor_map") or [],
            "technical_policy_tracks": sections.get("technical_policy_tracks") or [],
            "causal_chain": sections.get("causal_chain") or [],
            "economic_variables": sections.get("economic_variables") or [],
            "affected_nodes": affected,
            "impact_map": _impact_map(affected + narrative),
            "market_narrative": narrative,
            "expectation_delta": sections.get("expectation_delta") or [],
            "milestones": sections.get("milestones") or [],
            "risks": sections.get("risk_invalidation") or [],
            "changes": [{"text": row.get("text") or row.get("evidence_text") or "", "claim_id": row.get("local_id") or ""} for row in changes[:8]],
            "coverage": {key: bool(coverage.get(key)) for key in required},
            "required_evidence": list(required),
            "open_questions": [key for key in required if not coverage.get(key)],
            "gap_diagnostics": list(execution.get("gap_diagnostics") or []),
            "sources": source_rows,
            "execution": execution,
        }
    return {
        "name": name, "object_kind": "DISCRETE_EVENT", "state": infer_state(claims),
        "state_history": list((previous or {}).get("state_history") or []) + ([infer_state(claims)] if claims else []),
        "one_line_view": (
            (sections["what_changed"][0]["text"] if sections["what_changed"] else "")
            or (sections["event_definition"][0]["text"] if sections["event_definition"] else "")
            or "事件尚未获得足够原文确认。"
        ),
        "event_definition": sections["event_definition"], "baseline": sections["baseline"],
        "status_stage": sections["status_stage"], "what_changed": sections["what_changed"],
        "causal_chain": sections["causal_chain"], "economic_variables": sections["economic_variables"],
        "affected_nodes": sections["affected_nodes"], "expectation_delta": sections["expectation_delta"],
        "scenarios": sections["scenarios"], "milestones": sections["milestones"],
        "earnings_link": sections["earnings_link"], "risks": sections["risk_invalidation"],
        "changes": [{"text": row.get("text") or row.get("evidence_text") or "", "claim_id": row.get("local_id") or ""} for row in changes[:8]],
        "coverage": {key: bool(coverage.get(key)) for key in required},
        "required_evidence": list(required),
        "open_questions": [key for key in required if not coverage.get(key)],
        "sources": source_rows,
        "execution": execution,
    }


def diagnose_gaps(name: str, missing: list[str], events: list[dict]) -> list[dict]:
    """Explain whether a gap failed at search, read, extraction or coverage.

    This uses the public action trace only. It does not expose or reconstruct
    model reasoning.
    """
    rows = list(events or [])
    result = []
    for category in missing or []:
        attempts = []
        for index, event in enumerate(rows):
            if event.get("event_type") != "planner_decision":
                continue
            payload = event.get("payload") or {}
            if payload.get("action") != "SEARCH" or _action_category(name, payload) != category:
                continue
            run_id = event.get("run_id") or ""
            wave = payload.get("wave")
            segment = []
            for later in rows[index + 1:]:
                if later.get("event_type") == "planner_decision":
                    break
                if later.get("run_id") == run_id:
                    segment.append(later)
            searches = [
                item for item in segment
                if item.get("event_type") == "search"
                and (wave is None or (item.get("payload") or {}).get("wave") == wave)
            ]
            reads = [item for item in segment if item.get("event_type") == "read"]
            attempts.append({
                "query": payload.get("query") or "",
                "search_results": sum(int((item.get("payload") or {}).get("count") or 0) for item in searches),
                "opened": sum(1 for item in reads if item.get("status") == "ok"),
                "read_failed": sum(1 for item in reads if item.get("status") == "failed"),
                "errors": sorted({
                    (item.get("payload") or {}).get("error_code") or "SOURCE_UNREADABLE"
                    for item in reads if item.get("status") == "failed"
                }),
            })
        result.append(_diagnosis_row(category, attempts))
    return result


def _diagnosis_row(category: str, attempts: list[dict]) -> dict:
    searches = sum(row.get("search_results") or 0 for row in attempts)
    opened = sum(row.get("opened") or 0 for row in attempts)
    failed = sum(row.get("read_failed") or 0 for row in attempts)
    errors = sorted({item for row in attempts for item in (row.get("errors") or [])})
    if not attempts:
        code = "NOT_SEARCHED"
        reason = "这一项尚未进入独立检索。"
        next_step = "生成针对该缺口的一手来源查询。"
    elif searches == 0:
        code = "SEARCH_NO_RESULTS"
        reason = "已经检索，但对应查询没有返回候选结果。"
        next_step = "改用英文主题名、官方站点限定和已知框架名称继续搜。"
    elif opened == 0 and failed:
        code = "SOURCE_UNREADABLE"
        reason = "搜索返回了 {0} 条候选，但正文读取失败 {1} 次（{2}）。".format(
            searches, failed, "、".join(errors) or "动态页/反爬/登录墙",
        )
        next_step = "换官方镜像、监管数据库、可下载 PDF 或其他权威来源。"
    elif opened:
        code = "OPENED_NO_ACCEPTED_EVIDENCE"
        reason = "已经打开 {0} 份正文，但没有抽出满足这一字段定义的可引用证据。".format(opened)
        next_step = "复查正文与抽取分类；必要时寻找直接表述该变量的新来源。"
    else:
        code = "RESULTS_NOT_OPENED"
        reason = "搜索有结果，但没有形成新的可用正文，通常是重复、主体不匹配或相关性不足。"
        next_step = "扩大来源族并避免重复 URL。"
    return {
        "key": category,
        "label": EVIDENCE_LABELS.get(category) or category,
        "code": code,
        "reason": reason,
        "next_step": next_step,
        "attempt_count": len(attempts),
        "queries": [row.get("query") or "" for row in attempts[-3:]],
    }


def _action_category(name: str, payload: dict) -> str:
    explicit = payload.get("target_evidence") or ""
    if explicit in THEME_REQUIRED_EVIDENCE:
        return explicit
    query = re.sub(r"\s+", " ", payload.get("query") or "").strip().lower()
    reason = (payload.get("reason") or "").lower()
    markers = {
        "ORIGIN_BASELINE": ("responsible scaling policy 2023", "起源", "历史基线", "baseline"),
        "CURRENT_CATALYSTS": ("latest safeguards", "近期升温", "当前催化", "直接催化"),
        "MARKET_NARRATIVE": ("市场叙事", "market narrative", "交易的叙事"),
    }
    for category, tokens in markers.items():
        if any(token in query or token in reason for token in tokens):
            return category
    for category in THEME_REQUIRED_EVIDENCE:
        recipes = topic_playbooks.gap_queries(name, category)
        if any(re.sub(r"\s+", " ", item).strip().lower() in query for item in recipes):
            return category
    return ""


def completion(dossier: dict) -> dict:
    coverage = dossier.get("coverage") or {}
    required = dossier.get("required_evidence") or REQUIRED_EVIDENCE
    checks = [{"key": key, "passed": bool(coverage.get(key))} for key in required]
    passed = sum(1 for row in checks if row["passed"])
    return {
        "mode": "THEME_TRACKING" if dossier.get("object_kind") == "EVOLVING_THEME" else "EVENT_TRACKING",
        "status": "COMPLETE" if passed == len(checks) else "PARTIAL",
        "passed": passed == len(checks), "passed_count": passed, "checked_count": len(checks),
        "missing_required": [row["key"] for row in checks if not row["passed"]],
        "checks": checks,
        "completion_reason": (
            "主题定义、时间线、当前催化、主体行动、产业影响和反证均需有证据。"
            if dossier.get("object_kind") == "EVOLVING_THEME"
            else "事件状态、传导、预期差和兑现链均需有证据。"
        ),
    }
