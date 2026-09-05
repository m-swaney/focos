"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { NAV, useActiveSection } from "@/components/chrome/nav";

/** Sidebar navigation. Digits 1 to 6 jump between sections, Omarchy style. */
export function NavLinks() {
  const active = useActiveSection();
  const router = useRouter();

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const t = e.target as HTMLElement | null;
      if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable)) return;
      const i = Number(e.key) - 1;
      if (i >= 0 && i < NAV.length) router.push(NAV[i].href);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [router]);

  return (
    <nav className="flex flex-col gap-0.5" aria-label="Sections">
      {NAV.map((item, i) => {
        const isActive = active === item.href;
        return (
          <Link
            key={item.href}
            href={item.href}
            aria-current={isActive ? "page" : undefined}
            className={`flex items-center gap-3 rounded-[4px] px-2 py-1.5 text-[13px] ${
              isActive ? "bg-panel-2 font-semibold text-ink" : "text-secondary hover:bg-panel-2 hover:text-ink"
            }`}
          >
            <span className={`w-3 text-[11px] ${isActive ? "text-accent" : "text-muted"}`}>{i + 1}</span>
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}
