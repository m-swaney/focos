import fs from "node:fs";
import os from "node:os";
import path from "node:path";

/** ~/.focos/home.txt, written by `focos init --set-default` / the installer. */
function pointerHome(): string | undefined {
  try {
    const t = fs.readFileSync(path.join(os.homedir(), ".focos", "home.txt"), "utf-8").trim();
    return t && fs.existsSync(t) ? t : undefined;
  } catch {
    return undefined;
  }
}

/** The household data dir. Same resolution order as focos/paths.py. */
export const REPO_ROOT = process.env.FOCOS_HOME || process.env.FOCOS_REPO_ROOT || pointerHome() || path.resolve(process.cwd(), "..");
export const HOME = REPO_ROOT;
export const STATE = path.join(REPO_ROOT, "state");
export const DERIVED = path.join(STATE, "derived");
export const LATEST = path.join(DERIVED, "latest");
export const REPORTS = path.join(REPO_ROOT, "reports");
export const CONFIG = path.join(REPO_ROOT, "config");
export const SANDBOX = path.join(STATE, "sandbox");

export function envValue(key: string): string | undefined {
  if (process.env[key]) return process.env[key];
  try {
    const text = fs.readFileSync(path.join(REPO_ROOT, ".env"), "utf-8");
    const m = text.match(new RegExp(`^${key}=(.*)$`, "m"));
    return m?.[1]?.trim() || undefined;
  } catch {
    return undefined;
  }
}

function apiPort(): number {
  if (process.env.FOCOS_API_PORT) return Number(process.env.FOCOS_API_PORT);
  try {
    const m = fs.readFileSync(path.join(CONFIG, "focos.yml"), "utf-8").match(/api_port:\s*(\d+)/);
    if (m) return Number(m[1]);
  } catch {
    /* defaults */
  }
  return 3101;
}

/** The local focos API (FastAPI, loopback only). */
export const API_BASE = process.env.FOCOS_API_URL || `http://127.0.0.1:${apiPort()}`;

/** True once the setup wizard has been completed (config/focos.yml setup_completed_at). */
export function setupCompleted(): boolean {
  try {
    return /^setup_completed_at:\s*\S/m.test(fs.readFileSync(path.join(CONFIG, "focos.yml"), "utf-8"));
  } catch {
    return false;
  }
}

/** The names focos seeds itself; kept in step with PLACEHOLDER_LABELS in focos/api/routes/setup.py. */
const PLACEHOLDER_LABELS = ["Our household", "Household", "My household"];

/** The household name from config/focos.yml (home_label); undefined when unset or still a seeded placeholder. */
export function homeLabel(): string | undefined {
  try {
    const m = fs.readFileSync(path.join(CONFIG, "focos.yml"), "utf-8").match(/^home_label:\s*(.+)$/m);
    const v = m?.[1]?.trim().replace(/^["']|["']$/g, "");
    return !v || PLACEHOLDER_LABELS.includes(v) ? undefined : v;
  } catch {
    return undefined;
  }
}
