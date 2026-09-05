import { NextResponse } from "next/server";
import { API_BASE, envValue } from "@/lib/data/paths";

export const dynamic = "force-dynamic";

/** Proxy to the local focos API. The dashboard token is injected here, so the browser never sees it. */
async function handle(req: Request, ctx: { params: Promise<{ path: string[] }> }) {
  const { path } = await ctx.params;
  const url = new URL(req.url);
  const target = `${API_BASE}/${path.join("/")}${url.search}`;
  const body = req.method === "GET" || req.method === "HEAD" ? undefined : await req.text();
  try {
    const r = await fetch(target, {
      method: req.method,
      headers: { "content-type": "application/json", "x-focos-token": envValue("FOCOS_DASH_TOKEN") ?? "" },
      body,
      cache: "no-store",
    });
    const text = await r.text();
    return new NextResponse(text, { status: r.status, headers: { "content-type": r.headers.get("content-type") ?? "application/json" } });
  } catch {
    return NextResponse.json({ error: "The focos local service is not running. Start it with `focos serve` (or `focos service start`)." }, { status: 503 });
  }
}

export { handle as GET, handle as POST, handle as PUT, handle as PATCH, handle as DELETE };
