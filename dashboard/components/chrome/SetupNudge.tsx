"use client";

import Link from "next/link";
import { useEffect, useState, useSyncExternalStore } from "react";
import { SETUP_CHANGED, api } from "@/lib/api";

const subscribe = () => () => {};
const clientPath = () => window.location.pathname;
const serverPath = () => "";

/**
 * Until the wizard has been completed once, point every page at it (hidden while inside /setup).
 * Reads window.location through useSyncExternalStore rather than navigation hooks, which are unavailable
 * while Next prerenders its built-in error pages from the root layout.
 *
 * `completed` is the timestamp in focos.yml, which only the last wizard step writes. When it is missing we
 * ask the API whether every step is settled anyway, so configuring focos by hand or by CLI also clears the
 * banner, and re-ask after each write so it goes away without a reload.
 */
export function SetupNudge({ completed }: { completed: boolean }) {
  const pathname = useSyncExternalStore(subscribe, clientPath, serverPath);
  const [done, setDone] = useState(completed);
  useEffect(() => {
    if (completed) return;
    let alive = true;
    const read = () =>
      api<{ setup_complete?: boolean }>("/setup/status").then((r) => {
        if (alive && !r.error) setDone(!!r.setup_complete);
      });
    read();
    window.addEventListener(SETUP_CHANGED, read);
    return () => {
      alive = false;
      window.removeEventListener(SETUP_CHANGED, read);
    };
  }, [completed]);
  if (done || pathname === "" || pathname.startsWith("/setup")) return null;
  return (
    <div className="border-b border-hairline bg-wash-warn text-warn">
      <div className="flex w-full max-w-[1900px] flex-wrap items-center gap-x-3 gap-y-1 px-4 py-2 text-xs md:px-6 lg:px-8">
        <span className="font-medium">Setup is not finished.</span>
        <Link href="/setup" className="underline hover:text-ink">Continue setup</Link>
      </div>
    </div>
  );
}
