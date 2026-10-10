"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, type MemoryPattern } from "@/lib/api";

export default function PatternsPage() {
  const [rows, setRows] = useState<MemoryPattern[]>([]);
  const [error, setError] = useState("");

  async function load() {
    try {
      const data = await api.memoryPatterns();
      setRows(data.rows || []);
      setError("");
    } catch (err) {
      setError((err as Error).message);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  return (
    <>
      <section>
        <h2>Mistake Patterns</h2>
        <p className="section-note">
          重复出现的已确认错误。OBSERVED 不提示升级；CANDIDATE 需你确认是不是同一模式。不是人格标签。
        </p>
        <p>
          <Link href="/review">← 今日复盘</Link>
          {" · "}
          <Link href="/review/rules">规则</Link>
        </p>
        {error ? <p className="warn-line">{error}</p> : null}
      </section>
      <section>
        {!rows.length ? (
          <p className="muted">还没有 pattern。REVIEWED 且 primary_error ≠ NONE 才会进入 Mistake Memory。</p>
        ) : (
          <table className="review-table">
            <thead>
              <tr>
                <th>Pattern</th>
                <th>状态</th>
                <th className="num">次数</th>
                <th>最近</th>
                <th className="num">证据</th>
                <th>Active Rule</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id}>
                  <td>
                    <Link href={`/review/patterns/${row.id}`}>{row.pattern_key}</Link>
                    <div className="muted">{row.summary}</div>
                  </td>
                  <td>{row.status}</td>
                  <td className="num">{row.occurrence_count}</td>
                  <td>{row.last_seen_at || "—"}</td>
                  <td className="num">{row.evidence_count ?? row.occurrence_count}</td>
                  <td>{row.active_rule ? "是" : "否"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </>
  );
}
