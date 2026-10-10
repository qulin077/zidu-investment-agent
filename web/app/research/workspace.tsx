"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { isStructuredResearchReport, ResearchReport } from "@/components/agent/ResearchReport";
import {
  API_BASE,
  api,
  type ResearchCompanyRow,
  type ResearchEvent,
  type ResearchPlaybook,
  type ResearchSessionView,
  type ResearchSubjectType,
  type ResearchSource,
} from "@/lib/api";

const SUBJECT_COPY: Record<ResearchSubjectType, {
  tab: string;
  title: string;
  search: string;
  empty: string;
  dossier: string;
  continue: string;
}> = {
  company: {
    tab: "公司档案", title: "公司档案", search: "搜索公司或代码",
    empty: "还没有公司档案。去 Agent 说“全面研究一家公司”，完成后会自动沉淀到这里。",
    dossier: "当前公司档案", continue: "继续研究这家公司",
  },
  industry: {
    tab: "行业跟踪", title: "行业与产业链", search: "搜索行业或产业链",
    empty: "还没有行业跟踪档案。去 Agent 研究半导体、PCB、光模块等产业链后，会在这里长期更新。",
    dossier: "当前行业跟踪档案", continue: "继续更新这个行业",
  },
  event: {
    tab: "事件主题", title: "事件与主题", search: "搜索事件或主题",
    empty: "还没有事件档案。Rubin、AI 安全、地缘冲突等会作为有状态的研究对象，而不是新闻列表。",
    dossier: "当前事件跟踪档案", continue: "继续跟踪这个事件",
  },
};

const STATUS_LABELS: Record<string, string> = {
  DRAFT: "持续跟踪",
  FORMAL: "已确认",
  RUNNING: "更新中",
  UNAVAILABLE: "待补资料",
  INTERRUPTED: "更新中断",
  STALE: "上次更新未完成",
  OPEN: "待研究",
};

const OPEN_QUESTION_LABELS: Record<string, string> = {
  BUSINESS_MODEL: "公司基本盘与商业模式",
  MOAT: "核心壁垒",
  GROWTH_PROFIT: "增长变量与利润驱动",
  EXPECTATIONS: "管理层、卖方与市场预期",
  PRICE_EXPECTATION_GAP: "股价与预期差",
  CATALYST: "可核对催化剂",
  CHANGES: "事实、预期与判断变化",
  MONITORING: "下一步监控指标",
  DEFINITION_SCOPE: "定义与边界",
  ORIGIN_BASELINE: "起源与历史基线",
  TIMELINE: "演化时间线",
  CURRENT_CATALYSTS: "近期直接催化",
  ACTOR_ACTIONS: "关键主体与行动",
  TECHNICAL_POLICY_TRACKS: "技术与政策分支",
  CAUSAL_CHAIN: "逻辑与影响传导链",
  ECONOMIC_VARIABLES: "经济变量",
  AFFECTED_NODES: "产业与板块影响",
  MARKET_NARRATIVE: "市场叙事与事实差",
  EXPECTATION_DELTA: "预期变化",
  MILESTONES: "下一验证点",
  RISK_INVALIDATION: "风险与失效条件",
};

function traceLabel(event: ResearchEvent): string {
  const payload = event.payload || {};
  if (event.event_type === "entity_resolved") {
    const name = String(payload.name || "");
    const ticker = String(payload.ticker || "");
    return name ? `确认公司：${name}${ticker ? ` · ${ticker}` : ""}` : "确认研究对象";
  }
  if (event.event_type === "skill_selected") return `选择研究框架：${String(payload.skill || "")}`;
  if (event.event_type === "human_checkpoint") {
    if (String(payload.decision || "") === "CLARIFY") {
      return `等待确认研究重点：${String(payload.default_if_skipped || "可使用默认完整研究")}`;
    }
    return `研究边界已确认：${String(payload.focus || "按完整框架执行")}`;
  }
  if (event.event_type === "plan_created") {
    return `拆解研究问题：${String(payload.task_count || 0)} 个任务${payload.planner_model ? ` · ${String(payload.planner_model)}` : ""}`;
  }
  if (event.event_type === "dossier_upgrade") {
    if (event.status === "running") return `升级公司档案：复用 ${String(payload.reused_source_count || 0)} 份来源与 ${String(payload.reused_claim_count || 0)} 条证据`;
    return `公司档案升级完成：${String(payload.planner_model || "强模型")} 规划 · ${String(payload.analyst_model || "强模型")} 综合`;
  }
  if (event.event_type === "wave") return `执行：${String(payload.title || payload.detail || "研究任务")}`;
  if (event.event_type === "search") {
    const queries = Array.isArray(payload.queries) ? payload.queries.length : payload.count;
    return event.status === "failed" ? "联网检索失败" : `联网检索：${String(queries || 0)} 组查询`;
  }
  if (event.event_type === "ifind_industry") {
    if (event.status === "running") return "iFinD：检索行业变化与市场预期";
    if (event.status === "ok") return `iFinD：取得 ${String(payload.source_count || 0)} 条可引用资讯片段`;
    return `iFinD 暂不可用：${String(payload.message || payload.error_code || "继续使用公开来源")}`;
  }
  if (event.event_type === "read") {
    if (event.status === "failed") {
      const code = String(payload.error_code || "SOURCE_UNREADABLE");
      const reasons: Record<string, string> = {
        SOURCE_UNREADABLE: "动态页面、反爬、登录墙或正文提取失败",
        SOURCE_TOO_LARGE: "响应过大",
        PDF_PARSE_FAILED: "PDF 解析失败",
        SSRF_BLOCKED: "地址安全检查未通过",
        SOURCE_ENTITY_MISMATCH: "正文主体不匹配",
        FUTURE_SOURCE: "来源晚于研究截止日",
      };
      return `来源未能读取：${reasons[code] || String(payload.message || code)}`;
    }
    return `读取来源：${String(payload.title || payload.url || "网页")}`;
  }
  if (event.event_type === "claims") return `提取证据：${String(payload.count || 0)} 条`;
  if (event.event_type === "gap") return `发现证据缺口：${String(payload.text || "待补充")}`;
  if (event.event_type === "disconfirmation") return "主动搜索反方证据";
  if (event.event_type === "synthesis") return "合并证据并更新判断";
  if (event.event_type === "done") return "本轮研究完成";
  if (event.event_type === "interrupted") return "本轮研究中断";
  return event.event_type;
}

function shortDate(value: string): string {
  if (!value) return "时间未知";
  return value.slice(0, 10);
}

function statusLabel(status: string): string {
  return STATUS_LABELS[status] || status || "待研究";
}

function sourceCategory(source: ResearchSource): string {
  const text = `${source.source_label || ""} ${source.source_type || ""} ${source.content_type || ""} ${source.title || ""}`.toLowerCase();
  if (/annual|quarter|财报|年报|季报|公告/.test(text)) return "财报与公告";
  if (/transcript|电话会|业绩会|调研|互动|管理层/.test(text)) return "管理层交流";
  if (/broker|research|研报|卖方/.test(text)) return "卖方研究";
  if (/反方|反证|证伪|风险/.test(text)) return "反证与风险";
  if (/price|quote|行情|ifind|财务交叉/.test(text)) return "行情与数据";
  if (/市场观点|叙事|新闻/.test(text)) return "市场叙事";
  return source.source_label || "补充资料";
}

export function ResearchWorkspace() {
  const params = useSearchParams();
  const [subjectType, setSubjectType] = useState<ResearchSubjectType>("company");
  const [groups, setGroups] = useState<ResearchCompanyRow[]>([]);
  const [playbooks, setPlaybooks] = useState<ResearchPlaybook[]>([]);
  const [selectedKey, setSelectedKey] = useState("");
  const [view, setView] = useState<ResearchSessionView | null>(null);
  const [query, setQuery] = useState("");
  const [draft, setDraft] = useState("");
  const [network, setNetwork] = useState<"live" | "replay">("live");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const started = useRef(false);
  const activeSubjectType = useRef<ResearchSubjectType>("company");
  const listRequest = useRef(0);
  const viewRequest = useRef(0);
  const deepLinkPending = useRef(Boolean(params.get("session")));
  const deepLinkHandled = useRef(false);
  const selectedGroup = groups.find((group) => group.key === selectedKey) || null;
  const sessionId = view?.session.id || "";

  const filteredGroups = useMemo(() => {
    const keyword = query.trim().toLowerCase();
    if (!keyword) return groups;
    return groups.filter((group) => `${group.name} ${group.code}`.toLowerCase().includes(keyword));
  }, [groups, query]);

  const refreshList = useCallback(async () => {
    const requestedType = subjectType;
    const requestId = ++listRequest.current;
    const data = await api.researchLibrary(requestedType);
    if (requestId !== listRequest.current || activeSubjectType.current !== requestedType) {
      return data.rows || [];
    }
    setGroups(data.rows || []);
    setLoading(false);
    return data.rows || [];
  }, [subjectType]);

  const load = useCallback(async (id: string) => {
    const requestId = ++viewRequest.current;
    setLoading(true);
    const data = await api.researchSession(id);
    if (requestId !== viewRequest.current) return data;
    setView(data);
    setLoading(false);
    return data;
  }, []);

  const watch = useCallback(async (id: string) => {
    setBusy(true);
    refreshList().catch(() => undefined);
    let source: EventSource | null = null;
    try {
      source = new EventSource(`${API_BASE}/api/research/sessions/${encodeURIComponent(id)}/events`);
      source.onmessage = (message) => {
        const data = JSON.parse(message.data) as ResearchEvent & Record<string, unknown>;
        setView((current) => {
          if (!current || current.session.id !== id) return current;
          const events = current.events || [];
          if (events.some((row) => row.seq === data.seq)) return current;
          return {
            ...current,
            events: [...events, {
              seq: data.seq,
              event_type: data.event_type,
              status: data.status,
              run_id: data.run_id,
              payload: data,
            }],
          };
        });
      };
    } catch {
      source = null;
    }
    const startedAt = Date.now();
    while (Date.now() - startedAt < 300000) {
      const data = await load(id);
      if (data.session.status !== "RUNNING") break;
      await new Promise((resolve) => setTimeout(resolve, 1200));
    }
    source?.close();
    await refreshList();
    setBusy(false);
  }, [load, refreshList]);

  const send = useCallback(async (
    message: string,
    existing?: string,
    networkOverride?: "live" | "replay",
  ) => {
    const text = message.trim();
    if (!text || busy) return;
    setError("");
    setBusy(true);
    try {
      const body = {
        message: text,
        depth: "standard",
        mode: "remote_shadow" as const,
        search_provider: "ddgs",
        network: networkOverride || network,
      };
      const opened = existing
        ? await api.researchSessionMessage(existing, body)
        : await api.researchSessionCreate(body);
      setDraft("");
      await watch(opened.session_id);
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }, [busy, network, watch]);

  useEffect(() => {
    refreshList().catch((err) => {
      setError((err as Error).message);
      setLoading(false);
    });
  }, [refreshList]);

  useEffect(() => {
    api.researchPlaybooks()
      .then((data) => setPlaybooks(data.rows || []))
      .catch(() => setPlaybooks([]));
  }, []);

  function selectSubject(next: ResearchSubjectType) {
    if (next === subjectType) return;
    activeSubjectType.current = next;
    listRequest.current += 1;
    viewRequest.current += 1;
    setSubjectType(next);
    setGroups([]);
    setSelectedKey("");
    setView(null);
    setQuery("");
    setLoading(true);
    setError("");
  }

  useEffect(() => {
    const existing = params.get("session");
    if (existing) {
      if (deepLinkHandled.current) return;
      deepLinkHandled.current = true;
      load(existing)
        .then(async (data) => {
          const sessionType: ResearchSubjectType = data.session.skill === "industry-research"
            ? "industry"
            : data.session.skill === "event-impact" ? "event" : "company";
          activeSubjectType.current = sessionType;
          const requestId = ++listRequest.current;
          setGroups([]);
          setSubjectType(sessionType);
          setSelectedKey(data.session.primary_entity_code || data.session.primary_entity_name || data.session.title);
          const library = await api.researchLibrary(sessionType);
          if (requestId === listRequest.current && activeSubjectType.current === sessionType) {
            setGroups(library.rows || []);
            setLoading(false);
          }
          deepLinkPending.current = false;
        })
        .catch((err) => {
          deepLinkPending.current = false;
          setError((err as Error).message);
        });
      return;
    }
    const q = (params.get("q") || "").trim();
    if (!q || started.current) return;
    const key = `research-auto:${q}`;
    if (typeof window !== "undefined" && sessionStorage.getItem(key)) return;
    started.current = true;
    sessionStorage.setItem(key, "1");
    send(q).catch((err) => setError((err as Error).message));
  }, [params, load, send]);

  useEffect(() => {
    if (deepLinkPending.current || !groups.length) return;
    const current = groups.find((group) => group.key === selectedKey);
    if (current) return;
    setSelectedKey(groups[0].key);
    load(groups[0].primary_session_id).catch((err) => setError((err as Error).message));
  }, [groups, selectedKey, load]);

  function selectGroup(group: ResearchCompanyRow) {
    setSelectedKey(group.key);
    setError("");
    load(group.primary_session_id).catch((err) => setError((err as Error).message));
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    send(draft, sessionId || undefined);
  }

  function upgradeCompanyDossier() {
    if (!sessionId || subjectType !== "company" || busy) return;
    send(
      "使用新研究架构升级这份公司档案：重新规划并分析已有证据，保留旧版本，列出判断的保留、增强、削弱、反转或新增，以及仍需补充的证据缺口。",
      sessionId,
      "replay",
    );
  }

  const sources = view?.sources || [];
  const claims = view?.claims || [];
  const openQuestions = view?.open_questions || [];
  const events = view?.events || [];
  const upgradeHistory = view?.upgrade_history || [];
  const latestUpgrade = upgradeHistory.length ? upgradeHistory[upgradeHistory.length - 1] : null;
  const thesis = view?.current_thesis?.text || "";
  const sourceMix = useMemo(() => {
    const counts = new Map<string, number>();
    sources.forEach((source) => {
      const category = sourceCategory(source);
      counts.set(category, (counts.get(category) || 0) + 1);
    });
    return [...counts.entries()].sort((a, b) => b[1] - a[1]);
  }, [sources]);
  const incompleteCount = groups.filter((group) => ["UNAVAILABLE", "INTERRUPTED", "STALE"].includes(group.status)).length;
  const copy = SUBJECT_COPY[subjectType];

  return (
    <section className="research-page research-library-page">
      <header className="research-library-head">
        <div>
          <span className="research-eyebrow">LONG-TERM RESEARCH MEMORY</span>
          <h1>研究中心</h1>
          <p>
            公司档案、行业结构和事件影响分别沉淀，再通过产业链相互关联；
            Research 负责让判断可复用、可更新、可追溯，而不是堆一条新闻流。
          </p>
        </div>
        <Link className="research-primary-action" href="/agent">去 Agent 发起新研究</Link>
      </header>

      <nav className="research-subject-tabs" aria-label="研究对象类型">
        {(Object.keys(SUBJECT_COPY) as ResearchSubjectType[]).map((item) => (
          <button
            type="button"
            key={item}
            className={subjectType === item ? "active" : ""}
            aria-pressed={subjectType === item}
            onClick={() => selectSubject(item)}
          >
            {SUBJECT_COPY[item].tab}
          </button>
        ))}
      </nav>

      {subjectType === "industry" && playbooks.length ? (
        <section className="research-playbook-catalog" aria-label="行业研究 Playbook">
          <header>
            <div>
              <span className="research-eyebrow">INDUSTRY PLAYBOOKS</span>
              <h2>同一套研究骨架，按行业切换验证重点</h2>
            </div>
            <p>不是五条固定路线。Planner 先识别产业域与细分环节，再用对应指标补齐证据缺口。</p>
          </header>
          <div className="research-playbook-grid">
            {playbooks.map((playbook) => (
              <article key={playbook.id} className="research-playbook-card">
                <div>
                  <span>{playbook.domain}</span>
                  <h3>{playbook.label}</h3>
                </div>
                <div className="research-playbook-segments">
                  {playbook.segments.map((segment) => <span key={segment.id}>{segment.label}</span>)}
                </div>
                <details>
                  <summary>查看监控与验证框架</summary>
                  <strong>核心监控</strong>
                  <ul>{playbook.monitoring_metrics.map((metric) => <li key={metric}>{metric}</li>)}</ul>
                  <strong>财务验证</strong>
                  <ul>{playbook.financial_validation.map((item) => <li key={item}>{item}</li>)}</ul>
                  <strong>优先来源</strong>
                  <p>{playbook.source_priorities.join(" · ")}</p>
                </details>
              </article>
            ))}
          </div>
          <p className="research-playbook-note">
            细分主题按“产业域 → 环节 → 研究对象”归类：半导体材料进入半导体制造 / 材料环节，光模块测试进入光模块 / 测试设备与服务环节。
          </p>
        </section>
      ) : null}

      <div className="research-flow" aria-label="研究工作流">
        <div><span>01</span><strong>Agent 对话</strong><small>理解你真正关心什么</small></div>
        <div><span>02</span><strong>全面研究</strong><small>财报、交流、卖方与反证并行</small></div>
        <div><span>03</span><strong>研究对象</strong><small>沉淀公司、行业或事件档案</small></div>
        <div><span>04</span><strong>持续更新</strong><small>记录事实、预期与逻辑变化</small></div>
      </div>

      <div className="research-overview" aria-label="研究库概览">
        <div><span>已覆盖{copy.tab}</span><strong>{groups.length}</strong><small>同一对象合并展示</small></div>
        <div><span>本档案来源</span><strong>{sources.length}</strong><small>已打开并保留的资料</small></div>
        <div><span>可核查证据</span><strong>{claims.length}</strong><small>结论与来源可以互相定位</small></div>
        <div className={incompleteCount ? "needs-attention" : ""}><span>待补档案</span><strong>{incompleteCount}</strong><small>来源不足或上次更新中断</small></div>
      </div>

      <div className="research-library-layout">
        <aside className="research-company-index">
          <div className="research-index-head">
            <div>
              <span className="research-eyebrow">COVERAGE</span>
              <h2>{copy.title}</h2>
            </div>
            <span>{filteredGroups.length}</span>
          </div>
          <input
            className="research-company-search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={copy.search}
            aria-label={`搜索${copy.tab}`}
          />
          <div className="research-company-list">
            {filteredGroups.map((group) => (
              <button
                key={group.key}
                type="button"
                className={group.key === selectedKey ? "active" : ""}
                onClick={() => selectGroup(group)}
              >
                <span className="research-company-main">
                  <strong>{group.name}</strong>
                  <small>{group.code || (subjectType === "company" ? "代码待确认" : copy.tab)}</small>
                </span>
                <span className={`research-status status-${group.status.toLowerCase()}`}>
                  {statusLabel(group.status)}
                </span>
                <span className="research-company-meta">
                  更新于 {shortDate(group.updated_at)} · {group.research_count} 次研究
                </span>
              </button>
            ))}
            {!filteredGroups.length && !loading ? <p className="section-note">没有匹配的{copy.tab}。</p> : null}
          </div>
        </aside>

        <main className="research-dossier">
          {selectedGroup && view ? (
            <>
              <header className="research-dossier-head">
                <div>
                  <div className="research-dossier-title">
                    <h2>{view.session.primary_entity_name || selectedGroup.name}</h2>
                    {view.session.primary_entity_code ? <code>{view.session.primary_entity_code}</code> : null}
                    <span className={`research-status status-${selectedGroup.status.toLowerCase()}`}>
                      {statusLabel(selectedGroup.status)}
                    </span>
                  </div>
                  <p>最近更新 {shortDate(selectedGroup.updated_at)} · 档案会保留历史，不用每次从零开始。</p>
                </div>
                <div className="research-dossier-actions">
                  {subjectType === "company" ? (
                    <button
                      type="button"
                      className="research-upgrade-action"
                      onClick={upgradeCompanyDossier}
                      disabled={busy}
                      title="复用已有来源与证据，用 V4 Pro 重新规划和综合；本次不重复联网抓取"
                    >
                      {busy ? "正在处理…" : "用新架构升级"}
                    </button>
                  ) : null}
                  <a className="research-secondary-action" href="#continue-research">继续研究</a>
                </div>
              </header>

              {view.notice ? <div className="research-library-notice">{view.notice}</div> : null}
              {error ? <div className="research-library-error">{error}</div> : null}

              <section className="research-coverage-strip" aria-label="当前档案覆盖">
                <div><strong>{sources.length}</strong><span>来源</span></div>
                <div><strong>{claims.length}</strong><span>证据</span></div>
                <div><strong>{openQuestions.length}</strong><span>待回答</span></div>
                <div><strong>{view.runs?.length || selectedGroup.research_count}</strong><span>研究轮次</span></div>
              </section>

              {subjectType === "company" && latestUpgrade ? (
                <section className="research-upgrade-summary" aria-label="公司档案架构升级记录">
                  <div className="research-upgrade-heading">
                    <div>
                      <span className="research-eyebrow">DOSSIER UPGRADE</span>
                      <h3>已用新研究架构重新分析</h3>
                    </div>
                    <span>{latestUpgrade.planner_model} → {latestUpgrade.analyst_model}</span>
                  </div>
                  <div className="research-upgrade-metrics">
                    <span>复用 {latestUpgrade.reused_source_count} 份来源</span>
                    <span>复用 {latestUpgrade.reused_claim_count} 条证据</span>
                    <span>{latestUpgrade.mode === "REUSE_EXISTING_EVIDENCE" ? "未重复联网" : `新增 ${latestUpgrade.new_source_count} 份来源`}</span>
                    <span>{latestUpgrade.history_preserved ? "旧版本已保留" : "首次升级基线"}</span>
                  </div>
                  {latestUpgrade.judgment_changes.length ? (
                    <ul>
                      {latestUpgrade.judgment_changes.map((item, index) => <li key={`${index}-${item}`}>{item}</li>)}
                    </ul>
                  ) : <p>本轮未识别出足以改变判断的新增证据；旧档案已按新框架重新组织。</p>}
                  {upgradeHistory.length > 1 ? (
                    <details>
                      <summary>查看全部 {upgradeHistory.length} 次架构升级记录</summary>
                      <ol>
                        {[...upgradeHistory].reverse().map((item) => (
                          <li key={item.run_id}>
                            <strong>{item.upgraded_at?.slice(0, 16).replace("T", " ") || item.run_id}</strong>
                            <span>{item.planner_model} / {item.analyst_model} · {item.reused_claim_count} 条旧证据</span>
                          </li>
                        ))}
                      </ol>
                    </details>
                  ) : null}
                </section>
              ) : null}

              <section className="research-dossier-section">
                <div className="research-section-title">
                  <div>
                    <span className="research-eyebrow">CURRENT DOSSIER</span>
                    <h3>{copy.dossier}</h3>
                  </div>
                  <span>{view.current_thesis?.formal ? "已正式固化" : "研究草稿 · 持续更新"}</span>
                </div>
                {thesis ? (
                  isStructuredResearchReport(thesis) ? (
                    <ResearchReport
                      content={thesis}
                      subjectName={view.session.primary_entity_name || selectedGroup.name}
                      kind={subjectType}
                    />
                  ) : (
                    <div className="research-plain-thesis">{thesis}</div>
                  )
                ) : (
                  <div className="research-empty-state">
                    <strong>这个研究对象还没有形成可用档案</strong>
                    <p>可以在下方继续研究，Agent 会先补齐来源，再更新判断。</p>
                  </div>
                )}
              </section>

              <section className="research-audit-grid">
                <div>
                  <span className="research-eyebrow">SOURCE COVERAGE</span>
                  <h3>资料覆盖</h3>
                  {sourceMix.length ? (
                    <ul className="research-source-mix">
                      {sourceMix.map(([category, count]) => (
                        <li key={category}><span>{category}</span><strong>{count}</strong></li>
                      ))}
                    </ul>
                  ) : <p className="section-note">还没有读取到可用来源。</p>}
                </div>
                <div>
                  <span className="research-eyebrow">OPEN QUESTIONS</span>
                  <h3>下一步要补什么</h3>
                  {openQuestions.length ? (
                    <ul>{openQuestions.map((item) => <li key={item}>{OPEN_QUESTION_LABELS[item] || item}</li>)}</ul>
                  ) : <p className="section-note">当前没有显式未决问题；仍应定期检查新财报和预期变化。</p>}
                </div>
              </section>

              <details className="research-audit-details">
                <summary>查看来源、证据和执行轨迹</summary>
                <div className="research-audit-columns">
                  <section>
                    <h3>来源</h3>
                    {sources.length ? <ul>{sources.map((source) => (
                      <li key={source.local_id}>
                        {source.url ? <a href={source.url} target="_blank" rel="noreferrer">{source.title || source.url}</a> : source.title}
                        <small>{source.publisher || "来源待确认"} · {source.published_at || "日期待确认"}</small>
                      </li>
                    ))}</ul> : <p className="section-note">暂无来源。</p>}
                  </section>
                  <section>
                    <h3>证据</h3>
                    {claims.length ? <ul>{claims.map((claim) => (
                      <li key={claim.local_id}><code>{claim.local_id}</code> {claim.text}</li>
                    ))}</ul> : <p className="section-note">暂无证据。</p>}
                  </section>
                  <section>
                    <h3>执行轨迹</h3>
                    {events.length ? <ol>{events.map((event) => (
                      <li key={event.seq} className={event.status === "gap" || event.status === "failed" ? "is-gap" : ""}>
                        {traceLabel(event)}
                      </li>
                    ))}</ol> : <p className="section-note">暂无执行轨迹。</p>}
                  </section>
                </div>
              </details>

              <section className="research-continue" id="continue-research">
                <div>
                  <span className="research-eyebrow">CONTINUE THIS DOSSIER</span>
                  <h3>{copy.continue}：{view.session.primary_entity_name || selectedGroup.name}</h3>
                  <p>{subjectType === "company" ? "例如：补最近三年财报、只看管理层交流、检查市场预期，或寻找反方证据。" : subjectType === "industry" ? "例如：更新景气指标、代表公司业绩、产业链价值量、技术路线或活跃事件。" : "例如：核对里程碑、订单落地、价值量变化、影响链和证伪条件。"}</p>
                </div>
                <form onSubmit={onSubmit}>
                  <textarea
                    value={draft}
                    onChange={(event) => setDraft(event.target.value)}
                    placeholder="这次想补哪一块？"
                    aria-label="继续研究的问题"
                    disabled={busy}
                  />
                  <div>
                    <label>
                      <input
                        type="checkbox"
                        checked={network === "live"}
                        onChange={(event) => setNetwork(event.target.checked ? "live" : "replay")}
                      />
                      联网检查新信息
                    </label>
                    <button type="submit" disabled={busy || !draft.trim()}>{busy ? "研究中…" : "开始更新"}</button>
                  </div>
                </form>
              </section>
            </>
          ) : loading ? (
            <div className="research-empty-state"><strong>正在读取研究档案…</strong></div>
          ) : (
            <div className="research-empty-state">
              <strong>{copy.tab}还是空的</strong>
              <p>{copy.empty}</p>
              <Link href="/agent">打开 Agent</Link>
            </div>
          )}
        </main>
      </div>
    </section>
  );
}
