import fs from "node:fs";
import path from "node:path";
import { NextResponse } from "next/server";
import { REPO_ROOT, envValue } from "@/lib/data/paths";

export const dynamic = "force-dynamic";

const SANDBOX = path.join(REPO_ROOT, "state", "sandbox");

export async function POST(req: Request) {
  const token = envValue("FOCOS_DASH_TOKEN");
  if (!token) return NextResponse.json({ error: "FOCOS_DASH_TOKEN not set in repo .env" }, { status: 500 });
  if (req.headers.get("x-focos-token") !== token) return NextResponse.json({ error: "bad token" }, { status: 401 });
  const body = await req.json().catch(() => ({}));
  const action = String(body.action || "");
  const refId = String(body.ref_id || "");
  fs.mkdirSync(path.join(SANDBOX, "approvals"), { recursive: true });
  if (action === "kill") {
    fs.writeFileSync(path.join(SANDBOX, "KILL"), `killed from dashboard ${new Date().toISOString()}\n`);
    return NextResponse.json({ ok: true, killed: true });
  }
  if (action === "unkill") {
    const f = path.join(SANDBOX, "KILL");
    if (fs.existsSync(f)) fs.unlinkSync(f);
    return NextResponse.json({ ok: true, killed: false });
  }
  if (action === "approve") {
    if (!/^[0-9A-Za-z\-_.]{3,80}$/.test(refId)) return NextResponse.json({ error: "bad ref_id" }, { status: 400 });
    fs.writeFileSync(path.join(SANDBOX, "approvals", `${refId}.approved`), `approved from dashboard ${new Date().toISOString()}\n`);
    return NextResponse.json({ ok: true, approved: refId });
  }
  return NextResponse.json({ error: "unknown action" }, { status: 400 });
}
