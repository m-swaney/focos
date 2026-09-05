import path from "node:path";
import { DERIVED } from "@/lib/data/paths";
import { listDated, readJson } from "@/lib/data/read";
import { entities } from "@/lib/labels";
import type { AccountKey, Consolidated, EntityKey, SnapshotSummary } from "@/lib/types";

export interface SeriesPoint {
  date: string;
  netWorth: number | null;
  byEntity: Record<EntityKey, number | null>;
  brokerTotal: number | null;
  accounts: Record<AccountKey, number | null>;
}

/** One point per dated derived folder. Early folders may lack the ledger; those fields are null. */
export function series(): { points: SeriesPoint[]; entityKeys: EntityKey[] } {
  const configured = entities().map((e) => e.key);
  const seen = new Set<EntityKey>(configured);
  const points: SeriesPoint[] = [];
  for (const d of listDated()) {
    const dir = path.join(DERIVED, d);
    const snap = readJson<SnapshotSummary>(path.join(dir, "snapshot_summary.json"));
    const cons = readJson<Consolidated>(path.join(dir, "consolidated.json"));
    if (!snap && !cons) continue;
    const byEntity: Record<EntityKey, number | null> = {};
    if (cons?.available && cons.by_entity) {
      for (const [k, v] of Object.entries(cons.by_entity)) {
        byEntity[k] = typeof v.net_worth === "number" ? v.net_worth : null;
        seen.add(k);
      }
    }
    const accounts: Record<AccountKey, number | null> = {};
    for (const a of snap?.accounts ?? []) accounts[a.key] = a.portfolio?.total_value ?? null;
    points.push({
      date: d,
      netWorth: cons?.available && typeof cons.net_worth === "number" ? cons.net_worth : null,
      byEntity,
      brokerTotal: typeof snap?.total_value === "number" ? snap.total_value : null,
      accounts,
    });
  }
  const entityKeys = [...configured, ...[...seen].filter((k) => !configured.includes(k))];
  return { points, entityKeys };
}
