"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { SETUP_CHANGED } from "@/lib/api";

const EVERY_MS = 60_000;

/**
 * Keeps an open page current. Two triggers: a save through the API (the sidebar and setup banner are
 * server-rendered, so they would otherwise wait for a full page load), and a timer, because the service
 * re-prices holdings every few minutes and a dashboard left open all day should show it.
 *
 * `router.refresh()` re-requests the server tree; every page is force-dynamic over plain file reads, so that
 * picks up whatever is on disk. Hidden tabs are skipped and refreshed once on return, so a background window
 * costs nothing. Renders nothing.
 */
export function AutoRefresh() {
  const router = useRouter();
  useEffect(() => {
    const refresh = () => router.refresh();
    const refreshIfVisible = () => {
      if (document.visibilityState === "visible") router.refresh();
    };
    window.addEventListener(SETUP_CHANGED, refresh);
    document.addEventListener("visibilitychange", refreshIfVisible);
    const timer = window.setInterval(refreshIfVisible, EVERY_MS);
    return () => {
      window.removeEventListener(SETUP_CHANGED, refresh);
      document.removeEventListener("visibilitychange", refreshIfVisible);
      window.clearInterval(timer);
    };
  }, [router]);
  return null;
}
