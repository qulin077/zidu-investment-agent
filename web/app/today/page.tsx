"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { api, type TodayWorkbench } from "@/lib/api";

function todayISO() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
}

export default function TodayPage() {
  const [date, setDate] = useState(todayISO());
  const [data, setData] = useState<TodayWorkbench | null>(null);
  const [text, setText] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async (day: string) => {
    setError("");
    try {
      setData(await api.todayWorkbench(day));
    } catch (err) {
      setError((err as Error).message);
    }
  }, []);

  useEffect(() => {
    void load(date);
  }, [date, load]);

  async function onParse(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      await api.recorderParse({ raw_text: text, mode: "premarket" });
      window.location.href = "/review/new";
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const stage = data?.context_now?.market_stage || "—";
  const indices = data?.context_now?.indices || {};

  return (
    <>
      <section>
        <h2>今日</h2>
        <p className="section-note">
          今天的行动入口：处理未完成决策、成交核对、随手记录和规则提醒。历史结果去 Review，市场环境去看板。
        </p>
        <div className="review-toolbar">
          <label>
            日期
            <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
          </label>
          <Link href="/">看板</Link>
          <Link href="/review">复盘档案</Link>
          <Link href="/review/day">成交核对</Link>
          <Link href="/review/new">Recorder</Link>
        </div>
        {error ? <p className="warn-line">{error}</p> : null}
      </section>
      <section className="today-summary" aria-label="今日待办摘要">
        <div><span>进行中 Decision</span><strong>{data?.open_decisions?.length ?? "—"}</strong></div>
        <div><span>待复盘</span><strong>{data?.queue?.length ?? "—"}</strong></div>
        <div><span>待认领成交</span><strong>{data?.claimable?.length ?? "—"}</strong></div>
        <div><span>规则提醒</span><strong>{data?.reminders?.length ?? "—"}</strong></div>
      </section>
      <section>
        <h2>市场环境摘要</h2>
        <p className="section-note">只保留今天行动所需的事实快照。完整数据去 <Link href="/">市场看板</Link>。</p>
        <p>
          Market stage <strong>{String(stage)}</strong>
          {" · "}
          创业板 5d {String((indices.chinext as { ret_5d?: { value?: number } } | undefined)?.ret_5d?.value ?? "—")}
          {" · "}
          沪深300 5d {String((indices.csi300 as { ret_5d?: { value?: number } } | undefined)?.ret_5d?.value ?? "—")}
        </p>
      </section>
      <section>
        <h2>未完成 Decision</h2>
        {!data?.open_decisions?.length ? (
          <p className="muted">没有未完成 Decision。</p>
        ) : (
          <ul>
            {data.open_decisions.map((row) => (
              <li key={String(row.id)}>
                <Link href={`/review/${row.id}`}>{String(row.id)}</Link> {String(row.code)} {String(row.status)}
              </li>
            ))}
          </ul>
        )}
      </section>
      <section>
        <h2>记一个想法</h2>
        <form onSubmit={onParse}>
          <textarea className="recorder-text" rows={4} value={text} onChange={(e) => setText(e.target.value)} />
          <button type="submit" disabled={busy || !text.trim()}>
            打开 Recorder
          </button>
        </form>
      </section>
      <section>
        <h2>Rule reminders</h2>
        <p className="section-note">只提醒，不改仓位、不改止损。每条 Decision 最多 3 条。</p>
        {!data?.reminders?.length ? (
          <p className="muted">没有近期提醒。</p>
        ) : (
          <ul>
            {data.reminders.map((row) => (
              <li key={String(row.id)}>
                {String(row.rule_id || "")} {String(row.why || "").slice(0, 80)}
              </li>
            ))}
          </ul>
        )}
      </section>
      <section>
        <h2>收盘后</h2>
        <p className="muted">今日已导入 {data?.executions?.length || 0} 笔成交，{data?.claimable?.length || 0} 笔待认领。</p>
        <p><Link href="/review/day">进入成交核对 →</Link></p>
      </section>
    </>
  );
}
