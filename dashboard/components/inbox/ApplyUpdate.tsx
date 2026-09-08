"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { btnQuietCls } from "@/components/setup/StepFrame";

/** One button that applies a fixed list of structured updates as the owner and refreshes the page. */
export function ApplyUpdate({ label, updates, className = "" }: { label: string; updates: Record<string, unknown>[]; className?: string }) {
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const router = useRouter();
  return (
    <span className={`inline-flex items-center gap-2 ${className}`}>
      <button
        type="button"
        className={btnQuietCls}
        disabled={busy}
        onClick={async () => {
          setBusy(true);
          setMsg("");
          const r = await api("/updates", { body: { updates } });
          setBusy(false);
          if (r.error || !r.ok) setMsg(r.error ?? r.changes?.[0]?.error ?? "not applied");
          else setMsg("Applied.");
          router.refresh();
        }}
      >
        {label}
      </button>
      {msg ? <span className="text-[11px] text-secondary">{msg}</span> : null}
    </span>
  );
}
