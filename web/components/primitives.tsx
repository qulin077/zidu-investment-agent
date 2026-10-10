import type { ReactNode } from "react";

export function pct(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${value > 0 ? "+" : ""}${value.toFixed(digits)}%`;
}

export function num(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return value.toLocaleString("zh-CN", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

/** A 股配色：涨红跌绿。 */
export function moveClass(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "muted";
  if (value > 0) return "up";
  if (value < 0) return "down";
  return "muted";
}

export function Section({
  title,
  note,
  children,
}: {
  title: string;
  note?: string;
  children: ReactNode;
}) {
  return (
    <section>
      <h2>{title}</h2>
      {note ? <p className="section-note">{note}</p> : null}
      {children}
    </section>
  );
}

export function Banner({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="banner">
      <div className="t">{title}</div>
      <div className="muted">{children}</div>
    </div>
  );
}

export function ErrorState({ message }: { message: string }) {
  return (
    <Banner title="接口未就绪">
      {message}
      <br />
      先启动后端：<code>python3 -m uvicorn app.api.main:app --port 8787</code>
    </Banner>
  );
}
