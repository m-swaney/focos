import Link from "next/link";
import { StatusPopover } from "@/components/chrome/StatusPopover";
import { ThemeToggle } from "@/components/chrome/ThemeToggle";
import { Wordmark } from "@/components/chrome/Wordmark";

/** Compact top row below the lg breakpoint, where the sidebar is hidden. */
export function MobileHeader() {
  return (
    <header className="sticky top-0 z-20 flex items-center justify-between gap-3 border-b border-hairline bg-page px-4 py-2 pt-[calc(0.5rem+env(safe-area-inset-top))] lg:hidden">
      <Link href="/" aria-label="focos, Today">
        <Wordmark height={19} className="text-ink" />
      </Link>
      <div className="flex items-center gap-2">
        <StatusPopover compact id="focos-status-mobile" />
        <ThemeToggle className="w-[88px]" />
      </div>
    </header>
  );
}
