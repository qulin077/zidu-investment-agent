"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, type MemoryRule } from "@/lib/api";

export default function RulesPage() {
  const [rows, setRows] = useState<MemoryRule[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [reason, setReason] = useState("");

  async function load() {
    try {
      const data = await api.memoryRules();
      setRows(data.rows || []);
      setError("");
    } catch (err) {
      setError((err as Error).message);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function run(fn: () => Promise<unknown>) {
    setBusy(true);
    try {
      await fn();
      await load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <section>
        <h2>Active Rules</h2>
        <p className="section-note">
          只提醒，不改仓位、不取消 Decision、不设止损。RETIRED 不再弹出。
        </p>
        <p>
          <Link href="/review">← 今日复盘</Link>
          {" · "}
          <Link href="/review/patterns">模式</Link>
        </p>
        {error ? <p className="warn-line">{error}</p> : null}
      </section>
      <section>
        {!rows.length ? (
          <p className="muted">还没有规则。先确认 Pattern，再选择一条可执行规则。</p>
        ) : (
          <table className="review-table">
            <thead>
              <tr>
                <th>Rule</th>
                <th>来源 Pattern</th>
                <th>状态</th>
                <th>创建</th>
                <th className="num">违规次数</th>
                <th>最近触发</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id}>
                  <td>
                    {row.rule_text}
                    <div className="muted">{row.id}</div>
                  </td>
                  <td>
                    <Link href={`/review/patterns/${row.pattern_id}`}>{row.pattern_id}</Link>
                  </td>
                  <td>{row.status}</td>
                  <td>{row.created_at}</td>
                  <td className="num">{row.violation_count ?? 0}</td>
                  <td>{row.last_triggered || "—"}</td>
                  <td>
                    {row.status === "ACTIVE" ? (
                      <button
                        type="button"
                        className="ghost"
                        disabled={busy}
                        onClick={() => run(() => api.retireRule(row.id, reason || "用户认为不再适用"))}
                      >
                        停用
                      </button>
                    ) : null}
                    {row.status === "PROPOSED" ? (
                      <button type="button" disabled={busy} onClick={() => run(() => api.activateRule(row.id))}>
                        激活
                      </button>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <div className="claim-actions">
          <input
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="停用原因（可选）"
          />
        </div>
      </section>
    </>
  );
}
