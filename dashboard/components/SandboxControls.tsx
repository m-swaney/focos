"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Icon } from "@/components/ui/Icon";
import { useLocalStorage } from "@/lib/useLocalStorage";

const TOKEN_KEY = "focos_token";

async function call(action: string, ref_id?: string) {
  const token = typeof window !== "undefined" ? window.localStorage.getItem(TOKEN_KEY) || "" : "";
  const r = await fetch("/api/sandbox", {
    method: "POST",
    headers: { "content-type": "application/json", "x-focos-token": token },
    body: JSON.stringify({ action, ref_id }),
  });
  return r.json();
}

export function KillSwitch({ killed }: { killed: boolean }) {
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const router = useRouter();
  return (
    <div className="flex flex-wrap items-center gap-3">
      <button
        type="button"
        disabled={busy}
        onClick={async () => {
          setBusy(true);
          const res = await call(killed ? "unkill" : "kill");
          setMsg(res.error ? `Not applied: ${res.error}` : killed ? "Trading re-enabled." : "Kill switch set. No orders will pass the gate.");
          setBusy(false);
          router.refresh();
        }}
        className={`inline-flex items-center gap-1.5 rounded-[6px] border px-3 py-1.5 text-xs font-medium disabled:opacity-50 ${
          killed ? "border-gain text-gain hover:bg-wash-gain" : "border-critical text-critical hover:bg-wash-critical"
        }`}
      >
        <Icon name={killed ? "check" : "bolt"} size={14} />
        {killed ? "Clear kill switch" : "Kill all trading"}
      </button>
      <TokenUnlock />
      {msg ? <span className="text-xs text-secondary">{msg}</span> : null}
    </div>
  );
}

export function ApproveButton({ refId, approved }: { refId: string; approved: boolean }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const router = useRouter();
  if (approved)
    return (
      <span className="inline-flex items-center gap-1 text-xs font-medium text-gain">
        <Icon name="check" size={14} /> Approved
      </span>
    );
  return (
    <span className="inline-flex items-center gap-2">
      <button
        type="button"
        disabled={busy}
        onClick={async () => {
          setBusy(true);
          const res = await call("approve", refId);
          setErr(res.error ?? "");
          setBusy(false);
          router.refresh();
        }}
        className="rounded-[6px] border border-ink px-2.5 py-1 text-xs font-medium hover:bg-panel-2 disabled:opacity-50"
      >
        Approve
      </button>
      {err ? <span className="text-xs text-critical">{err}</span> : null}
    </span>
  );
}

/** The dashboard token is entered once and kept in this browser. */
function TokenUnlock() {
  const [open, setOpen] = useState(false);
  const [stored, setStored] = useLocalStorage(TOKEN_KEY);
  const v = stored ?? "";
  const has = !!v;
  return (
    <span className="relative inline-flex items-center">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="inline-flex items-center gap-1.5 rounded-[6px] px-2 py-1.5 text-xs text-secondary hover:bg-panel-2 hover:text-ink"
      >
        <Icon name="lock" size={13} />
        {has ? "Token saved" : "Enter token"}
      </button>
      {open ? (
        <span className="absolute right-0 top-full z-10 mt-1 flex items-center gap-2 rounded-[4px] border border-hairline bg-panel p-2 shadow-[0_8px_24px_-8px_rgba(0,0,0,0.3)] sm:left-0 sm:right-auto">
          <input
            type="password"
            autoFocus
            placeholder="FOCOS_DASH_TOKEN"
            value={v}
            onChange={(e) => setStored(e.target.value)}
            className="w-40 rounded-[4px] border border-hairline bg-page px-2 py-1 text-xs sm:w-48"
          />
          <button type="button" onClick={() => setOpen(false)} className="text-xs text-secondary hover:text-ink">
            Done
          </button>
        </span>
      ) : null}
    </span>
  );
}
