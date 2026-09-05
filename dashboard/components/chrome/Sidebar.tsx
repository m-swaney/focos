import Link from "next/link";
import { NavLinks } from "@/components/chrome/NavLinks";
import { StatusPopover } from "@/components/chrome/StatusPopover";
import { ThemeToggle } from "@/components/chrome/ThemeToggle";
import { Wordmark } from "@/components/chrome/Wordmark";

/** Desktop navigation. Hidden below lg, where the TabBar and MobileHeader take over. */
export function Sidebar() {
  return (
    <aside className="sticky top-0 hidden h-dvh w-[220px] shrink-0 flex-col border-r border-hairline bg-page px-4 py-5 lg:flex">
      <Link href="/" className="mb-6 flex flex-col gap-1">
        {/* Width-driven so the mark spans the sidebar column; the SVG keeps its own aspect. */}
        <Wordmark width={188} className="h-auto w-full text-ink" />
        <span className="whitespace-nowrap text-center text-[10px] font-medium tracking-[0.02em] text-muted">Family Office Chief of Staff</span>
      </Link>
      <NavLinks />
      <div className="mt-auto space-y-3 px-1">
        <div className="flex gap-3 text-[11px] text-muted">
          <Link href="/setup" className="hover:text-ink">Setup</Link>
          <Link href="/health" className="hover:text-ink">Health</Link>
        </div>
        <StatusPopover id="focos-status" />
        <ThemeToggle />
      </div>
    </aside>
  );
}
