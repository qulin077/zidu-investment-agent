"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { api, type RecorderParseResult, type RecorderQuoted } from "@/lib/api";

function show(item: RecorderQuoted | undefined) {
  if (!item || item.value === null || item.value === undefined || item.value === "") return "—";
  return String(item.value);
}

export default function RecorderNewPage() {
  const [text, setText] = useState("");
  const [symbol, setSymbol] = useState("");
  const [mode, setMode] = useState("premarket");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [parsed, setParsed] = useState<RecorderParseResult | null>(null);
  const [edits, setEdits] = useState<Record<string, string>>({});
  const [created, setCreated] = useState<Record<string, unknown> | null>(null);

  async function onParse(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setCreated(null);
    try {
      const result = await api.recorderParse({
        raw_text: text,
        known_symbol: symbol,
        mode,
      });
      setParsed(result);
      setEdits({});
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function onConfirm() {
    if (!parsed) return;
    setBusy(true);
    setError("");
    try {
      const clean: Record<string, unknown> = {};
      for (const [key, value] of Object.entries(edits)) {
        if (value.trim()) clean[key] = value;
      }
      const result = await api.recorderConfirm({
        draft_id: parsed.draft_id,
        confirmed: true,
        edits: clean,
      });
      setCreated(result);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function onCancel() {
    if (!parsed) return;
    setBusy(true);
    try {
      await api.recorderReject({ draft_id: parsed.draft_id });
      setParsed(null);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const draft = parsed?.draft;

  return (
    <>
      <section>
        <h2>记录一个想法</h2>
        <p className="section-note">
          Recorder 只抽取你说出来的话，不补止损、不荐股。确认前不会写入 Decision。
        </p>
        <p>
          <Link href="/review">← 今日复盘</Link>
        </p>
        <form onSubmit={onParse}>
          <textarea
            className="recorder-text"
            rows={6}
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="例如：特变如果回踩31.8附近不破我想买一点，跌破30这逻辑就算错了，先上10%仓看看。"
          />
          <div className="review-toolbar">
            <label>
              已选标的（可选）
              <input value={symbol} onChange={(e) => setSymbol(e.target.value)} placeholder="600089" />
            </label>
            <label>
              模式
              <select value={mode} onChange={(e) => setMode(e.target.value)}>
                <option value="premarket">盘前</option>
                <option value="intraday">盘中</option>
                <option value="posthoc">事后补录</option>
              </select>
            </label>
            <button type="submit" disabled={busy || !text.trim()}>
              解析
            </button>
          </div>
        </form>
        {error ? <p className="warn-line">{error}</p> : null}
      </section>

      {draft ? (
        <section>
          <h2>你刚才表达的是</h2>
          <p className="section-note">
            intent {draft.intent} · 见证 {parsed?.witnessed_at} · origin {parsed?.origin} · {parsed?.status}
          </p>
          <div className="claim-card">
            <p><b>标的</b> {show(draft.symbol)}</p>
            <p><b>投资逻辑</b> {show(draft.thesis)}</p>
            <p><b>预期</b> {draft.expectations[0]?.raw_text || "—"}</p>
            <p><b>入场条件</b> {show(draft.plan.entry_rule)}</p>
            <p><b>失效条件</b> {show(draft.plan.invalidation)}</p>
            <p><b>目标仓位</b> {show(draft.plan.target_size_pct)}</p>
            <p><b>持有周期</b> {show(draft.plan.holding_period)}</p>
            <p><b>市场语境</b> {show(draft.market_context)}</p>
            {draft.missing_fields.length ? (
              <p className="warn-line">仍缺：{draft.missing_fields.join("、")}</p>
            ) : null}
            {draft.ambiguities.length ? (
              <p className="muted">{draft.ambiguities.join("；")}</p>
            ) : null}
            {parsed?.ask ? <p>{parsed.ask}</p> : null}
            {parsed?.error ? <p className="warn-line">{parsed.error}</p> : null}
          </div>
          {draft.intent === "CREATE_DECISION" || draft.intent === "UPDATE_DRAFT" ? (
            <>
              <p className="section-note">需要改再写，不改直接确认。系统不会替你补数字。</p>
              <div className="claim-actions">
                <input
                  placeholder="修改 thesis"
                  value={edits.thesis || ""}
                  onChange={(e) => setEdits({ ...edits, thesis: e.target.value })}
                />
                <input
                  placeholder="修改失效条件"
                  value={edits.invalidation || ""}
                  onChange={(e) => setEdits({ ...edits, invalidation: e.target.value })}
                />
              </div>
              <div className="claim-actions">
                <button type="button" disabled={busy || parsed?.status === "FAILED"} onClick={onConfirm}>
                  确认创建
                </button>
                <button type="button" className="ghost" disabled={busy} onClick={onCancel}>
                  取消
                </button>
              </div>
            </>
          ) : (
            <p className="muted">闲聊或荐股请求不会创建 Decision。</p>
          )}
        </section>
      ) : null}

      {created ? (
        <section>
          <h2>已写入</h2>
          <p>
            {String(created.decision_id || "—")} · {String(created.status)} · origin {String(created.origin)}
          </p>
          {Array.isArray(created.reminders) && created.reminders.length ? (
            <div className="claim-card">
              <p className="section-note">相关规则提醒（不改仓位 / 不改计划）</p>
              {(created.reminders as Array<Record<string, unknown>>).map((item) => (
                <div key={String(item.id)}>
                  <p>{String(item.why || item.rule_text || "")}</p>
                  <p className="muted">
                    证据 {(item.evidence_decision_ids as string[] | undefined)?.join(" / ") || "—"}
                  </p>
                  {created.decision_id && item.id ? (
                    <div className="claim-actions">
                      <button
                        type="button"
                        className="ghost"
                        onClick={() =>
                          api.reminderFeedback(String(item.id), "RELEVANT").catch((err) => setError(err.message))
                        }
                      >
                        相关
                      </button>
                      <button
                        type="button"
                        className="ghost"
                        onClick={() =>
                          api.reminderFeedback(String(item.id), "NOT_RELEVANT").catch((err) => setError(err.message))
                        }
                      >
                        不相关
                      </button>
                    </div>
                  ) : null}
                </div>
              ))}
            </div>
          ) : null}
          {created.decision_id ? (
            <Link href={`/review/${created.decision_id}`}>查看 Decision</Link>
          ) : null}
        </section>
      ) : null}
    </>
  );
}
