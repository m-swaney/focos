import fs from "node:fs";
import path from "node:path";
import { LATEST, REPORTS } from "@/lib/data/paths";
import { readJson } from "@/lib/data/read";
import type {
  Alerts,
  BriefResult,
  Catalysts,
  Consolidated,
  Diff,
  Drift,
  Entities,
  Optimizer,
  Plan,
  Portfolio,
  Properties,
  Risk,
  Sandbox,
  SnapshotSummary,
  TaxLots,
} from "@/lib/types";

const latest = <T,>(name: string) => readJson<T>(path.join(LATEST, name));

export const portfolio = () => latest<Portfolio>("portfolio.json");
export const consolidated = () => latest<Consolidated>("consolidated.json");
export const diff = () => latest<Diff>("diff.json");
export const drift = () => latest<Drift>("drift.json");
export const entitiesData = () => latest<Entities>("entities.json");
export const optimizer = () => latest<Optimizer>("optimizer.json");
export const plan = () => latest<Plan>("plan.json");
export const properties = () => latest<Properties>("properties.json");
export const risk = () => latest<Risk>("risk.json");
export const sandbox = () => latest<Sandbox>("sandbox.json");
export const snapshotSummary = () => latest<SnapshotSummary>("snapshot_summary.json");
export const taxLots = () => latest<TaxLots>("tax_lots.json");
export const alerts = () => latest<Alerts>("alerts.json");
export const briefResult = () => latest<BriefResult>("brief_result.json");
export const catalysts = () => latest<Catalysts>("catalysts.json");

export const ASSET_NAMES = ["tearsheet.html", "correlation.png"] as const;
export type AssetName = (typeof ASSET_NAMES)[number];

/** Where a weekly artifact lives, if anywhere. Pipeline and CLI write to different places. */
export function assetPath(name: AssetName): string | null {
  const candidates = [path.join(LATEST, name)];
  const tearsheets = path.join(REPORTS, "tearsheets");
  if (fs.existsSync(tearsheets)) {
    const dated = fs
      .readdirSync(tearsheets)
      .filter((d) => fs.statSync(path.join(tearsheets, d)).isDirectory())
      .sort()
      .reverse();
    for (const d of dated) candidates.push(path.join(tearsheets, d, name));
    candidates.push(path.join(tearsheets, name));
  }
  candidates.push(path.join(REPORTS, name));
  return candidates.find((f) => fs.existsSync(f)) ?? null;
}

export const artifacts = () => ({
  tearsheet: assetPath("tearsheet.html") != null,
  heatmap: assetPath("correlation.png") != null,
});
