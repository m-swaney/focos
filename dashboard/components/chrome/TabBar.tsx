"use client";

import Link from "next/link";
import { NAV, useActiveSection } from "@/components/chrome/nav";
import { Icon } from "@/components/ui/Icon";

/** Phone and tablet navigation: six tabs pinned to the bottom edge. */
export function TabBar() {
  const active = useActiveSection();
  return (
    <nav
      aria-label="Sections"
      className="fixed inset-x-0 bottom-0 z-20 grid grid-cols-6 border-t border-hairline bg-page pb-[env(safe-area-inset-bottom)] lg:hidden"
    >
      {NAV.map((item) => {
        const isActive = active === item.href;
        return (
          <Link
            key={item.href}
            href={item.href}
            aria-current={isActive ? "page" : undefined}
            className={`relative flex h-14 flex-col items-center justify-center gap-1 text-[10px] font-medium ${isActive ? "text-ink" : "text-muted"}`}
          >
            {isActive ? <span className="absolute inset-x-3 top-0 h-0.5 bg-accent" aria-hidden="true" /> : null}
            <Icon name={item.icon} size={18} className={isActive ? "text-accent" : ""} />
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}
