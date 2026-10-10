import type { Metadata } from "next";
import Link from "next/link";
import { MainNavigation } from "@/components/MainNavigation";
import "./globals.css";

export const metadata: Metadata = {
  title: "自渡 ThesisLoop",
  description: "把投资研究、决策和复盘连接成可持续更新的个人证据链。研究用途，非投资建议。",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-CN">
      <body>
        <div className="shell">
          <header className="topbar">
            <Link href="/agent" className="brand">自渡 <span>ThesisLoop</span></Link>
            <MainNavigation />
            <span className="spacer" />
            <span className="disclaimer">研究框架，非投资建议</span>
          </header>
          {children}
        </div>
      </body>
    </html>
  );
}
