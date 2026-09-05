"use client";

/** Browser-side helper for the local focos API (through the /api/focos proxy). */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export async function api<T = any>(path: string, init?: { method?: string; body?: unknown }): Promise<T & { error?: string }> {
  const method = init?.method ?? (init?.body !== undefined ? "POST" : "GET");
  const r = await fetch(`/api/focos${path}`, {
    method,
    headers: { "content-type": "application/json" },
    body: init?.body === undefined ? undefined : JSON.stringify(init.body),
    cache: "no-store",
  });
  const data = (await r.json().catch(() => ({}))) as T & { error?: string; detail?: unknown };
  if (!r.ok && !data.error) data.error = typeof data.detail === "string" ? data.detail : `HTTP ${r.status}`;
  return data;
}

export function errorText(e: unknown): string {
  if (!e) return "";
  if (typeof e === "string") return e;
  if (typeof e === "object" && e && "error" in e) return String((e as { error: unknown }).error ?? "");
  return String(e);
}
