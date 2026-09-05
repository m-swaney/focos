import fs from "node:fs";
import { ASSET_NAMES, assetPath, type AssetName } from "@/lib/data/latest";

export const dynamic = "force-dynamic";

const TYPES: Record<AssetName, string> = {
  "correlation.png": "image/png",
  "tearsheet.html": "text/html; charset=utf-8",
};

export async function GET(req: Request) {
  const name = new URL(req.url).searchParams.get("name") || "";
  if (!(ASSET_NAMES as readonly string[]).includes(name)) return new Response("not found", { status: 404 });
  const file = assetPath(name as AssetName);
  if (!file) return new Response("not generated yet (weekly run)", { status: 404 });
  return new Response(fs.readFileSync(file), { headers: { "content-type": TYPES[name as AssetName], "cache-control": "no-store" } });
}
