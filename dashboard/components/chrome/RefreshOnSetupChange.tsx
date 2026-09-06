"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { SETUP_CHANGED } from "@/lib/api";

/**
 * The sidebar and the setup banner are server-rendered, so a write through the API would not reach them
 * until the next full page load. Re-render the server tree whenever something is saved. Renders nothing.
 */
export function RefreshOnSetupChange() {
  const router = useRouter();
  useEffect(() => {
    const refresh = () => router.refresh();
    window.addEventListener(SETUP_CHANGED, refresh);
    return () => window.removeEventListener(SETUP_CHANGED, refresh);
  }, [router]);
  return null;
}
