"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { api, type ReviewArchive, type ReviewArchiveItem } from "@/lib/api";

const STATUS_LABEL: Record<string, string> = {
  DRAFT: "草稿",
  PLANNED: "已计划",
  ACTIVE: "进行中",
  CLOSED: "已结束",
  REVIEW_PENDING: "待复盘",
  REVIEWED: "已复盘",
  CANCELLED: "已取消",
  EXPIRED: "已过期",
};

function pnl(value: number | null) {
  if (value === null || value === undefined) return "—";
  return `${value > 0 ? "+" : ""}${Number(value).toLocaleString("zh-CN", { maximumFractionDigits: 0 })}`;
}

export function ReviewArchiveClient() {
  const [data, setData] = useState<ReviewArchive | null>(null);
  const [status, setStatus] = useState("");
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      setError("");
      setData(await api.reviewArchive({ status, limit: 500 }));
    } catch (err) {
      setError((err as Error).message);
    }
  }, [status]);

  useEffect(() => { void load(); }, [load]);

  const rows = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return data?.items || [];
    return (data?.items || []).filter((row) =>
      [row.code, row.name, row.thesis, row.id].some((value) => value.toLowerCase().includes(needle))
    );
  }, [data, query]);

  const reviewed = (data?.items || []).filter((row) => row.status === "REVIEWED").length;
  const pending = (data?.items || []).filter((row) => row.status === "REVIEW_PENDING").length;
  const active = (data?.items || []).filter((row) => ["DRAFT", "PLANNED", "ACTIVE"].includes(row.status)).length;

  return (
    <>
      <section>
        <h2>复盘档案</h2>
        <p className="section-note">这里对照事前 Decision、实际执行和事后复盘；Pattern 与 Rule 只有在用户确认后才会沉淀。</p>
        <div className="review-toolbar">
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索公司、代码或 Thesis" />
          <select value={status} onChange={(event) => setStatus(event.target.value)}>
            <option value="">全部状态</option>
            {Object.entries(STATUS_LABEL).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
          <Link href="/review/day">成交核对</Link>
          <Link href="/review/patterns">复盘模式</Link>
          <Link href="/review/rules">规则</Link>
          <Link href="/review/new">记录想法</Link>
        </div>
        {error ? <p className="warn-line">{error}</p> : null}
      </section>

      <section className="today-summary" aria-label="复盘档案摘要">
        <div><span>全部 Decision</span><strong>{data?.total ?? "—"}</strong></div>
        <div><span>进行中</span><strong>{active}</strong></div>
        <div><span>待复盘</span><strong>{pending}</strong></div>
        <div><span>已完成复盘</span><strong>{reviewed}</strong></div>
      </section>

      <section>
        <h2>Decision 时间线</h2>
        {!rows.length ? <p className="muted">没有符合条件的 Decision。</p> : (
          <table className="review-table review-archive-table">
            <thead><tr><th>日期</th><th>公司 / 标的</th><th>状态</th><th>Thesis</th><th>执行</th><th>复盘</th><th className="num">已实现</th></tr></thead>
            <tbody>
              {rows.map((row: ReviewArchiveItem) => (
                <tr key={row.id}>
                  <td>{row.opened_on || "—"}</td>
                  <td><Link href={`/review/${row.id}`}><strong>{row.name || row.code || row.id}</strong></Link><br /><span className="code">{row.code}</span></td>
                  <td><span className={`match-pill match-${row.status}`}>{STATUS_LABEL[row.status] || row.status}</span>{row.origin === "POST_HOC" ? <><br /><small className="muted">事后补录</small></> : null}</td>
                  <td className="review-thesis-cell">{row.thesis || "未记录 Thesis"}</td>
                  <td>{row.execution_count} 笔</td>
                  <td>{row.status === "REVIEW_PENDING" ? <Link href={`/review/${row.id}/guided`}>开始复盘</Link> : `${row.review_count} 次`}</td>
                  <td className="num">{pnl(row.realized_pnl)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </>
  );
}
