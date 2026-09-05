import fs from "node:fs";
import path from "node:path";
import { DERIVED } from "@/lib/data/paths";

/** One read per file per request; the layout and the page share it. */
export function readJson<T>(file: string): T | null {
  try {
    return JSON.parse(fs.readFileSync(file, "utf-8")) as T;
  } catch {
    return null;
  }
}

export function readJsonl<T>(file: string): T[] {
  if (!fs.existsSync(file)) return [];
  return fs
    .readFileSync(file, "utf-8")
    .split(/\r?\n/)
    .filter(Boolean)
    .map((line) => {
      try {
        return JSON.parse(line) as T;
      } catch {
        return null;
      }
    })
    .filter((x): x is T => x != null);
}

/** Dated derived folders, ascending. */
export function listDated(): string[] {
  if (!fs.existsSync(DERIVED)) return [];
  return fs
    .readdirSync(DERIVED)
    .filter((d) => /^\d{4}-\d{2}-\d{2}$/.test(d) && fs.statSync(path.join(DERIVED, d)).isDirectory())
    .sort();
}
