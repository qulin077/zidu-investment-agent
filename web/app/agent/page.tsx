"use client";

import Link from "next/link";
import { Fragment, FormEvent, useEffect, useRef, useState } from "react";
import { api, type AgentHome, type AgentPanel, type AgentProgressEvent, type AgentTurn } from "@/lib/api";
import { IntakeChoices, inlineContent, isCompanyReport, ResearchReport } from "@/components/agent/ResearchReport";

type Message = AgentTurn["messages"][number];

const DEMO_MODE = process.env.NEXT_PUBLIC_DEMO_MODE === "1";
const DEMO_TASKS = [
  "完整研究东山精密：先给研究计划，再补齐财报、管理层交流、卖方预期、市场叙事与反证。",
  "记录一条东山精密的模拟决策：我关注 AI 服务器相关需求能否兑现，先保存为草稿，不要替我确认。",
  "复盘东山精密这条模拟决策：对照事前 Thesis、实际执行和当前证据，先问我发生了什么。",
];

function mark(status: string) {
  if (status === "gap") return "!";
  if (status === "failed") return "×";
  return "✓";
}

function processIcon(phase: string) {
  if (phase === "intent") return "◎";
  if (phase === "plan") return "◇";
  if (phase === "search") return "⌕";
  if (phase === "read") return "↗";
  if (phase === "evidence") return "◆";
  if (phase === "research") return "⌕";
  if (phase === "data") return "↻";
  if (phase === "memory") return "◇";
  if (phase === "synthesis") return "✦";
  if (phase === "done") return "✓";
  return "●";
}

function processPhaseLabel(phase: string) {
  if (phase === "intent") return "意图";
  if (phase === "plan") return "计划";
  if (phase === "search") return "检索";
  if (phase === "read") return "原文";
  if (phase === "evidence") return "证据";
  if (phase === "data") return "数据";
  if (phase === "synthesis") return "综合";
  if (phase === "memory") return "记忆";
  if (phase === "done") return "完成";
  if (phase === "tool") return "工具";
  return "执行";
}

function MessageContent({ content, companyName, busy, showSuggestions, onSuggestion }: {
  content: string;
  companyName?: string;
  busy?: boolean;
  showSuggestions?: boolean;
  onSuggestion: (value: string) => void;
}) {
  if (isCompanyReport(content)) return <ResearchReport content={content} companyName={companyName} />;
  return (
    <div className="agent-message-content">
      {content.split("\n").map((raw, index) => {
        const line = raw.trim();
        if (!line) return <span className="agent-message-space" key={index} />;
        if (line.startsWith("# ")) return <h2 key={index}>{inlineContent(line.slice(2))}</h2>;
        if (line.startsWith("## ")) return <h3 key={index}>{inlineContent(line.slice(3))}</h3>;
        if (line.startsWith("### ")) return <h4 key={index}>{inlineContent(line.slice(4))}</h4>;
        if (line.startsWith("- ")) return <p className="agent-message-bullet" key={index}>{inlineContent(line.slice(2))}</p>;
        return <p key={index}>{inlineContent(line)}</p>;
      })}
      {showSuggestions ? <IntakeChoices content={content} disabled={busy} onChoose={onSuggestion} /> : null}
    </div>
  );
}

function ProcessTrace({ events, running, elapsed }: {
  events: AgentProgressEvent[];
  running: boolean;
  elapsed: number;
}) {
  const rows = events.length ? events : [{
    seq: 0,
    phase: "intent",
    title: "正在连接 Agent",
    detail: "准备读取对话和长期上下文",
    status: "running",
  }];
  const visibleRows = rows.slice(-48);
  const readCount = rows.filter((event) => event.phase === "read" && event.status === "completed").length;
  const searchCount = rows.filter((event) => event.phase === "search").length;
  const gapCount = rows.filter((event) => event.status === "gap" || event.status === "failed").length;
  return (
    <details className={`agent-process ${running ? "running" : "completed"}`} open={running}>
      <summary>
        <span className="agent-process-state">{running ? <span className="agent-process-spinner" /> : "✓"}</span>
        <span>{running ? "正在执行" : `已完成 · ${rows.length} 步`}</span>
        <span className="agent-process-time">{elapsed}s</span>
        <span className="agent-process-chevron">⌄</span>
      </summary>
      <ol>
        {visibleRows.map((event, index) => {
          const effectiveStatus = event.status === "running" && index < visibleRows.length - 1 ? "completed" : event.status;
          return (
          <li key={`${event.seq}-${index}`} className={`process-${effectiveStatus}`}>
            <span className="agent-process-icon">{processIcon(event.phase)}</span>
            <span>
              <span className="agent-process-heading">
                <span className={`agent-process-phase phase-${event.phase}`}>{processPhaseLabel(event.phase)}</span>
                <strong>{event.title}</strong>
              </span>
              {event.detail ? <small>{event.detail}</small> : null}
            </span>
          </li>
          );
        })}
      </ol>
      {rows.length > 3 ? (
        <div className="agent-process-stats">
          <span>检索动作 {searchCount}</span>
          <span>已读原文 {readCount}</span>
          <span className={gapCount ? "has-gap" : ""}>缺口/失败 {gapCount}</span>
        </div>
      ) : null}
      <p className="agent-process-note">这里只展示可核对的执行轨迹，不展示模型的私有思维链。</p>
    </details>
  );
}

export default function AgentPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [panel, setPanel] = useState<AgentPanel | null>(null);
  const [draft, setDraft] = useState("");
  const [goal, setGoal] = useState("");
  const [live, setLive] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [pendingMessage, setPendingMessage] = useState("");
  const [process, setProcess] = useState<AgentProgressEvent[]>([]);
  const [traceAfterId, setTraceAfterId] = useState("");
  const [startedAt, setStartedAt] = useState(0);
  const [elapsed, setElapsed] = useState(0);
  const logRef = useRef<HTMLDivElement | null>(null);

  function applyHome(data: AgentHome) {
    setMessages(data.messages || []);
    setPanel(data.panel || null);
  }

  function applyTurn(data: AgentTurn) {
    setMessages(data.messages || []);
    setPanel(data.panel || null);
  }

  useEffect(() => {
    void api.agentHome().then(applyHome).catch((err: Error) => setError(err.message));
  }, []);

  useEffect(() => {
    if (!busy || !startedAt) return;
    const update = () => setElapsed(Math.max(0, Math.floor((Date.now() - startedAt) / 1000)));
    update();
    const timer = window.setInterval(update, 1000);
    return () => window.clearInterval(timer);
  }, [busy, startedAt]);

  useEffect(() => {
    const node = logRef.current;
    if (!node) return;
    node.scrollTo({ top: node.scrollHeight, behavior: busy ? "smooth" : "auto" });
  }, [messages, pendingMessage, process, busy]);

  async function sendMessage(value: string) {
    const message = value.trim();
    if (!message || busy) return;
    setBusy(true);
    setError("");
    setDraft("");
    setPendingMessage(message);
    setProcess([]);
    setTraceAfterId("");
    setStartedAt(Date.now());
    setElapsed(0);
    try {
      const data = await api.agentMessageStream(message, live ? "live" : "replay", (event) => {
        setProcess((current) => [...current, event]);
      });
      applyTurn(data);
      setProcess(data.process?.length ? data.process : process);
      const user = [...(data.messages || [])].reverse().find((row) => row.role === "user");
      setTraceAfterId(user?.id || "");
      setPendingMessage("");
    } catch (err) {
      setError((err as Error).message);
      setProcess((current) => [...current, {
        seq: current.length + 1,
        phase: "done",
        title: "本轮执行失败",
        detail: "没有把未完成内容当成结论",
        status: "failed",
      }]);
    } finally {
      setBusy(false);
    }
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    await sendMessage(draft);
  }

  async function onGoal(event: FormEvent) {
    event.preventDefault();
    const title = goal.trim();
    if (!title) return;
    setError("");
    try {
      await api.agentGoal({
        title,
        goal_type: "RESEARCH",
        project_ids: panel?.active_project?.id ? [panel.active_project.id] : [],
      });
      setGoal("");
      applyHome(await api.agentHome());
    } catch (err) {
      setError((err as Error).message);
    }
  }

  const project = panel?.active_project;
  const sessionHref = project?.research_session_id
    ? `/research?session=${encodeURIComponent(project.research_session_id)}`
    : "/research";

  return (
    <section className="research-page">
      <header className="research-head">
        <h2>Investment Agent</h2>
        <p className="section-note">
          先聊清楚，再在需要时研究、记录或复盘。重要内容会沉淀，正式事实仍需证据和确认。
        </p>
      </header>
      <div className="research-desk">
        <div className="research-chat">
          <div className="research-log" ref={logRef}>
            {panel?.health ? (
              <p className="section-note">
                Model: {panel.health.llm_configured ? "Configured" : "Unavailable"}
                {" · "}
                {panel.health.provider || "OpenAI Compatible"}
                {panel.health.model ? ` · ${panel.health.model}` : ""}
                {" · "}
                Search: {panel.health.search || "Unavailable"}
                {" · "}
                iFinD: {panel.health.ifind || "Unavailable"}
                {" · "}
                Runtime: {panel.health.runtime || "legacy"}
                {panel.health.max_steps ? ` · ≤${panel.health.max_steps} steps` : ""}
                {" · "}
                Network: {live ? "Live" : "Replay"}
                {panel.last_runtime?.planning_mode ? ` · ${panel.last_runtime.planning_mode}` : ""}
                {panel.last_runtime?.model ? ` · Last: ${panel.last_runtime.model}` : ""}
                {typeof panel.last_runtime?.model_calls === "number" ? ` ×${panel.last_runtime.model_calls}` : ""}
                {panel.last_runtime?.last_steps_used ? ` · ${panel.last_runtime.last_steps_used} steps` : ""}
              </p>
            ) : null}
            {messages.length ? messages.map((row, index) => (
              <Fragment key={row.id}>
                <div className={`research-bubble ${row.role === "user" ? "user" : "assistant"} ${isCompanyReport(row.content) ? "report" : ""}`}>
                  {row.role === "user" ? <p>{row.content}</p> : (
                    <MessageContent
                      content={row.content}
                      companyName={row.entity_refs?.[0]?.name || row.entity_refs?.[0]?.mention}
                      busy={busy}
                      showSuggestions={index === messages.length - 1}
                      onSuggestion={(value) => void sendMessage(value)}
                    />
                  )}
                </div>
                {traceAfterId === row.id && process.length ? (
                  <ProcessTrace events={process} running={false} elapsed={elapsed} />
                ) : null}
              </Fragment>
            )) : DEMO_MODE ? (
              <div className="agent-demo-start">
                <p>从一个真实工作流开始</p>
                {DEMO_TASKS.map((task) => (
                  <button key={task} type="button" disabled={busy} onClick={() => void sendMessage(task)}>
                    {task}
                  </button>
                ))}
              </div>
            ) : <p className="section-note">直接说你在看的公司、想记的一笔，或要复盘的决策。</p>}
            {pendingMessage ? (
              <div className="research-bubble user pending"><p>{pendingMessage}</p></div>
            ) : null}
            {busy || (pendingMessage && process.length) ? (
              <ProcessTrace events={process} running={busy} elapsed={elapsed} />
            ) : null}
            {error ? <p className="research-notice">{error}</p> : null}
          </div>
          <form className="research-form" onSubmit={onSubmit}>
            <input
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              placeholder="聊聊今天，或者说你想研究、记录、复盘什么…"
              aria-label="给 Investment Agent 的一句话"
            />
            <button type="submit" disabled={busy}>发送</button>
          </form>
          <label className="section-note">
            <input type="checkbox" checked={live} onChange={(event) => setLive(event.target.checked)} />
            {" "}允许联网获取最新资料。关掉则只用已有研究记忆和本地数据。
          </label>
        </div>
        <aside className="research-board">
          <section>
            <h3>Active Goal</h3>
            <p>{panel?.active_goal?.title || "还没有长期目标。"}</p>
            <form className="research-form" onSubmit={onGoal}>
              <input
                value={goal}
                onChange={(event) => setGoal(event.target.value)}
                placeholder="记下目标"
                aria-label="长期目标"
              />
              <button type="submit">记下</button>
            </form>
          </section>
          <section>
            <h3>对话上下文</h3>
            <p>当前标的：{panel?.active_entity || "还没有"}</p>
            <p>当前事件：{panel?.active_event || "还没有"}</p>
            {panel?.active_workflow?.id ? (
              <p className="section-note">
                Workflow：{panel.active_workflow.workflow_type} · {panel.active_workflow.stage}
                {panel.active_workflow.pending_question ? ` · ${panel.active_workflow.pending_question}` : ""}
              </p>
            ) : null}
            <p className="section-note">{(panel?.open_questions || []).slice(0, 3).join("；")}</p>
          </section>
          <section>
            <h3>Today&apos;s Journal</h3>
            {(panel?.today_journal || []).length ? (
              <ul>
                {panel?.today_journal?.map((row) => (
                  <li key={row.id}>{row.summary || row.raw_text}</li>
                ))}
              </ul>
            ) : <p className="section-note">今天还没有需要沉淀的对话。</p>}
          </section>
          <section>
            <h3>Active Project</h3>
            <p>{project?.title || "还没有研究项目。"}</p>
            {project?.strategy?.name ? (
              <p className="section-note">
                本项目研究偏好：{project.strategy.name}{project.strategy.time_horizon ? ` · ${project.strategy.time_horizon}` : ""}
              </p>
            ) : null}
            <p className="section-note">{project?.thesis || ""}</p>
            <p className="section-note">{project?.open_question || ""}</p>
            <p><Link href={sessionHref}>打开研究工作区</Link></p>
          </section>
          <section>
            <h3>Open Decisions</h3>
            {(panel?.open_decisions || []).length ? (
              <ul>
                {panel?.open_decisions?.map((row) => (
                  <li key={row.id}><Link href={`/review/${row.id}`}>{row.name || row.id}</Link> · {row.status}</li>
                ))}
              </ul>
            ) : <p className="section-note">没有未关闭的 Decision。</p>}
          </section>
          <section>
            <h3>Pending Reviews</h3>
            {(panel?.pending_reviews || []).length ? (
              <ul>
                {panel?.pending_reviews?.map((row) => (
                  <li key={row.id}><Link href={`/review/${row.id}/guided`}>{row.name || row.id}</Link></li>
                ))}
              </ul>
            ) : <p className="section-note">没有待复盘。</p>}
          </section>
          <section>
            <h3>Active Rules</h3>
            {(panel?.active_rules || []).length ? (
              <ul>
                {panel?.active_rules?.map((row) => <li key={row.id}>{row.rule_text}</li>)}
              </ul>
            ) : <p className="section-note">没有生效中的 Rule。</p>}
          </section>
          <section>
            <h3>最近动作</h3>
            <ul className="research-trace">
              {(panel?.activity || []).map((row) => (
                <li key={row.id} className={row.status === "gap" ? "trace-gap" : ""}>
                  {mark(row.status)} {row.summary}
                </li>
              ))}
            </ul>
          </section>
        </aside>
      </div>
    </section>
  );
}
