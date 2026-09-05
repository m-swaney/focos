import fs from "node:fs";
import path from "node:path";
import { parse } from "yaml";
import { CONFIG } from "@/lib/data/paths";
import type { AccountKey, EntityKey } from "@/lib/types";

function readYaml<T>(file: string): T | null {
  try {
    return parse(fs.readFileSync(path.join(CONFIG, file), "utf-8")) as T;
  } catch {
    return null;
  }
}

export interface EntityInfo {
  key: EntityKey;
  label: string;
  short: string;
  /** 1-based series slot, fixed by config order. */
  slot: number;
}

/** A short label for chips: the first two words of the label, or the label when it is already short. */
function shorten(label: string): string {
  if (label.length <= 14) return label;
  const words = label.split(/\s+/);
  const cut = words.slice(0, 2).join(" ");
  return cut.length < label.length ? cut : label;
}

/** Entities in config order. The color slot follows this order and never changes. */
export function entities(): EntityInfo[] {
  const y = readYaml<{ entities?: Record<string, { label?: string; short?: string }> }>("entities.yml");
  const keys = Object.keys(y?.entities ?? {});
  return keys.map((key, i) => {
    const label = y?.entities?.[key]?.label ?? key;
    return { key, label, short: y?.entities?.[key]?.short ?? shorten(label), slot: i + 1 };
  });
}

export function entity(key: EntityKey): EntityInfo {
  return entities().find((e) => e.key === key) ?? { key, label: key, short: key, slot: 0 };
}

export const seriesVar = (slot: number) => (slot > 0 ? `var(--series-${((slot - 1) % 3) + 1})` : "var(--dim)");

export function etfLabels(): Record<string, string> {
  const y = readYaml<{ etf_labels?: Record<string, string> }>("analytics.yml");
  return y?.etf_labels ?? {};
}

export function riskLimits(): { maxSingleStock?: number; maxSector?: number } {
  const y = readYaml<{ risk?: { max_single_stock_weight_pct?: number; max_sector_weight_pct?: number } }>("profile.yml");
  return {
    maxSingleStock: y?.risk?.max_single_stock_weight_pct != null ? y.risk.max_single_stock_weight_pct / 100 : undefined,
    maxSector: y?.risk?.max_sector_weight_pct != null ? y.risk.max_sector_weight_pct / 100 : undefined,
  };
}

/** The household's first name from profile.yml (v2 `owner.name`, v1 `person.name`). */
export function ownerName(): string | null {
  const y = readYaml<{ owner?: { name?: string }; person?: { name?: string } }>("profile.yml");
  return y?.owner?.name ?? y?.person?.name ?? null;
}

export const ROLE_LABELS: Record<string, string> = {
  taxable: "Taxable",
  roth_ira: "Roth IRA",
  traditional_ira: "Traditional IRA",
  "401k": "401(k)",
  hsa: "HSA",
  "529": "529",
  sandbox: "Sandbox",
  other: "Other",
};

interface BrokerageEntry {
  key: string;
  label?: string;
  role?: string;
}

/** Brokerage accounts from accounts.yml; accepts the v1 (`robinhood: {key: {label, role}}`) layout too. */
export function brokerageAccounts(): BrokerageEntry[] {
  const y = readYaml<{
    brokerage?: BrokerageEntry[];
    robinhood?: Record<string, { label?: string; role?: string }>;
  }>("accounts.yml");
  if (y?.brokerage) return y.brokerage;
  return Object.entries(y?.robinhood ?? {}).map(([key, v]) => ({ key, label: v?.label, role: v?.role }));
}

export function accountLabel(key: AccountKey): string {
  const hit = brokerageAccounts().find((a) => a.key === key);
  if (hit?.label) return hit.label;
  return ROLE_LABELS[key] ?? key;
}

export function roleLabel(role: string): string {
  return ROLE_LABELS[role] ?? role;
}
