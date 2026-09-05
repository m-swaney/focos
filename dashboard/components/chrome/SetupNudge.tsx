"use client";

import Link from "next/link";
import { useSyncExternalStore } from "react";

const subscribe = () => () => {};
const clientPath = () => window.location.pathname;
const serverPath = () => "";

/**
 * Until the wizard has been completed once, point every page at it (hidden while inside /setup).
 * Reads window.location through useSyncExternalStore rather than navigation hooks, which are unavailable
 * while Next prerenders its built-in error pages from the root layout.
 */
export function SetupNudge({ completed }: { completed: boolean }) {
  const pathname = useSyncExternalStore(subscribe, clientPath, serverPath);
  if (completed || pathname === "" || pathname.startsWith("/setup")) return null;
  return (
    <div className="border-b border-hairline bg-wash-warn text-warn">
      <div className="flex w-full max-w-[1900px] flex-wrap items-center gap-x-3 gap-y-1 px-4 py-2 text-xs md:px-6 lg:px-8">
        <span className="font-medium">Setup is not finished.</span>
        <Link href="/setup" className="underline hover:text-ink">Continue setup</Link>
      </div>
    </div>
  );
}
