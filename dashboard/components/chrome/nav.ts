"use client";

import { useSelectedLayoutSegment } from "next/navigation";
import type { IconName } from "@/components/ui/Icon";

export const NAV: readonly { href: string; label: string; icon: IconName }[] = [
  { href: "/", label: "Today", icon: "today" },
  { href: "/wealth", label: "Wealth", icon: "wealth" },
  { href: "/portfolio", label: "Portfolio", icon: "portfolio" },
  { href: "/plan", label: "Plan", icon: "plan" },
  { href: "/sandbox", label: "Sandbox", icon: "sandbox" },
  { href: "/briefs", label: "Briefs", icon: "briefs" },
];

/**
 * Which section is active. Uses the layout segment rather than usePathname,
 * which is not available while Next prerenders its built-in error pages.
 */
export function useActiveSection(): string {
  const segment = useSelectedLayoutSegment();
  return segment == null ? "/" : `/${segment}`;
}
