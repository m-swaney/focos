import path from "node:path";
import { STATE } from "@/lib/data/paths";
import { readJson } from "@/lib/data/read";
import type { Intraday } from "@/lib/types";

/**
 * state/cache/intraday.json, written by the dashboard service every few minutes. It lives under cache/ because
 * it is ephemeral and git ignores that folder, so re-pricing all day does not leave the data dir dirty.
 */
export const intraday = (): Intraday | null => readJson<Intraday>(path.join(STATE, "cache", "intraday.json"));

/** How stale is too stale to show as "current". Quotes are delayed anyway; past this it is just an old number. */
const MAX_AGE_MINUTES = 90;

export interface IntradayView {
  data: Intraday;
  ageMinutes: number;
  /** Fresh enough to headline, and actually newer than the snapshot it re-prices. */
  usable: boolean;
}

export function intradayView(now = Date.now()): IntradayView | null {
  const data = intraday();
  if (!data?.available || !data.asof) return null;
  const t = new Date(data.asof).getTime();
  if (Number.isNaN(t)) return null;
  const ageMinutes = (now - t) / 60000;
  const captured = data.snapshot_captured_at ? new Date(data.snapshot_captured_at).getTime() : 0;
  return { data, ageMinutes, usable: ageMinutes <= MAX_AGE_MINUTES && ageMinutes >= -5 && t >= captured };
}
