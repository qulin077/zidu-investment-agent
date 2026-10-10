"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, type MemoryPatternDetail, type MemoryRule } from "@/lib/api";

export default function PatternDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const [id, setId] = useState("");
  const [data, setData] = useState<MemoryPatternDetail | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [custom, setCustom] = useState("");
  const [proposed, setProposed] = useState<MemoryRule[]>([]);

  useEffect(() => {
    void params.then((p) => setId(p.id));
  }, [params]);

  async function load(pid: string) {
    setBusy(true);
    try {
      setData(await api.memoryPattern(pid));
      setError("");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    if (id) void load(id);
  }, [id]);

  async function run(fn: () => Promise<unknown>) {
    setBusy(true);
    try {
      await fn();
      if (id) await load(id);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const pattern = data?.pattern;
  const n = pattern?.occurrence_count || 0;

  return (
    <>
      <section>
        <h2>{pattern?.pattern_key || id}</h2>
        <p className="section-note">
          出现 {n} 次 · {pattern?.status}。下面是结构化证据，不是“你经常 FOMO”。
        </p>
        <p>
          <Link href="/review/patterns">← Patterns</Link>
        </p>
        {error ? <p className="warn-line">{error}</p> : null}
        {pattern?.summary ? <p>{pattern.summary}</p> : null}
        <div className="claim-actions">
          {pattern?.status === "CANDIDATE" ? (
            <>
              <button type="button" disabled={busy} onClick={() => run(() => api.confirmPattern(id))}>
                确认是同一模式
              </button>
              <button type="button" className="ghost" disabled={busy} onClick={() => run(() => api.dismissPattern(id))}>
                不是同一模式
              </button>
            </>
          ) : null}
          {pattern?.status === "CONFIRMED" ? (
            <button
              type="button"
              disabled={busy}
              onClick={() =>
                run(async () => {
                  const rows = await api.proposeRules({ pattern_id: id });
                  setProposed(rows.rows || []);
                })
              }
            >
              生成规则候选
            </button>
          ) : null}
        </div>
      </section>

      <section>
        <h2>证据</h2>
        {(data?.evidence || []).map((card) => (
          <div key={card.decision_id} className="claim-card">
            <p>
              <Link href={`/review/${card.decision_id}`}>{card.decision_id}</Link>
              {" · "}
              {card.quadrant} · {card.attribution || "—"}
            </p>
            <div className="fact-grid">
              <div>
                <h3>当时计划</h3>
                <p>仓位 {String(card.plan.target_size_pct ?? "—")}%</p>
                <p>{String(card.plan.invalidation || "")}</p>
              </div>
              <div>
                <h3>实际执行</h3>
                <p>最高仓位 {String(card.actual.max_size_pct ?? "—")}%</p>
              </div>
              <div>
                <h3>结果</h3>
                <p>{String(card.outcome.realized_pct ?? card.outcome.gross_pnl ?? "—")}</p>
              </div>
              <div>
                <h3>违规 / 归因 / Lesson</h3>
                <p>{(card.violations || []).join("、") || "无"}</p>
                <p>{card.attribution || "—"}</p>
                <p>{card.lesson || "—"}</p>
              </div>
            </div>
          </div>
        ))}
      </section>

      {pattern?.status === "CONFIRMED" ? (
        <section>
          <h2>是否为这个模式建立规则？</h2>
          {(proposed.length ? proposed : data?.rules || []).map((rule) => (
            <div key={rule.id} className="claim-card">
              <p>{rule.rule_text}</p>
              <p className="muted">
                WHEN {rule.trigger_text || "—"} · DO {rule.expected_behavior || "—"} · {rule.status}
              </p>
              {rule.status === "PROPOSED" ? (
                <div className="claim-actions">
                  <button type="button" disabled={busy} onClick={() => run(() => api.activateRule(rule.id))}>
                    选择并激活
                  </button>
                  <button type="button" className="ghost" disabled={busy} onClick={() => run(() => api.rejectRule(rule.id))}>
                    不建立
                  </button>
                </div>
              ) : null}
            </div>
          ))}
          <div className="claim-actions">
            <input
              value={custom}
              onChange={(e) => setCustom(e.target.value)}
              placeholder="自己改：必须包含若/则或不得，不能写冷静一点"
            />
            <button
              type="button"
              disabled={busy || !custom.trim()}
              onClick={() =>
                run(async () => {
                  const rows = await api.proposeRules({
                    pattern_id: id,
                    rule_text: custom,
                    trigger_text: "用户自定义条件",
                    expected_behavior: custom,
                  });
                  setProposed(rows.rows || []);
                  setCustom("");
                })
              }
            >
              用自己的表述提出
            </button>
          </div>
        </section>
      ) : null}
    </>
  );
}
