"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { btnQuietCls } from "@/components/setup/StepFrame";

type Target = "goal" | "tax_agenda" | "decision";

/**
 * Small status buttons that apply a structured update as the owner (actor=user) and refresh the page.
 * goal: active -> Done / Pause; done|paused -> Reopen. tax_agenda: open -> Done / Drop; else Reopen.
 * decision: open -> Acted on / Retire; resolved -> label only.
 */
export function MarkDone({ target, id, status }: { target: Target; id: string; status?: string | null }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const router = useRouter();

  const apply = async (set: Record<string, string>) => {
    setBusy(true);
    setErr("");
    const upd: Record<string, unknown> = { target, id, set, reason: "dashboard" };
    if (target === "decision") upd.op = "resolve";
    const r = await api("/updates", { body: { updates: [upd] } });
    setBusy(false);
    if (r.error || !r.ok) setErr(r.error ?? r.changes?.[0]?.error ?? "not applied");
    router.refresh();
  };

  const btn = (label: string, set: Record<string, string>, tone = "") => (
    <button type="button" className={`${btnQuietCls} px-2 py-0.5 text-[11px] ${tone}`} disabled={busy} onClick={() => apply(set)}>
      {label}
    </button>
  );

  let buttons: React.ReactNode = null;
  if (target === "goal") {
    buttons =
      !status || status === "active" ? (
        <>
          {btn("Done", { status: "done" }, "text-gain")}
          {btn("Pause", { status: "paused" })}
        </>
      ) : (
        btn("Reopen", { status: "active" })
      );
  } else if (target === "tax_agenda") {
    buttons =
      !status || status === "open" ? (
        <>
          {btn("Done", { status: "done" }, "text-gain")}
          {btn("Drop", { status: "dropped" })}
        </>
      ) : (
        btn("Reopen", { status: "open" })
      );
  } else {
    buttons =
      !status || status === "open" ? (
        <>
          {btn("Acted on", { status: "acted" }, "text-gain")}
          {btn("Retire", { status: "retired" })}
        </>
      ) : (
        <span className="text-[11px] text-muted">{status}</span>
      );
  }

  return (
    <span className="inline-flex flex-wrap items-center gap-1.5">
      {buttons}
      {err ? <span className="text-[11px] text-critical">{err}</span> : null}
    </span>
  );
}
