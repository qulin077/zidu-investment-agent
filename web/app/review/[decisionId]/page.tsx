import Link from "next/link";
import { api } from "@/lib/api";
import { ErrorState, Section } from "@/components/primitives";

export const dynamic = "force-dynamic";

function fmt(value: unknown) {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "number") return `${value > 0 ? "+" : ""}${value}`;
  return String(value);
}

function ContextCard({
  payload,
  diff,
}: {
  payload: Record<string, unknown> | undefined;
  diff: { changes?: { field: string; entry: unknown; review: unknown }[]; note?: string } | undefined;
}) {
  const headline = (payload?.headline || {}) as Record<string, unknown>;
  const warning = String(payload?.warning || "");
  return (
    <div className="context-card">
      <h3>当时环境</h3>
      <p className="section-note">ENTRY CONTEXT 是事实快照，不是建议动作。</p>
      {warning ? <p className="warn-line">{warning}</p> : null}
      <div className="health-grid">
        <div>
          <span className="muted">Market Stage</span>
          <strong>{fmt(headline.market_stage)}</strong>
        </div>
        <div>
          <span className="muted">创业板 5d</span>
          <strong>{fmt(headline.chinext_5d)}</strong>
        </div>
        <div>
          <span className="muted">科技 vs 沪深300</span>
          <strong>{fmt(headline.sector_rs)}</strong>
        </div>
        <div>
          <span className="muted">银行 B档</span>
          <strong>{fmt(headline.bank_b)}</strong>
        </div>
        <div>
          <span className="muted">VIX</span>
          <strong>{fmt(headline.vix)}</strong>
        </div>
        <div>
          <span className="muted">SOX 5d</span>
          <strong>{fmt(headline.sox_5d)}</strong>
        </div>
        <div>
          <span className="muted">Coverage</span>
          <strong>{fmt(headline.coverage)}</strong>
        </div>
        <div>
          <span className="muted">Cutoff</span>
          <strong>{fmt(headline.cutoff_at)}</strong>
        </div>
        <div>
          <span className="muted">Policy</span>
          <strong>{fmt(headline.temporal_policy)}</strong>
        </div>
        <div>
          <span className="muted">Temporal coverage</span>
          <strong>{fmt(headline.temporal_coverage)}</strong>
        </div>
        <div>
          <span className="muted">Future rejected</span>
          <strong>{fmt(headline.future_rejected_count)}</strong>
        </div>
        <div>
          <span className="muted">As-of</span>
          <strong>{fmt(headline.as_of)}</strong>
        </div>
      </div>
      {diff?.changes?.length ? (
        <>
          <h3>Entry vs Review</h3>
          <p className="section-note">{diff.note || "环境变化事实。不自动生成归因。"}</p>
          <ul>
            {diff.changes.map((row) => (
              <li key={row.field}>
                {row.field}: {fmt(row.entry)} → {fmt(row.review)}
              </li>
            ))}
          </ul>
        </>
      ) : null}
    </div>
  );
}

export default async function ReviewDecisionPage({
  params,
}: {
  params: Promise<{ decisionId: string }>;
}) {
  const { decisionId } = await params;
  try {
    const data = await api.reviewDecision(decisionId);
    const origin = String(data.decision.origin || "EX_ANTE");
    const status = String(data.decision.status || "");
    return (
      <Section
        title={decisionId}
        note={`${origin} · ${status} · Decision 是意图，下面的成交是事实`}
      >
        <p>
          <Link href="/review">← 今日复盘</Link>
          {status === "REVIEW_PENDING" ? (
            <>
              {" · "}
              <Link href={`/review/${decisionId}/guided`}>开始复盘</Link>
            </>
          ) : null}
        </p>
        <pre className="review-card">{data.card}</pre>
        {data.research_link?.attached ? (
          <p className="section-note">
            Based on: {data.research_link.thesis_id} v{data.research_link.decision_version}
            。复盘时: v{data.research_link.current_version}
            {data.research_link.diff_verdict ? ` · ${data.research_link.diff_verdict}` : ""}
            。是不是 Research Error，由你确认。
          </p>
        ) : null}
        <ContextCard payload={data.context} diff={data.context_diff} />
      </Section>
    );
  } catch (error) {
    return <ErrorState message={(error as Error).message} />;
  }
}
