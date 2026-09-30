"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { ApproveButton } from "@/components/SandboxControls";
import { api } from "@/lib/api";
import type { NeedsYouItem } from "@/lib/types";

const quiet =
  "inline-flex items-center rounded-[6px] border border-hairline px-2 py-0.5 text-[11px] text-secondary hover:bg-panel-2 hover:text-ink disabled:opacity-50";
const primary =
  "inline-flex items-center rounded-[6px] border border-ink px-2 py-0.5 text-[11px] font-medium hover:bg-panel-2 disabled:opacity-50";

/**
 * The way out for each item on the Needs you list. Decisions resolve through /updates (logged as the owner);
 * everything else is handled or snoozed through /needs-you, which also stops its phone pushes.
 */
export function ItemActions({ item }: { item: NeedsYouItem }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const router = useRouter();

  const run = async (fn: () => Promise<{ error?: string; ok?: boolean }>) => {
    setBusy(true);
    setErr("");
    const r = await fn();
    setBusy(false);
    if (r.error || r.ok === false) setErr(r.error ?? "not applied");
    router.refresh();
  };
  const resolve = (status: string) =>
    run(() =>
      api("/updates", {
        body: { updates: [{ target: "decision", op: "resolve", id: item.decision_id, set: { status }, reason: "dashboard" }] },
      }),
    );
  const act = (action: string, days = 7) => run(() => api("/needs-you", { body: { id: item.id, action, days } }));

  let buttons: React.ReactNode = null;
  if (item.kind === "approve" && item.ref_id) {
    buttons = <ApproveButton refId={item.ref_id} approved={false} />;
  } else if (item.kind === "decide") {
    buttons = (
      <>
        <button type="button" className={primary} disabled={busy} onClick={() => resolve("acted")} title="I did this">
          Done
        </button>
        <button type="button" className={quiet} disabled={busy} onClick={() => resolve("standing")} title="Leave things as they are and stop raising it">
          Keep as is
        </button>
        <button type="button" className={quiet} disabled={busy} onClick={() => resolve("retired")} title="Not doing this">
          Drop
        </button>
      </>
    );
  } else if (item.kind === "watch") {
    buttons = (
      <button type="button" className={quiet} disabled={busy} onClick={() => act("dismiss")} title="Hide until it gets worse">
        Hide
      </button>
    );
  } else {
    buttons = (
      <>
        <button type="button" className={primary} disabled={busy} onClick={() => act("dismiss")} title="Hide until it gets worse">
          Handled
        </button>
        <button type="button" className={quiet} disabled={busy} onClick={() => act("snooze", 7)}>
          Snooze a week
        </button>
      </>
    );
  }
  return (
    <span className="inline-flex flex-wrap items-center gap-1.5">
      {buttons}
      {err ? <span className="text-[11px] text-critical">{err}</span> : null}
    </span>
  );
}

/** Clear every dismissal and snooze and rebuild the list from scratch. */
export function StartFresh() {
  const [busy, setBusy] = useState(false);
  const router = useRouter();
  return (
    <button
      type="button"
      className="text-[11px] text-muted underline-offset-2 hover:text-ink hover:underline disabled:opacity-50"
      disabled={busy}
      onClick={async () => {
        setBusy(true);
        await api("/needs-you/start-fresh", { body: {} });
        setBusy(false);
        router.refresh();
      }}
    >
      Show hidden items again
    </button>
  );
}
