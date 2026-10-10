"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

const ALL_ITEMS = [
  { href: "/", label: "市场", matches: (path: string) => path === "/" },
  { href: "/agent", label: "Agent", matches: (path: string) => path === "/agent" || path.startsWith("/agent/") },
  { href: "/research", label: "Research", matches: (path: string) => path === "/research" || path.startsWith("/research/") },
  { href: "/today", label: "Today", matches: (path: string) => path === "/today" || path.startsWith("/today/") },
  {
    href: "/review",
    label: "Review",
    matches: (path: string) =>
      (path === "/review" || path.startsWith("/review/")) &&
      !path.startsWith("/review/patterns") &&
      !path.startsWith("/review/rules"),
  },
  {
    href: "/review/patterns",
    label: "Memory",
    matches: (path: string) => path.startsWith("/review/patterns") || path.startsWith("/review/rules"),
  },
];

const DEMO_MODE = process.env.NEXT_PUBLIC_DEMO_MODE === "1";
const DEMO_HREFS = new Set(["/agent", "/research", "/review"]);
const ITEMS = DEMO_MODE ? ALL_ITEMS.filter((item) => DEMO_HREFS.has(item.href)) : ALL_ITEMS;

export function MainNavigation() {
  const pathname = usePathname();
  const [pendingHref, setPendingHref] = useState("");

  useEffect(() => {
    setPendingHref("");
  }, [pathname]);

  return (
    <nav className="nav" aria-label="主导航">
      {ITEMS.map((item) => {
        const active = item.matches(pathname);
        const pending = pendingHref === item.href && !active;
        return (
          <Link
            key={item.href}
            href={item.href}
            className={[active ? "active" : "", pending ? "pending" : ""].filter(Boolean).join(" ") || undefined}
            aria-current={active ? "page" : undefined}
            aria-busy={pending || undefined}
            onClick={() => {
              if (!active) setPendingHref(item.href);
            }}
          >
            {item.label}
            {pending ? <span className="nav-pending-dot" aria-hidden="true" /> : null}
          </Link>
        );
      })}
    </nav>
  );
}
