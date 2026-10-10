"use client";

import { useEffect, useRef, useState } from "react";
import { api, type SessionMessage } from "@/lib/api";

export function ReplayChat() {
  const [messages, setMessages] = useState<SessionMessage[]>([]);
  const [awaiting, setAwaiting] = useState("");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const box = useRef<HTMLDivElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api
      .session()
      .then((session) => {
        setMessages(session.history || []);
        setAwaiting(session.awaiting || "");
      })
      .catch((err) => setError((err as Error).message));
  }, []);

  useEffect(() => {
    box.current?.scrollTo({ top: box.current.scrollHeight });
  }, [messages, busy]);

  async function send(payload: { q?: string; image_base64?: string; mime?: string }) {
    setBusy(true);
    setError("");
    try {
      const packet = await api.dialogueTurn({ persist: true, ...payload });
      setMessages(packet.history || []);
      setAwaiting(packet.next?.slot || "");
      setText("");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    const q = text.trim();
    if (!q || busy) return;
    await send({ q });
  }

  async function onFile(file: File | null) {
    if (!file || busy) return;
    const dataUrl = await new Promise<string>((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result || ""));
      reader.onerror = () => reject(new Error("读图失败"));
      reader.readAsDataURL(file);
    });
    await send({ q: "交割单截图", image_base64: dataUrl, mime: file.type });
  }

  function onPaste(event: React.ClipboardEvent<HTMLTextAreaElement>) {
    const item = [...event.clipboardData.items].find((entry) =>
      entry.type.startsWith("image/"),
    );
    const file = item?.getAsFile();
    if (file) {
      event.preventDefault();
      void onFile(file);
    }
  }

  async function reset() {
    setBusy(true);
    try {
      const session = await api.resetSession();
      setMessages(session.history || []);
      setAwaiting(session.awaiting || "");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section>
      <h2>复盘对话</h2>
      <p className="section-note">
        收盘三步：把交割单截图拖进来或 Ctrl/Cmd+V 粘贴 → 按提示补每笔为什么买/卖和止损 →
        写一句明天可证伪的预期。平时打开只看下面两套账。说「你好」不会入库、也不会跳过。
      </p>
      <div className="chat-log" ref={box}>
        {messages.length === 0 ? (
          <div className="muted">还没有对话。丢截图或说「对账预测」开始。</div>
        ) : (
          messages.map((item, index) => (
            <div
              className={`chat-bubble ${item.role === "user" ? "me" : "bot"}`}
              key={`${item.role}-${index}`}
            >
              <div className="kicker">
                {item.role === "user" ? "你" : "复盘"}
                {item.image ? " · 截图" : ""}
                {item.slot ? ` · ${item.slot}` : ""}
              </div>
              <div className="chat-text">{item.text}</div>
            </div>
          ))
        )}
        {busy ? <div className="muted">在读…</div> : null}
      </div>
      {awaiting ? (
        <p className="section-note">当前在等：{awaiting}。答不上来就说「先看账本」，不要硬编。</p>
      ) : null}
      {error ? <p className="section-note">{error}</p> : null}
      <form className="chat-form" onSubmit={onSubmit}>
        <textarea
          value={text}
          onChange={(event) => setText(event.target.value)}
          onPaste={onPaste}
          placeholder="说话，或直接粘贴交割截图"
          rows={2}
          disabled={busy}
        />
        <div className="chat-actions">
          <input
            ref={fileRef}
            type="file"
            accept="image/*"
            hidden
            onChange={(event) => {
              void onFile(event.target.files?.[0] || null);
              event.target.value = "";
            }}
          />
          <button type="button" onClick={() => fileRef.current?.click()} disabled={busy}>
            交割截图
          </button>
          <button type="submit" disabled={busy}>
            发送
          </button>
          <button type="button" onClick={() => void reset()} disabled={busy}>
            清空会话
          </button>
        </div>
      </form>
    </section>
  );
}
