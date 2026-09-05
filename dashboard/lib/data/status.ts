import path from "node:path";
import { alerts } from "@/lib/data/latest";
import { STATE } from "@/lib/data/paths";
import { readJson } from "@/lib/data/read";
import type { Mode, RunStatus, Status } from "@/lib/types";

export const status = (): Status => readJson<Status>(path.join(STATE, "status.json")) ?? {};

export type Tone = "ok" | "warn" | "bad" | "none";

export interface TokenHealth {
  label: string;
  expires: string | null;
  hoursLeft: number | null;
  tone: Tone;
}

export interface Health {
  tone: Tone;
  label: string;
  detail?: string;
  daily?: RunStatus;
  hoursSinceDaily: number | null;
  stale: boolean;
  runs: { mode: Mode; run: RunStatus | undefined }[];
  tokens: TokenHealth[];
  subscription?: string | null;
}

const STALE_HOURS = 30;

function tokenHealth(label: string, iso: string | null | undefined, now: number): TokenHealth {
  if (!iso) return { label, expires: null, hoursLeft: null, tone: "none" };
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return { label, expires: null, hoursLeft: null, tone: "none" };
  const hoursLeft = (t - now) / 36e5;
  return { label, expires: iso, hoursLeft, tone: hoursLeft <= 0 ? "bad" : hoursLeft < 48 ? "warn" : "ok" };
}

/** What the header pill and the failure banner need, computed once per request. */
export function health(): Health {
  const st = status();
  const now = Date.now();
  const daily = st.daily;
  const t = daily?.finished || daily?.started;
  const hoursSinceDaily = t ? (now - new Date(t).getTime()) / 36e5 : null;
  const stale = hoursSinceDaily != null && hoursSinceDaily > STALE_HOURS;
  const tk = alerts()?.tokens;
  const tokens: TokenHealth[] = tk
    ? [
        tokenHealth("Robinhood access", tk.robinhood_access_expires, now),
        tokenHealth("Claude login", tk.claude_refresh_expires, now),
      ]
    : [];
  const stageFailed = Object.values(daily?.stages ?? {}).some((s) => s && s.ok === false);
  const loginBad = tokens.find((x) => x.label === "Claude login")?.tone === "bad";

  let tone: Tone = "none";
  let label = "No runs yet";
  let detail: string | undefined;
  if (daily) {
    if (daily.ok === false) {
      tone = "bad";
      label = "Last daily run failed";
      detail = daily.error ?? undefined;
    } else if (stale) {
      tone = "bad";
      label = "Daily run is stale";
    } else if (daily.ok == null) {
      tone = "warn";
      label = "Daily run in progress";
    } else if (stageFailed || loginBad || tokens.some((x) => x.tone === "warn")) {
      tone = "warn";
      label = "Daily run ok, attention needed";
    } else {
      tone = "ok";
      label = "Daily run ok";
    }
  }
  return {
    tone,
    label,
    detail,
    daily,
    hoursSinceDaily,
    stale,
    runs: (["daily", "weekly", "monthly"] as Mode[]).map((mode) => ({ mode, run: st[mode] })),
    tokens,
    subscription: tk?.subscription,
  };
}
