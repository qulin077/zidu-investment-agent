export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? process.env.API_BASE ?? "http://127.0.0.1:8787";
const BASE = API_BASE;

export type DatasetStatus = {
  name: string;
  description: string;
  rows: number;
  asof: string;
  age: number | null;
  ok: boolean;
  issues: string[];
  coverage: number | null;
};

export type Mover = {
  code: string;
  name: string;
  sector: string;
  close: number | null;
  pct_chg: number | null;
};

export type Sector = {
  sector: string;
  count: number;
  avg_pct: number | null;
  max_pct: number | null;
  min_pct: number | null;
};

export type Position = {
  code: string;
  name: string;
  qty: number | null;
  cost: number | null;
  current_price: number | null;
  current_value: number | null;
  current_pnl_pct: number | null;
  quote_date: string | null;
};

export type NewsItem = {
  id: string;
  source: string;
  published_at: string;
  title: string;
  url: string;
  summary: string;
  tags: string;
};

export type ResearchUpdateCandidate = {
  id: string;
  news_id: string;
  news_url: string;
  news_title: string;
  news_source: string;
  published_at: string;
  candidate_type: string;
  target_type: "company" | "industry" | "event" | "new_event";
  target_session_id: string;
  target_name: string;
  target_code: string;
  match_reason: string;
  matched_terms: string[];
  importance: "HIGH" | "MEDIUM" | "LOW";
  status: string;
};

export type Board = {
  health: { ok: boolean; checked_at: string; datasets: DatasetStatus[] };
  pulse: {
    indices: { code: string; name: string; close: number; pct_chg: number }[];
    vix: {
      name: string;
      value: number | null;
      chg_1d_pct: number | null;
      band: string;
      date: string;
      source: string;
      series: number[];
    };
    emotion: {
      asof: string;
      stage: string;
      why: string;
      action: string;
      limit_up: number | null;
      zhaban: number | null;
      height: number | null;
      zhaban_rate: number | null;
    };
    themes: {
      asof: string;
      themes: {
        theme: string;
        n: number;
        max_board: number;
        names: string;
        role: string;
      }[];
    };
    breadth: { asof: string; up: number; down: number; flat: number; n: number };
    macro: {
      asof: string;
      items: {
        id: string;
        name: string;
        value: number | null;
        chg_1d_pct: number | null;
        unit: string;
        date: string;
      }[];
    };
  };
  movers: { asof: string; gainers: Mover[]; losers: Mover[] };
  sectors: { asof: string; sectors: Sector[] };
  positions: {
    asof: string;
    quote_date: string;
    stale_days: number | null;
    rows: Position[];
  };
  account: {
    asof: string;
    rows: {
      date: string;
      equity: number | null;
      pnl_day_pct: number | null;
      position_pct: number | null;
    }[];
  };
  trades: { total: number; asof: string; fill_rates: Record<string, number> };
  news: {
    asof: string;
    sources: { source: string; count: number }[];
    rows: NewsItem[];
  };
  research_updates: {
    pending_count: number;
    rows: ResearchUpdateCandidate[];
  };
};

export type FrameworkDoc = {
  path: string;
  section: string;
  title: string;
  size: number;
};

class ApiError extends Error {}

async function get<T>(path: string): Promise<T> {
  const response = await fetch(`${BASE}${path}`, { cache: "no-store" });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const detail = typeof body.detail === "string" ? body.detail : "";
    throw new ApiError(detail || `${path} 返回 ${response.status}`);
  }
  return (await response.json()) as T;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    const detail = typeof payload.detail === "string" ? payload.detail : "";
    throw new ApiError(detail || `${path} 返回 ${response.status}`);
  }
  return (await response.json()) as T;
}

async function postEventStream<T>(
  path: string,
  body: unknown,
  onProgress: (event: AgentProgressEvent) => void,
): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  if (!response.ok || !response.body) {
    const payload = await response.json().catch(() => ({}));
    const detail = typeof payload.detail === "string" ? payload.detail : "";
    throw new ApiError(detail || `${path} 返回 ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let result: T | null = null;

  function consume(frame: string) {
    let eventName = "message";
    const data: string[] = [];
    for (const line of frame.split(/\r?\n/)) {
      if (line.startsWith("event:")) eventName = line.slice(6).trim();
      if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
    }
    if (!data.length) return;
    const payload = JSON.parse(data.join("\n")) as AgentProgressEvent | T | { message?: string };
    if (eventName === "progress") onProgress(payload as AgentProgressEvent);
    if (eventName === "result") result = payload as T;
    if (eventName === "error") throw new ApiError((payload as { message?: string }).message || "这轮执行失败了");
  }

  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    const frames = buffer.split(/\r?\n\r?\n/);
    buffer = frames.pop() || "";
    for (const frame of frames) consume(frame);
    if (done) break;
  }
  if (buffer.trim()) consume(buffer);
  if (!result) throw new ApiError("执行完成，但没有收到最终回答");
  return result;
}

export type ResearchProjectRow = {
  id: string;
  title: string;
  industry: string;
  status: string;
  updated_at: string;
};

export type ResearchPlan = {
  ok: boolean;
  error_code?: string;
  error_message?: string;
  skill?: string;
  route?: { skill?: string; intent?: string; confidence?: number; reason_code?: string };
  plan?: {
    research_question: string;
    steps: { step: number; name: string; detail: string }[];
    tasks?: { id: string; question: string; category: string; priority: number }[];
  };
};

export type ResearchRunResult = {
  ok: boolean;
  status?: string;
  error_code?: string;
  error_message?: string;
  project_id?: string;
  thesis_id?: string;
  thesis_version?: number;
};

export type ResearchProjectView = {
  project: {
    id: string;
    title: string;
    industry: string;
    question?: string;
    industry_definition?: string;
    map?: {
      skill?: string;
      company_view?: {
        business_model?: Record<string, string>;
        revenue_driver_tree?: string;
        financial_trend?: Record<string, number | null>;
        industry_context?: string;
        expectations?: Record<string, string>;
        variant?: Record<string, string>;
        valuation_context?: Record<string, number | null>;
        monitoring?: string[];
        commercial_stage?: string;
        exposure_type?: string;
      };
    };
  };
  claims: Record<
    string,
    {
      id: string;
      claim_text: string;
      status: string;
      confidence: string;
      evidence?: { evidence_text: string; evidence_location: string; source_title?: string }[];
    }[]
  >;
  conflicts: { metric: string; value_a: string; value_b: string; possible_reason: string; status: string }[];
  value_chain: { node_name: string; upstream_node: string; role: string; bottleneck: string }[];
  company_mapping: {
    company: string;
    code: string;
    value_chain_node: string;
    exposure_type: string;
    revenue_exposure: string;
    evidence_level: string;
    product_evidence: string;
    customer_evidence: string;
    commercial_stage?: string;
  }[];
  runs?: { id: string; status: string; llm_mode?: string; iterations?: number; llm_calls?: number; error_code?: string }[];
  thesis: {
    id?: string;
    version?: number;
    summary?: string;
    as_of?: string;
    bull_case?: string;
    base_case?: string;
    bear_case?: string;
    invalidation?: string;
    diff_verdict?: string;
    catalysts?: string[];
    risks?: string[];
  };
  thesis_versions: { version: number; as_of: string; diff_verdict: string; created_at: string }[];
  open_questions: { question: string; status: string }[];
  metrics?: Record<string, number | null>;
  waves?: { wave: number; name: string }[];
  disconfirmation?: { query: string; result: string; status: string }[];
  claim_relations?: { relation: string; source_claim_id: string; target_claim_id: string }[];
  expectations?: { source_type: string; statement: string; status: string }[];
};

export type ChainMeta = {
  id: string;
  name: string;
  thesis: string;
  aliases: string[];
  layers: string[];
  n_members: number;
};

export type ChainMember = {
  code: string;
  name: string;
  role: string;
  close: number | null;
  pct_chg: number | null;
  in_book: boolean;
};

export type ChainLayer = {
  id: string;
  name: string;
  side: string;
  logic: string;
  avg_pct: number | null;
  breadth: number | null;
  quoted: number;
  held: number;
  members: ChainMember[];
};

export type ChainBrief = {
  id: string;
  name: string;
  thesis: string;
  asof: string;
  prev_asof: string;
  switched: boolean;
  layers: ChainLayer[];
  overseas: {
    symbol: string;
    name: string;
    date: string;
    close: number;
    pct_chg: number | null;
  }[];
  money: {
    layer: string;
    name: string;
    avg_pct: number | null;
    laggard: string;
    laggard_pct: number | null;
    why: string;
  };
  prev_money: { name: string; avg_pct: number | null };
  book: {
    asof: string;
    stale_days: number | null;
    stale_warning: boolean;
    verdict: string;
    in_chain: Position[];
    in_universe_other_chain: Position[];
    orphans: { code: string; name: string }[];
  };
  news: { title: string; source: string; published_at: string; matched: string[] }[];
  disclaimer: string;
};

export type AgentActivity = {
  id: string;
  type: string;
  status: string;
  summary: string;
  project_id?: string;
  created_at?: string;
};

export type AgentProgressEvent = {
  seq: number;
  phase: "intent" | "tool" | "research" | "data" | "synthesis" | "memory" | "done" | string;
  title: string;
  detail?: string;
  status: "running" | "completed" | "gap" | "failed" | string;
};

export type AgentTurn = {
  ok: boolean;
  session_id: string;
  skill: string;
  domain: string;
  answer: string;
  active_project_id: string;
  research_session_id: string;
  thesis_label: string;
  messages: {
    id: string;
    role: string;
    content: string;
    skill: string;
    domain: string;
    entity_refs?: { name?: string; mention?: string; code?: string }[];
  }[];
  panel: AgentPanel;
  process?: AgentProgressEvent[];
  runtime?: {
    turn_id?: string;
    steps_used?: number;
    stop_reason?: string;
    max_steps?: number;
    model?: string;
    model_calls?: number;
    planning_mode?: string;
  };
};

export type AgentPanel = {
  domain: string;
  active_strategy?: { id?: string; name?: string; time_horizon?: string; style?: string };
  strategies?: { id: string; name: string; time_horizon?: string; style?: string }[];
  active_workflow?: {
    id?: string;
    workflow_type?: string;
    stage?: string;
    pending_question?: string;
    decision_id?: string;
  };
  personal_memory?: {
    id: string;
    memory_type: string;
    memory_key: string;
    confirmation_status: string;
    value?: Record<string, unknown>;
  }[];
  active_goal?: { id?: string; title?: string; goal_type?: string };
  goals?: { id: string; title: string; goal_type: string; status?: string }[];
  active_project?: {
    id?: string;
    title?: string;
    thesis?: string;
    open_question?: string;
    research_session_id?: string;
    strategy?: { id?: string; name?: string; time_horizon?: string; style?: string };
  };
  open_decisions?: { id: string; name?: string; code?: string; status?: string }[];
  pending_reviews?: { id: string; name?: string; status?: string }[];
  active_rules?: { id: string; rule_text: string; status?: string }[];
  activity?: AgentActivity[];
  prompt_version?: string;
  active_entity?: string;
  active_event?: string;
  active_industry?: string;
  last_skill?: string;
  last_intent?: string;
  last_runtime?: {
    last_turn_id?: string;
    last_steps_used?: number;
    last_stop_reason?: string;
    max_steps?: number;
    model?: string;
    model_calls?: number;
    planning_mode?: string;
  };
  open_questions?: string[];
  health?: {
    llm_connected?: boolean;
    llm_configured?: boolean;
    llm_status?: string;
    provider?: string;
    model?: string;
    search?: string;
    ifind?: string;
    runtime?: string;
    max_steps?: number;
    planning_mode?: string;
  };
  today_journal?: {
    id: string;
    entry_type: string;
    raw_text: string;
    summary: string;
    created_at: string;
  }[];
};

export type AgentHome = {
  prompt_version: string;
  session: { id: string; title: string; current_domain: string; active_project_id: string };
  messages: AgentTurn["messages"];
  panel: AgentPanel;
};

export const api = {
  board: () => get<Board>("/api/board"),
  news: (limit = 80, source?: string) =>
    get<Board["news"]>(
      `/api/news?limit=${limit}${source ? `&source=${encodeURIComponent(source)}` : ""}`,
    ),
  frameworks: () => get<{ rows: FrameworkDoc[] }>("/api/frameworks"),
  frameworkContent: (path: string) =>
    get<{ path: string; title: string; content: string }>(
      `/api/frameworks/content?path=${encodeURIComponent(path)}`,
    ),
  chains: () => get<{ rows: ChainMeta[] }>("/api/chains"),
  chain: (id: string) => get<ChainBrief>(`/api/chains/${id}`),
  replay: (date?: string) =>
    get<ReplayDay>(
      `/api/replay${date ? `?date=${encodeURIComponent(date)}` : ""}`,
    ),
  personas: () => get<{ modes: Record<string, PersonaMode> }>("/api/personas"),
  researchSessions: () =>
    get<{ ok: boolean; rows: ResearchSessionRow[] }>("/api/research/sessions"),
  researchPlaybooks: () =>
    get<{ ok: boolean; rows: ResearchPlaybook[] }>("/api/research/playbooks"),
  researchLibrary: (subjectType: ResearchSubjectType = "company") =>
    get<{ ok: boolean; rows: ResearchCompanyRow[] }>(
      `/api/research/library?subject_type=${encodeURIComponent(subjectType)}`,
    ),
  researchSession: (id: string) =>
    get<ResearchSessionView>(`/api/research/sessions/${encodeURIComponent(id)}`),
  researchSessionCreate: (body: ResearchSessionRequest) =>
    post<{ session_id: string; run_id: string; status: string }>("/api/research/sessions", body),
  researchSessionMessage: (id: string, body: ResearchSessionRequest) =>
    post<{ session_id: string; run_id: string; status: string }>(
      `/api/research/sessions/${encodeURIComponent(id)}/messages`,
      body,
    ),
  researchUpdateCandidates: () =>
    get<{ ok: boolean; pending_count: number; rows: ResearchUpdateCandidate[] }>(
      "/api/research/update-candidates",
    ),
  researchUpdateScan: () =>
    post<{ ok: boolean; created: number; pending: number }>(
      "/api/research/update-candidates/scan", {},
    ),
  researchUpdateAccept: (id: string) =>
    post<{ ok: boolean; session_id: string; run_id: string; status: string }>(
      `/api/research/update-candidates/${encodeURIComponent(id)}/accept`, {},
    ),
  researchUpdateDismiss: (id: string) =>
    post<{ ok: boolean; status: string }>(
      `/api/research/update-candidates/${encodeURIComponent(id)}/dismiss`, {},
    ),
  agentHome: () => get<AgentHome>("/api/agent/home"),
  agentMessage: (message: string, network: "live" | "replay" = "replay") =>
    post<AgentTurn>("/api/agent/messages", { message, network, use_llm: true, llm_mode: "auto" }),
  agentMessageStream: (
    message: string,
    network: "live" | "replay" = "replay",
    onProgress: (event: AgentProgressEvent) => void,
  ) => postEventStream<AgentTurn>(
    "/api/agent/messages/stream",
    { message, network, use_llm: true, llm_mode: "auto" },
    onProgress,
  ),
  agentGoal: (body: { title: string; goal_type?: string; project_ids?: string[]; pattern_ids?: string[] }) =>
    post<{ id: string; title: string }>("/api/agent/goals", body),
  agentStrategy: (body: { name: string; time_horizon?: string; style?: string; activate?: boolean }) =>
    post<{ strategy: { id: string; name: string }; active: boolean }>("/api/agent/strategies", body),
  agentStrategyActivate: (strategyId: string) =>
    post<{ strategy: { id: string; name: string }; active: boolean }>(
      `/api/agent/strategies/${encodeURIComponent(strategyId)}/activate`, {},
    ),
  agentActivity: (projectId = "") =>
    get<{ activities: AgentActivity[] }>(
      `/api/agent/activity${projectId ? `?project_id=${encodeURIComponent(projectId)}` : ""}`,
    ),
  researchPlan: (q: string, theme = "", skill = "") =>
    get<ResearchPlan>(
      `/api/research/plan?q=${encodeURIComponent(q)}${theme ? `&theme=${encodeURIComponent(theme)}` : ""}${skill ? `&skill=${encodeURIComponent(skill)}` : ""}`,
    ),
  researchProjects: () => get<{ ok: boolean; rows: ResearchProjectRow[]; error_message?: string }>("/api/research/projects"),
  researchProject: (id: string) => get<ResearchProjectView>(`/api/research/projects/${encodeURIComponent(id)}`),
  researchCreate: (body: {
    research_question: string;
    industry_or_theme?: string;
    as_of?: string;
    mode?: "fixture" | "remote";
    market_scope?: string[];
  }) => post<ResearchRunResult>("/api/research/projects", body),
  dialogueTurn: (body: {
    q?: string;
    persist?: boolean;
    image_base64?: string;
    mime?: string;
  }) => post<DialoguePacket>("/api/dialogue", body),
  session: () => get<SessionState>("/api/session"),
  resetSession: () => post<SessionState>("/api/session/reset", {}),
  reviewToday: (date?: string) =>
    get<ReviewToday>(
      `/api/review/today${date ? `?date=${encodeURIComponent(date)}` : ""}`,
    ),
  reviewArchive: (params?: { status?: string; code?: string; limit?: number }) => {
    const search = new URLSearchParams();
    if (params?.status) search.set("status", params.status);
    if (params?.code) search.set("code", params.code);
    if (params?.limit) search.set("limit", String(params.limit));
    const suffix = search.toString() ? `?${search.toString()}` : "";
    return get<ReviewArchive>(`/api/review/archive${suffix}`);
  },
  reviewDecision: (id: string) =>
    get<ReviewDecision>(`/api/review/decision/${encodeURIComponent(id)}`),
  reviewConfirm: (body: { execution_id: string; decision_id: string; note?: string }) =>
    post<Record<string, unknown>>("/api/review/match/confirm", body),
  reviewUnmatched: (body: { execution_id: string; note?: string }) =>
    post<Record<string, unknown>>("/api/review/match/unmatched", body),
  reviewPostHoc: (body: { execution_id: string; thesis?: string }) =>
    post<Record<string, unknown>>("/api/review/decision/post-hoc", body),
  recorderParse: (body: {
    raw_text: string;
    known_symbol?: string;
    known_company?: string;
    mode?: string;
  }) => post<RecorderParseResult>("/api/review/recorder/parse", body),
  recorderConfirm: (body: {
    draft_id: string;
    confirmed: boolean;
    edits?: Record<string, unknown>;
  }) => post<Record<string, unknown>>("/api/review/recorder/confirm", body),
  recorderReject: (body: { draft_id: string }) =>
    post<Record<string, unknown>>("/api/review/recorder/reject", body),
  reviewFlags: () => get<ReviewFlags>("/api/review/flags"),
  productHealth: () => get<ProductHealth>("/api/product/health"),
  productMetrics: (includeDemo = false) =>
    get<ProductMetrics>(
      `/api/product/metrics${includeDemo ? "?include_demo=true" : ""}`,
    ),
  todayWorkbench: (date?: string) =>
    get<TodayWorkbench>(
      `/api/today${date ? `?date=${encodeURIComponent(date)}` : ""}`,
    ),
  decisionContext: (id: string) =>
    get<DecisionContextPayload>(
      `/api/review/decision/${encodeURIComponent(id)}/context`,
    ),
  decisionContextDebug: (id: string, snapshotType = "ENTRY_CONTEXT") =>
    get<Record<string, unknown>>(
      `/api/review/decision/${encodeURIComponent(id)}/context/debug?snapshot_type=${encodeURIComponent(snapshotType)}`,
    ),
  guidedContext: (id: string) =>
    get<GuidedSession>(`/api/review/${encodeURIComponent(id)}/context`),
  confirmOutcome: (id: string, confirmed = true) =>
    post<GuidedSession>(`/api/review/${encodeURIComponent(id)}/confirm-outcome`, { confirmed }),
  confirmViolations: (id: string, confirmed = true) =>
    post<GuidedSession>(`/api/review/${encodeURIComponent(id)}/confirm-violations`, { confirmed }),
  guidedAnswer: (id: string, body: { answer?: string; option_id?: string }) =>
    post<Record<string, unknown>>(`/api/review/${encodeURIComponent(id)}/answer`, body),
  confirmAttribution: (id: string, body: { primary_error: string; evidence?: unknown[]; counterfactual?: string }) =>
    post<Record<string, unknown>>(`/api/review/${encodeURIComponent(id)}/confirm-attribution`, body),
  completeReview: (id: string, lesson: string) =>
    post<Record<string, unknown>>(`/api/review/${encodeURIComponent(id)}/complete`, { lesson }),
  memoryPatterns: () => get<{ rows: MemoryPattern[] }>("/api/memory/patterns"),
  memoryPattern: (id: string) => get<MemoryPatternDetail>(`/api/memory/patterns/${encodeURIComponent(id)}`),
  confirmPattern: (id: string) =>
    post<MemoryPattern>(`/api/memory/patterns/${encodeURIComponent(id)}/confirm`, {}),
  dismissPattern: (id: string) =>
    post<MemoryPattern>(`/api/memory/patterns/${encodeURIComponent(id)}/dismiss`, {}),
  mergePatterns: (targetId: string, sourceId: string) =>
    post<Record<string, unknown>>(`/api/memory/patterns/${encodeURIComponent(targetId)}/merge`, {
      source_id: sourceId,
    }),
  memoryRules: () => get<{ rows: MemoryRule[] }>("/api/memory/rules"),
  proposeRules: (body: { pattern_id: string; rule_text?: string; trigger_text?: string; expected_behavior?: string }) =>
    post<{ rows: MemoryRule[] }>("/api/memory/rules/propose", body),
  activateRule: (id: string) => post<MemoryRule>(`/api/memory/rules/${encodeURIComponent(id)}/activate`, {}),
  rejectRule: (id: string) => post<MemoryRule>(`/api/memory/rules/${encodeURIComponent(id)}/reject`, {}),
  retireRule: (id: string, reason: string) =>
    post<MemoryRule>(`/api/memory/rules/${encodeURIComponent(id)}/retire`, { reason }),
  memoryReminders: (decisionId: string) =>
    get<{ decision_id: string; rows: MemoryReminder[] }>(
      `/api/memory/reminders?decision_id=${encodeURIComponent(decisionId)}`,
    ),
  reminderFeedback: (id: string, value: "RELEVANT" | "NOT_RELEVANT") =>
    post<MemoryReminder>(`/api/memory/reminders/${encodeURIComponent(id)}/feedback`, { value }),
};

export type ReviewFlags = {
  RECORDER_REMOTE_MODE: string;
  remote_primary_allowed: boolean;
  GUIDED_REVIEW_ENABLED: boolean;
  MEMORY_ENABLED?: boolean;
  DECISION_CONTEXT_ENABLED?: boolean;
  PILOT_MODE?: boolean;
  environment?: string;
  demo?: boolean;
};

export type ProductHealth = {
  ok: boolean;
  review_backlog: number;
  recorder_drafts: number;
  memory_candidates: number;
  flags: ReviewFlags;
  lines: string[];
  items: Record<string, { status: string; detail?: string }>;
};

export type MetricCell = {
  name: string;
  value: number | null;
  numerator: number;
  numerator_def: string;
  denominator: number;
  denominator_def: string;
  exclude: string[];
};

export type ProductMetrics = {
  recorder: Record<string, MetricCell>;
  review: Record<string, MetricCell>;
  memory: Record<string, MetricCell | number>;
  context: Record<string, MetricCell>;
  data_quality?: Record<string, MetricCell | boolean>;
};

export type TodayWorkbench = ReviewToday & {
  health: ProductHealth;
  open_decisions: Record<string, unknown>[];
  reminders: Record<string, unknown>[];
  metrics: ProductMetrics;
  context_now: {
    market_stage?: string;
    indices?: Record<string, { ret_5d?: { value?: number | null } }>;
  };
  flags: ReviewFlags;
};

export type DecisionContextPayload = {
  entry: {
    missing?: boolean;
    warning?: string;
    headline?: Record<string, unknown>;
    coverage?: string;
    as_of?: string;
    captured_at?: string;
    market_regime?: string;
    provider_status?: Record<string, string>;
  };
  diff: {
    changes: { field: string; entry: unknown; review: unknown }[];
    note?: string;
  };
};

export type MemoryPattern = {
  id: string;
  pattern_key: string;
  status: string;
  summary: string;
  occurrence_count: number;
  last_seen_at: string;
  evidence_count?: number;
  active_rule?: boolean;
  active_rule_id?: string;
};

export type MemoryEvidence = {
  decision_id: string;
  plan: Record<string, unknown>;
  actual: Record<string, unknown>;
  outcome: Record<string, unknown>;
  violations: string[];
  attribution: string;
  lesson: string;
  quadrant: string;
};

export type MemoryPatternDetail = {
  pattern: MemoryPattern;
  evidence: MemoryEvidence[];
  rules: MemoryRule[];
  active_rule?: MemoryRule | null;
  summarizer?: Record<string, unknown>;
};

export type MemoryRule = {
  id: string;
  pattern_id: string;
  rule_text: string;
  trigger_text: string;
  expected_behavior: string;
  status: string;
  created_at: string;
  confirmed_at?: string;
  violation_count?: number;
  last_triggered?: string;
  evidence_decision_ids?: string;
};

export type MemoryReminder = {
  id: string;
  decision_id: string;
  rule_id: string;
  rule_text?: string;
  why: string;
  evidence_decision_ids?: string[] | string;
  feedback?: string;
  target_size_unchanged?: boolean;
};

export type GuidedFact = { statement: string; evidence_ref: string };

export type GuidedTurn = {
  question: string;
  options?: { id: string; label: string }[];
  unresolved_dimension?: string;
  attribution_candidates?: { type: string; reason: string; evidence_refs: string[] }[];
  fact_summary?: GuidedFact[];
  quadrant?: string;
  counterfactual?: { statement?: string } | null;
  needs_user_input?: boolean;
  agent_conclusion?: unknown;
};

export type GuidedSession = {
  session_id?: string;
  decision_id: string;
  facts: {
    decision: Record<string, unknown>;
    plan: Record<string, unknown>;
    actual: Record<string, unknown>;
    outcome?: Record<string, unknown> | null;
    violations: { code: string; detail?: string }[];
    quadrant?: string;
    quote_coverage?: string;
    process_followed?: boolean;
    pnl_sign?: string;
    fact_summary?: GuidedFact[];
    counterfactual?: { statement?: string } | null;
  };
  turn: GuidedTurn;
  unresolved?: string;
  context_diff?: {
    changes: { field: string; entry: unknown; review: unknown }[];
    note?: string;
  };
};

export type ReplayTrade = {
  id: string;
  date: string;
  time: string;
  code: string;
  name: string;
  side: string;
  price: number | null;
  qty: number | null;
  earning_type: string;
  reason: string;
  planned: string;
};

export type ReplayDay = {
  asof: string;
  dates: string[];
  trades: ReplayTrade[];
  n_trades: number;
  n_buys: number;
  missing_earning_type: number;
  unplanned: number;
  predictions: {
    pending: Record<string, string>[];
    scored: Record<string, string>[];
    pending_count: number;
    scored_count: number;
  };
  fill_rates: Record<string, number>;
  trade_total: number;
  purpose: { perception: string; execution: string };
};

export type PersonaMode = {
  name: string;
  one_liner: string;
  watches: string[];
  ignores: string[];
  fail_when: string;
  position: string;
  earning_types: string[];
};

export type ResearchSessionRow = {
  id: string;
  title: string;
  skill: string;
  status: string;
  primary_entity_name: string;
  primary_entity_code: string;
  updated_at: string;
  last_run_id: string;
};

export type ResearchCompanyRow = {
  key: string;
  subject_type?: ResearchSubjectType;
  name: string;
  code: string;
  exchange: string;
  status: string;
  primary_session_id: string;
  latest_session_id: string;
  updated_at: string;
  research_count: number;
  source_count: number;
  claim_count: number;
  open_question_count: number;
};

export type ResearchSubjectType = "company" | "industry" | "event";

export type ResearchPlaybook = {
  id: string;
  label: string;
  domain: string;
  segments: { id: string; label: string; aliases: string[] }[];
  monitoring_metrics: string[];
  financial_validation: string[];
  source_priorities: string[];
};

export type ResearchSessionRequest = {
  message: string;
  depth?: string;
  mode?: "fixture" | "remote_shadow" | "remote_primary";
  search_provider?: string;
  network?: string;
  inline?: boolean;
  skill?: "company-research" | "industry-research" | "event-impact";
};

export type ResearchClaim = {
  local_id: string;
  claim_type?: string;
  text: string;
  evidence_text?: string;
  source_id?: string;
  location?: string;
  tier?: number;
};

export type ResearchSource = {
  local_id: string;
  url: string;
  title: string;
  publisher?: string;
  published_at?: string;
  content_type?: string;
  source_type?: string;
  source_skill?: string;
  source_label?: string;
  evidence_role?: string;
  tier?: number;
};

export type ResearchEvent = {
  seq: number;
  event_type: string;
  status: string;
  run_id?: string;
  payload?: Record<string, unknown>;
};

export type ResearchSessionView = {
  ok: boolean;
  session: {
    id: string;
    title: string;
    skill: string;
    status: string;
    primary_entity_type?: ResearchSubjectType;
    primary_entity_name: string;
    primary_entity_code: string;
    primary_entity_exchange: string;
    summary?: {
      universe_status?: string;
      plan?: { research_goal?: string; tasks?: { id: string; question: string }[] };
      notice?: string;
      formal?: boolean;
    };
  };
  messages: {
    id: string;
    role: "USER" | "ASSISTANT";
    content: string;
    claim_refs?: string[];
    source_refs?: string[];
    run_id?: string;
  }[];
  runs: { id: string; status?: string; question?: string }[];
  current_thesis: { text: string; formal: boolean; label: string };
  sources: ResearchSource[];
  claims: ResearchClaim[];
  conflicts: { topic?: string }[];
  open_questions: string[];
  events: ResearchEvent[];
  notice?: string;
  upgrade_history?: {
    run_id: string;
    upgraded_at: string;
    mode: "REUSE_EXISTING_EVIDENCE" | "REUSE_AND_FILL_GAPS";
    planner_model: string;
    analyst_model: string;
    reused_source_count: number;
    reused_claim_count: number;
    new_source_count: number;
    new_claim_count: number;
    previous_view: string;
    current_view: string;
    judgment_changes: string[];
    open_questions: string[];
    history_preserved: boolean;
  }[];
};

export type DialoguePacket = {
  query: string;
  intent: string;
  classified: string;
  room: string;
  followup: boolean;
  next: { slot: string; ask: string };
  reply?: string;
  action: string;
  tools?: { name: string; args: Record<string, string | boolean> }[];
  filled: Record<string, string>;
  slots: Record<string, string>;
  vision?: { ok: boolean; n_trades: number; error: string } | null;
  context: { room: string; read: string[]; facts: Record<string, string | number | null> };
  window: {
    max_history_turns: number;
    history_turns: number;
    prompt_turns?: number;
    loaded: string[];
    facts_keys: string[];
    not_loaded: string[];
  };
  history?: SessionMessage[];
  history_turns: number;
  disclaimer: string;
};

export type SessionMessage = {
  role: string;
  text: string;
  intent?: string;
  classified?: string;
  slot?: string;
  image?: boolean;
};

export type SessionState = {
  room: string;
  intent: string;
  slots: Record<string, string>;
  history: SessionMessage[];
  awaiting: string;
  updated_at: string;
};

export type ReviewCandidate = {
  decision_id: string;
  rank?: number;
  score?: number;
  reason: string;
};

export type ReviewOpenDecision = {
  id: string;
  opened_on: string;
  code: string;
  name: string;
  status: string;
  origin: string;
  thesis: string;
  account: string;
};

export type ReviewExecution = {
  id: string;
  symbol: string;
  name: string;
  side: string;
  price: number;
  qty: number;
  time: string;
  executed_on: string;
  account: string;
  match_status: string;
  match_reason: string;
  decision_id: string | null;
  fingerprint: string;
  subjective_context: string;
  broker_order_id: string;
  claimable: boolean;
  candidates: ReviewCandidate[];
  open_decisions: ReviewOpenDecision[];
};

export type ReviewQueueItem = {
  decision_id: string;
  symbol: string;
  name: string;
  account: string;
  status: string;
  today_execution_count: number;
  realized_pnl: number | null;
  process_violation_count: number;
  coverage: string;
  review_reason: string[];
  detail: string;
};

export type ReviewToday = {
  date: string;
  executions: ReviewExecution[];
  claimable: ReviewExecution[];
  queue: ReviewQueueItem[];
};

export type ReviewArchiveItem = {
  id: string;
  opened_on: string;
  closed_on: string;
  reviewed_at: string;
  code: string;
  name: string;
  direction: string;
  status: string;
  origin: string;
  thesis: string;
  holding_period: string;
  execution_count: number;
  review_count: number;
  realized_pnl: number | null;
};

export type ReviewArchive = {
  items: ReviewArchiveItem[];
  total: number;
};

export type ReviewDecision = {
  decision_id: string;
  card: string;
  decision: Record<string, unknown>;
  executions: Record<string, unknown>[];
  context?: Record<string, unknown>;
  context_diff?: {
    changes: { field: string; entry: unknown; review: unknown }[];
    note?: string;
  };
  research_link?: {
    attached: boolean;
    project_id?: string;
    thesis_id?: string;
    decision_version?: number;
    current_version?: number;
    diff_verdict?: string;
    research_error?: string;
  };
};

export type RecorderQuoted = {
  value: unknown;
  source_quote: string | null;
  provenance?: string;
};

export type RecorderParseResult = {
  input_id: string;
  draft_id: string;
  status: string;
  witnessed_at: string;
  origin?: string;
  ask?: string | null;
  error?: string | null;
  grounding_ok?: boolean;
  draft: {
    intent: string;
    symbol: RecorderQuoted;
    thesis: RecorderQuoted;
    market_context: RecorderQuoted;
    expectations: { raw_text: string; source_quote: string }[];
    plan: {
      entry_rule: RecorderQuoted;
      invalidation: RecorderQuoted;
      target_size_pct: RecorderQuoted;
      holding_period: RecorderQuoted;
    };
    missing_fields: string[];
    ambiguities: string[];
  } | null;
};

export { ApiError, BASE };
