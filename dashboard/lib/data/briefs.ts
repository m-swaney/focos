import { createHash } from "node:crypto";
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

export const decisionId = (date: string, text: string) => createHash("sha1").update(`${date}|${text}`, "utf8").digest("hex").slice(0, 8);

/** Decisions newest first, each with a stable id and its status from later resolution lines (open when none). */
export function decisions(limit = 50): Decision[] {
  const rows = readJsonl<Decision>(path.join(STATE, "decisions.jsonl")).map((d) =>
    d.kind === "resolution" || d.id ? d : { ...d, id: decisionId(d.date ?? "", d.text ?? "") },
  );
  const status = new Map<string, string>();
  for (const r of rows) if (r.kind === "resolution" && r.ref && r.status) status.set(r.ref, r.status);
  return rows
    .map((d) => (d.kind === "resolution" ? d : { ...d, status: status.get(d.id ?? "") ?? "open" }))
    .slice(-limit)
    .reverse();
}

export const gateLog = (limit = 50): GateEntry[] => readJsonl<GateEntry>(path.join(SANDBOX, "gate_log.jsonl")).slice(-limit).reverse();
