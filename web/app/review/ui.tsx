"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import {
  api,
  type ProductHealth,
  type ProductMetrics,
  type ReviewExecution,
  type ReviewQueueItem,
  type ReviewToday,
} from "@/lib/api";

const STATUS_LABEL: Record<string, string> = {
  AUTO_MATCHED: "自动匹配",
  REVIEW_REQUIRED: "需认领",
  NO_CANDIDATE: "无候选",
  HUMAN_CONFIRMED: "已确认",
  HUMAN_UNMATCHED: "先不挂",
};

function todayISO() {
  const now = new Date();
  const y = now.getFullYear();
  const m = String(now.getMonth() + 1).padStart(2, "0");
  const d = String(now.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

function money(value: number | null) {
  if (value === null || value === undefined) return "—";
  const n = Number(value);
  const sign = n > 0 ? "+" : "";
  return `${sign}${n.toLocaleString("zh-CN", { maximumFractionDigits: 0 })}`;
}

function ClaimRow({
  row,
  busy,
  onConfirm,
  onPostHoc,
  onUnmatched,
}: {
  row: ReviewExecution;
  busy: boolean;
  onConfirm: (executionId: string, decisionId: string, note: string) => void;
  onPostHoc: (executionId: string) => void;
  onUnmatched: (executionId: string) => void;
}) {
  const [choice, setChoice] = useState(row.candidates[0]?.decision_id || row.open_decisions[0]?.id || "");
  const [note, setNote] = useState("");
  const options = useMemo(() => {
    const seen = new Set<string>();
    const out: { id: string; label: string }[] = [];
    for (const c of row.candidates) {
      if (seen.has(c.decision_id)) continue;
      seen.add(c.decision_id);
      out.push({
        id: c.decision_id,
        label: `${c.decision_id}  score=${c.score ?? "—"}`,
      });
    }
    for (const d of row.open_decisions) {
      if (seen.has(d.id)) continue;
      seen.add(d.id);
      out.push({
        id: d.id,
        label: `${d.id}  ${d.status}  ${d.origin}`,
      });
    }
    return out;
  }, [row]);

  return (
    <div className="claim-card">
      <div className="claim-head">
        <span className="code">{row.symbol}</span>
        <span>
          {row.side} {row.price} × {row.qty}
        </span>
        <span className="muted">{row.time || "—"}</span>
        <span className={`match-pill match-${row.match_status}`}>{STATUS_LABEL[row.match_status] || row.match_status}</span>
      </div>
      <p className="muted">{row.match_reason || "待人工认领"}</p>
      {row.candidates.length > 1 ? (
        <p className="warn-line">多个候选都说得通，系统不会自动绑定。</p>
      ) : null}
      <form
        className="claim-actions"
        onSubmit={(event: FormEvent) => {
          event.preventDefault();
          if (choice) onConfirm(row.id, choice, note);
        }}
      >
        <select value={choice} onChange={(e) => setChoice(e.target.value)} disabled={busy || options.length === 0}>
          {options.length === 0 ? <option value="">没有可挂的 Decision</option> : null}
          {options.map((opt) => (
            <option key={opt.id} value={opt.id}>
              {opt.label}
            </option>
          ))}
        </select>
        <input
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="归属理由（可空）"
          disabled={busy}
        />
        <button type="submit" disabled={busy || !choice}>
          挂到已有 Decision
        </button>
        <button type="button" disabled={busy} onClick={() => onPostHoc(row.id)}>
          新建复盘 Decision
        </button>
        <button type="button" className="ghost" disabled={busy} onClick={() => onUnmatched(row.id)}>
          先不挂
        </button>
      </form>
    </div>
  );
}

function rate(cell: { value?: number | null } | undefined) {
  if (!cell || cell.value === null || cell.value === undefined) return "—";
  return `${(Number(cell.value) * 100).toFixed(0)}%`;
}

export function HealthPanel({
  health,
  metrics,
}: {
  health: ProductHealth | null;
  metrics: ProductMetrics | null;
}) {
  const mem = metrics?.memory || {};
  const rec = metrics?.recorder || {};
  const dq = metrics?.data_quality || {};
  return (
    <section>
      <h2>System / Product Health</h2>
      <p className="section-note">看系统有没有在工作。不是行情终端，也不是荐股。</p>
      <div className="health-grid">
        <div>
          <span className="muted">Full test baseline</span>
          <strong>CI: discover + evals</strong>
        </div>
        <div>
          <span className="muted">Quotes</span>
          <strong>{health?.items?.quotes?.status || "—"}</strong>
        </div>
        <div>
          <span className="muted">Product Events</span>
          <strong>{health?.items?.product_events?.status || "—"}</strong>
        </div>
        <div>
          <span className="muted">Pipelines</span>
          <strong>{health?.items?.pipelines?.status || "—"}</strong>
        </div>
        <div>
          <span className="muted">Event write</span>
          <strong>{rate(dq.event_write_success_rate as { value?: number | null })}</strong>
        </div>
        <div>
          <span className="muted">Review backlog</span>
          <strong>{health?.review_backlog ?? "—"}</strong>
        </div>
        <div>
          <span className="muted">Recorder confirm</span>
          <strong>{rate(rec.draft_confirm_rate as { value?: number | null })}</strong>
        </div>
        <div>
          <span className="muted">Critical edit</span>
          <strong>{rate(rec.critical_field_edit_rate as { value?: number | null })}</strong>
        </div>
        <div>
          <span className="muted">Memory precision</span>
          <strong>{rate(mem.memory_precision as { value?: number | null })}</strong>
        </div>
        <div>
          <span className="muted">Repeated mistakes</span>
          <strong>{rate(mem.repeated_confirmed_mistake_rate as { value?: number | null })}</strong>
        </div>
        <div>
          <span className="muted">Active rules</span>
          <strong>{String(mem.active_rule_n ?? "—")}</strong>
        </div>
        <div>
          <span className="muted">Mode</span>
          <strong>
            {health?.flags?.PILOT_MODE ? "PILOT" : "LIVE"} · {health?.flags?.RECORDER_REMOTE_MODE || "—"}
            {health?.flags?.DECISION_CONTEXT_ENABLED === false ? " · context off" : ""}
          </strong>
        </div>
      </div>
    </section>
  );
}

export function ReviewTodayClient({ initialDate }: { initialDate: string }) {
  const [date, setDate] = useState(initialDate || todayISO());
  const [data, setData] = useState<ReviewToday | null>(null);
  const [health, setHealth] = useState<ProductHealth | null>(null);
  const [metrics, setMetrics] = useState<ProductMetrics | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async (day: string) => {
    setError("");
    try {
      const [payload, h, m] = await Promise.all([
        api.reviewToday(day),
        api.productHealth(),
        api.productMetrics(),
      ]);
      setData(payload);
      setHealth(h);
      setMetrics(m);
    } catch (err) {
      setError((err as Error).message);
      setData(null);
    }
  }, []);

  useEffect(() => {
    load(date);
  }, [date, load]);

  async function run(action: () => Promise<unknown>) {
    setBusy(true);
    setError("");
    try {
      await action();
      await load(date);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <section>
        <h2>成交核对</h2>
        <p className="section-note">
          Decision 是一次完整意图，Execution 是成交事实。事后新建的 Decision 标记为 POST_HOC，不进 Plan Adherence。
        </p>
        <div className="review-toolbar">
          <label>
            日期
            <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
          </label>
          <Link href="/today">Today</Link>
          <Link href="/review">复盘档案</Link>
          <Link href="/review/new">记录一个想法</Link>
          <Link href="/review/patterns">模式</Link>
          <Link href="/review/rules">规则</Link>
          <button type="button" className="ghost" onClick={() => load(date)} disabled={busy}>
            刷新
          </button>
        </div>
        {error ? <p className="warn-line">{error}</p> : null}
      </section>
      <HealthPanel health={health} metrics={metrics} />

      <section>
        <h2>今日成交</h2>
        <p className="section-note">客观成交。匹配状态来自 core.review.matching，页面不改 decision_id。</p>
        {!data?.executions.length ? (
          <p className="muted">这一天没有 execution。</p>
        ) : (
          <table className="review-table">
            <thead>
              <tr>
                <th>代码</th>
                <th>方向</th>
                <th className="num">价格</th>
                <th className="num">数量</th>
                <th>时间</th>
                <th>账户</th>
                <th>匹配</th>
                <th>Decision</th>
              </tr>
            </thead>
            <tbody>
              {data.executions.map((row) => (
                <tr key={row.id}>
                  <td className="code">{row.symbol}</td>
                  <td>{row.side}</td>
                  <td className="num">{row.price}</td>
                  <td className="num">{row.qty}</td>
                  <td>{row.time || "—"}</td>
                  <td>{row.account || "—"}</td>
                  <td>
                    <span className={`match-pill match-${row.match_status}`}>
                      {STATUS_LABEL[row.match_status] || row.match_status || "—"}
                    </span>
                  </td>
                  <td>
                    {row.decision_id ? (
                      <Link href={`/review/${row.decision_id}`}>{row.decision_id}</Link>
                    ) : (
                      "—"
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section>
        <h2>待认领</h2>
        <p className="section-note">只处理 REVIEW_REQUIRED / NO_CANDIDATE。多候选不会自动绑定。</p>
        {!data?.claimable.length ? (
          <p className="muted">没有待认领成交。</p>
        ) : (
          data.claimable.map((row) => (
            <ClaimRow
              key={row.id}
              row={row}
              busy={busy}
              onConfirm={(executionId, decisionId, note) =>
                run(() => api.reviewConfirm({ execution_id: executionId, decision_id: decisionId, note }))
              }
              onPostHoc={(executionId) =>
                run(() => api.reviewPostHoc({ execution_id: executionId }))
              }
              onUnmatched={(executionId) =>
                run(() => api.reviewUnmatched({ execution_id: executionId }))
              }
            />
          ))
        )}
      </section>

      <section>
        <h2>今日待复盘</h2>
        <p className="section-note">直接用 queue.as_dicts(day)。点 Decision 看详情。</p>
        {!data?.queue.length ? (
          <p className="muted">队列为空。</p>
        ) : (
          <table className="review-table">
            <thead>
              <tr>
                <th>Decision</th>
                <th>代码</th>
                <th>状态</th>
                <th className="num">今日成交</th>
                <th className="num">已实现</th>
                <th className="num">违规</th>
                <th>覆盖</th>
                <th>原因</th>
              </tr>
            </thead>
            <tbody>
              {data.queue.map((item: ReviewQueueItem, index) => (
                <tr key={`${item.decision_id || item.symbol}-${index}`}>
                  <td>
                    {item.decision_id ? (
                      <>
                        <Link href={`/review/${item.decision_id}`}>{item.decision_id}</Link>
                        {item.status === "REVIEW_PENDING" ? (
                          <>
                            {" "}
                            <Link href={`/review/${item.decision_id}/guided`}>开始复盘</Link>
                          </>
                        ) : null}
                      </>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td className="code">{item.symbol}</td>
                  <td>{item.status}</td>
                  <td className="num">{item.today_execution_count}</td>
                  <td className="num">{money(item.realized_pnl)}</td>
                  <td className="num">{item.process_violation_count}</td>
                  <td>{item.coverage}</td>
                  <td>{item.review_reason.join("、")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </>
  );
}
