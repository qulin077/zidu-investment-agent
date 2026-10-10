"use client";

import { useState } from "react";
import { api, type ResearchUpdateCandidate } from "@/lib/api";

const TARGET_LABEL: Record<ResearchUpdateCandidate["target_type"], string> = {
  company: "公司档案",
  industry: "行业跟踪",
  event: "事件主题",
  new_event: "新事件候选",
};

export function ResearchUpdateInbox({
  initialRows,
  initialCount,
}: {
  initialRows: ResearchUpdateCandidate[];
  initialCount: number;
}) {
  const [rows, setRows] = useState(initialRows);
  const [count, setCount] = useState(initialCount);
  const [busy, setBusy] = useState("");
  const [message, setMessage] = useState("");

  async function refresh() {
    const data = await api.researchUpdateCandidates();
    setRows(data.rows);
    setCount(data.pending_count);
  }

  async function scan() {
    setBusy("scan");
    setMessage("");
    try {
      const result = await api.researchUpdateScan();
      await refresh();
      setMessage(`已扫描今日新闻，新增 ${result.created} 条候选。`);
    } catch (error) {
      setMessage((error as Error).message);
    } finally {
      setBusy("");
    }
  }

  async function accept(row: ResearchUpdateCandidate) {
    setBusy(row.id);
    setMessage("");
    try {
      const result = await api.researchUpdateAccept(row.id);
      window.location.href = `/research?session=${encodeURIComponent(result.session_id)}`;
    } catch (error) {
      setMessage((error as Error).message);
      setBusy("");
    }
  }

  async function dismiss(row: ResearchUpdateCandidate) {
    setBusy(row.id);
    setMessage("");
    try {
      await api.researchUpdateDismiss(row.id);
      await refresh();
    } catch (error) {
      setMessage((error as Error).message);
    } finally {
      setBusy("");
    }
  }

  return (
    <div className="research-update-inbox">
      <div className="research-update-toolbar">
        <div>
          <strong>{count} 条待核验</strong>
          <span>新闻只是候选；确认后 Agent 才会读原文、补搜并回写档案。</span>
        </div>
        <button type="button" onClick={scan} disabled={Boolean(busy)}>
          {busy === "scan" ? "扫描中…" : "扫描今日新闻"}
        </button>
      </div>
      {message ? <p className="research-update-message">{message}</p> : null}
      {rows.length ? (
        <div className="research-update-grid">
          {rows.map((row) => (
            <article className="research-update-card" key={row.id}>
              <div className="research-update-meta">
                <span className={`importance ${row.importance.toLowerCase()}`}>{row.importance}</span>
                <span>{TARGET_LABEL[row.target_type]} · {row.target_name || "待命名"}</span>
                <time>{row.published_at.slice(0, 16)}</time>
              </div>
              <h3>{row.news_title}</h3>
              <p>{row.match_reason}</p>
              <div className="research-update-source">{row.news_source || "来源未知"}</div>
              <div className="research-update-actions">
                <button type="button" onClick={() => accept(row)} disabled={Boolean(busy)}>
                  {busy === row.id ? "启动中…" : "核验并回写"}
                </button>
                <button className="ghost" type="button" onClick={() => dismiss(row)} disabled={Boolean(busy)}>
                  忽略
                </button>
                {row.news_url ? <a href={row.news_url} target="_blank" rel="noreferrer">先看原文 ↗</a> : null}
              </div>
            </article>
          ))}
        </div>
      ) : (
        <p className="section-note">暂无待核验变化。可以手动扫描，完整日更也会自动生成候选。</p>
      )}
    </div>
  );
}
