import path from "node:path";
import { STATE } from "@/lib/data/paths";
import { readJsonl } from "@/lib/data/read";
import type { ChangeRecord, InboxNote } from "@/lib/types";

/** state/changes.jsonl, newest first. */
export const recentChanges = (limit = 30): ChangeRecord[] => readJsonl<ChangeRecord>(path.join(STATE, "changes.jsonl")).slice(-limit).reverse();

/** state/inbox.jsonl, newest first. */
export const inboxNotes = (limit = 50): InboxNote[] => readJsonl<InboxNote>(path.join(STATE, "inbox.jsonl")).slice(-limit).reverse();

const MAX_SHOWINGS = 4;

export const pendingNotes = (): InboxNote[] => inboxNotes(500).filter((n) => n.status === "pending");
export const unaddressedNotes = (): InboxNote[] => inboxNotes(500).filter((n) => n.status === "consumed" && (n.consumed_count ?? 0) >= MAX_SHOWINGS);

/** One line for a change record: "goal heloc_payoff: status active -> done". Mirrors focos.updates.apply.describe. */
export function describeChange(c: ChangeRecord): string {
  const head = `${c.target}${c.id ? ` ${c.id}` : ""}`;
  if (!c.ok) return `${head}: not applied (${c.error ?? "unknown error"})`;
  const before = (c.before ?? {}) as Record<string, unknown>;
  const after = (c.after ?? {}) as Record<string, unknown>;
  const parts: string[] = [];
  for (const [k, v] of Object.entries(after)) {
    if (k === "text") continue;
    const b = before[k];
    parts.push(b != null && b !== "" && b !== v ? `${k} ${String(b)} -> ${String(v)}` : `${k} = ${String(v)}`);
  }
  return `${head}: ${parts.length ? parts.join(", ") : c.op}`;
}

export const ACTOR_LABEL: Record<string, string> = { model: "Chief of staff", user: "You", system: "focos" };
