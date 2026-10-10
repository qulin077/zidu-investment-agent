"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { api, type GuidedSession } from "@/lib/api";

const ERROR_OPTIONS = [
  "NONE",
  "RESEARCH_ERROR",
  "EXPECTATION_ERROR",
  "TIMING_ERROR",
  "SIZING_ERROR",
  "EXECUTION_ERROR",
  "RISK_CONTROL_ERROR",
  "EMOTION_ERROR",
  "PROCESS_ERROR",
  "EXTERNAL_SHOCK",
];

export default function GuidedReviewPage({
  params,
}: {
  params: Promise<{ decisionId: string }>;
}) {
  const [decisionId, setDecisionId] = useState("");
  const [data, setData] = useState<GuidedSession | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [option, setOption] = useState("");
  const [answer, setAnswer] = useState("");
  const [primary, setPrimary] = useState("NONE");
  const [lesson, setLesson] = useState("");
  const [done, setDone] = useState<Record<string, unknown> | null>(null);

  useEffect(() => {
    void params.then((p) => setDecisionId(p.decisionId));
  }, [params]);

  async function load(id: string) {
    setBusy(true);
    setError("");
    try {
      const flags = await api.reviewFlags();
      if (!flags.GUIDED_REVIEW_ENABLED) {
        setError("Guided Review 尚未开启（P1.25 Eval Gate 未通过前保持关闭）。");
        setData(null);
        return;
      }
      setData(await api.guidedContext(id));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    if (decisionId) void load(decisionId);
  }, [decisionId]);

  const unresolved = data?.unresolved || data?.turn?.unresolved_dimension || "";
  const facts = data?.facts;
  const plan = facts?.plan || {};
  const actual = facts?.actual || {};
  const outcome = facts?.outcome || {};

  async function run(fn: () => Promise<unknown>) {
    if (!decisionId) return;
    setBusy(true);
    setError("");
    try {
      const result = await fn();
      if (result && typeof result === "object" && "turn" in (result as object)) {
        setData(result as GuidedSession);
      } else {
        await load(decisionId);
      }
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <section>
        <h2>结构化复盘</h2>
        <p className="section-note">
          第一屏是事实，不是点评。Agent 一次只问一个问题，不能替你写归因，也不会荐股。
        </p>
        <p>
          <Link href={`/review/${decisionId}`}>← Decision 卡片</Link>
        </p>
        {error ? <p className="warn-line">{error}</p> : null}
      </section>

      {data?.context_diff?.changes?.length ? (
        <section>
          <h2>当时环境 vs 复盘时环境</h2>
          <p className="section-note">{data.context_diff.note || "环境变化事实。不自动生成归因。"}</p>
          <ul>
            {data.context_diff.changes.map((row) => (
              <li key={row.field}>
                {row.field}: {String(row.entry ?? "—")} → {String(row.review ?? "—")}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {facts ? (
        <section>
          <h2>你原来怎么想 vs 你实际怎么做 vs 后来发生什么</h2>
          <p className="section-note">
            {String(facts.quadrant || "")} · 覆盖 {String(facts.quote_coverage || "—")}
          </p>
          <div className="fact-grid">
            <div className="claim-card">
              <h3>原计划</h3>
              <p>仓位 {String(plan.target_size_pct ?? "—")}%</p>
              <p>入场 {String(plan.entry_rule || "—")}</p>
              <p>失效 {String(plan.invalidation || "—")}</p>
            </div>
            <div className="claim-card">
              <h3>实际</h3>
              <p>最高仓位 {String(actual.max_size_pct ?? "—")}%</p>
              <p>成交 {String(actual.n_executions ?? 0)} 笔</p>
            </div>
            <div className="claim-card">
              <h3>结果</h3>
              <p>
                实现盈亏{" "}
                {outcome && outcome.realized_pct != null ? `${String(outcome.realized_pct)}%` : "—"}
              </p>
              <p>PnL {outcome && outcome.gross_pnl != null ? String(outcome.gross_pnl) : "—"}</p>
            </div>
            <div className="claim-card">
              <h3>系统事实</h3>
              {(facts.violations || []).length === 0 ? (
                <p>Process Violation = none</p>
              ) : (
                facts.violations.map((v) => (
                  <p key={v.code}>
                    {v.code} {v.detail || ""}
                  </p>
                ))
              )}
              {facts.counterfactual?.statement ? <p>{facts.counterfactual.statement}</p> : null}
            </div>
          </div>
        </section>
      ) : null}

      {data?.turn && !done ? (
        <section>
          <h2>{unresolved || "问题"}</h2>
          <p>{data.turn.question}</p>
          {unresolved === "OUTCOME" ? (
            <div className="claim-actions">
              <button type="button" disabled={busy} onClick={() => run(() => api.confirmOutcome(decisionId, true))}>
                确认 Outcome
              </button>
            </div>
          ) : null}
          {unresolved === "VIOLATIONS" ? (
            <div className="claim-actions">
              <button
                type="button"
                disabled={busy}
                onClick={() => run(() => api.confirmViolations(decisionId, true))}
              >
                确认 Process Violations
              </button>
            </div>
          ) : null}
          {unresolved === "ATTRIBUTION" ? (
            <>
              <form
                className="claim-actions"
                onSubmit={(event: FormEvent) => {
                  event.preventDefault();
                  void run(() => api.guidedAnswer(decisionId, { option_id: option, answer }));
                }}
              >
                <select value={option} onChange={(e) => setOption(e.target.value)}>
                  <option value="">选择一项（不会自动写成归因）</option>
                  {(data.turn.options || []).map((opt) => (
                    <option key={opt.id} value={opt.id}>
                      {opt.id} {opt.label}
                    </option>
                  ))}
                </select>
                <input value={answer} onChange={(e) => setAnswer(e.target.value)} placeholder="补充说明（可空）" />
                <button type="submit" disabled={busy}>
                  记录回答
                </button>
              </form>
              <p className="section-note">候选只是选项。写入 attribution 必须再点确认。</p>
              <div className="claim-actions">
                <select value={primary} onChange={(e) => setPrimary(e.target.value)}>
                  {ERROR_OPTIONS.map((code) => (
                    <option key={code} value={code}>
                      {code}
                    </option>
                  ))}
                </select>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => run(() => api.confirmAttribution(decisionId, { primary_error: primary }))}
                >
                  确认归因
                </button>
              </div>
            </>
          ) : null}
          {unresolved === "LESSON" ? (
            <form
              className="claim-actions"
              onSubmit={async (event: FormEvent) => {
                event.preventDefault();
                setBusy(true);
                setError("");
                try {
                  if (lesson.trim()) {
                    await api.guidedAnswer(decisionId, { answer: lesson });
                  }
                  const result = await api.completeReview(decisionId, lesson);
                  setDone(result);
                } catch (err) {
                  setError((err as Error).message);
                } finally {
                  setBusy(false);
                }
              }}
            >
              <input
                value={lesson}
                onChange={(e) => setLesson(e.target.value)}
                placeholder="下次遇到类似情况要注意什么？不要写明天买什么"
              />
              <button type="submit" disabled={busy}>
                完成复盘
              </button>
            </form>
          ) : null}
        </section>
      ) : null}

      {done ? (
        <section>
          <h2>REVIEWED</h2>
          <p>
            {String(done.decision_id)} · {String(done.status)} · lesson {String(done.lesson || "—")}
          </p>
          {(() => {
            const mem = (done.memory || {}) as {
              pattern?: { id?: string; pattern_key?: string; status?: string; occurrence_count?: number };
              mistake?: unknown;
              reason?: string;
            };
            const pattern = mem.pattern;
            if (!pattern?.id) {
              return <p className="muted">Lesson 已保存。{mem.reason || "未形成 Mistake Instance。"}</p>;
            }
            return (
              <div className="claim-card">
                <p>Lesson 已保存</p>
                <p>
                  发现与历史模式相似：{pattern.pattern_key} · {pattern.status} · 过去出现{" "}
                  {pattern.occurrence_count} 次
                </p>
                <div className="claim-actions">
                  <Link href={`/review/patterns/${pattern.id}`}>查看模式</Link>
                  <span className="muted">暂不处理</span>
                </div>
              </div>
            );
          })()}
          <Link href={`/review/${decisionId}`}>查看 Decision</Link>
        </section>
      ) : null}
    </>
  );
}
