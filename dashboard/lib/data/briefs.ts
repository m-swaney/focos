import fs from "node:fs";
import path from "node:path";
import { REPORTS, SANDBOX, STATE } from "@/lib/data/paths";
import { readJsonl } from "@/lib/data/read";
import type { BriefRef, Decision, GateEntry, Mode } from "@/lib/types";

const KINDS: Mode[] = ["daily", "weekly", "monthly"];

export function briefs(): BriefRef[] {
  const out: BriefRef[] = [];
  for (const kind of KINDS) {
    const dir = path.join(REPORTS, kind);
    if (!fs.existsSync(dir)) continue;
    for (const f of fs.readdirSync(dir)) {
      if (!f.endsWith(".md")) continue;
      const full = path.join(dir, f);
      out.push({ kind, id: f.replace(/\.md$/, ""), file: full, mtime: fs.statSync(full).mtimeMs });
    }
  }
  return out.sort((a, b) => b.id.localeCompare(a.id) || KINDS.indexOf(a.kind) - KINDS.indexOf(b.kind));
}

export const isMode = (s: string): s is Mode => (KINDS as string[]).includes(s);

export function briefText(kind: string, id: string): string | null {
  if (!isMode(kind) || !/^[0-9A-Za-z\-]+$/.test(id)) return null;
  const file = path.join(REPORTS, kind, `${id}.md`);
  return fs.existsSync(file) ? fs.readFileSync(file, "utf-8") : null;
}

/** Body of the first `## ...` heading matching `re` (must carry the `m` flag), or null when absent. */
export function briefSectionMatching(md: string | null, re: RegExp): string | null {
  if (!md) return null;
  const m = re.exec(md);
  if (!m) return null;
  const rest = md.slice(m.index + m[0].length);
  const next = /^##\s+/m.exec(rest);
  return (next ? rest.slice(0, next.index) : rest).trim();
}

/** Body of one `## Heading` section of a brief, or null when absent. */
export function briefSection(md: string | null, heading: string): string | null {
  const re = new RegExp(`^##\\s+${heading.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\s*$`, "m");
  return briefSectionMatching(md, re);
}

export const decisions = (limit = 50): Decision[] => readJsonl<Decision>(path.join(STATE, "decisions.jsonl")).slice(-limit).reverse();

export const gateLog = (limit = 50): GateEntry[] => readJsonl<GateEntry>(path.join(SANDBOX, "gate_log.jsonl")).slice(-limit).reverse();
