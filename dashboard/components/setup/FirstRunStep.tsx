"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { Msg, StepFrame, btnCls } from "@/components/setup/StepFrame";

type Run = { id: string; finished: string | null; ok?: boolean; stages?: Record<string, string>; error?: string; log?: string[]; status?: { report_path?: string; summary_line?: string } };

export function FirstRunStep() {
  const [run, setRun] = useState<Run | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ kind: "info" | "ok" | "warn" | "bad"; text: string } | null>(null);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => () => { if (timer.current) clearInterval(timer.current); }, []);

  const start = async () => {
    setBusy(true); setMsg(null);
    const r = await api("/run", { body: { mode: "daily" } });
    if (r.error) { setBusy(false); setMsg({ kind: "bad", text: r.error }); return; }
    setRun({ id: r.id, finished: null });
    timer.current = setInterval(async () => {
      const g = await api<Run>(`/run/${r.id}`);
      if (g.error) return;
      setRun(g);
      if (g.finished) {
        if (timer.current) clearInterval(timer.current);
        setBusy(false);
        if (g.ok) {
          await api("/setup/complete", { body: {} });
          setMsg({ kind: "ok", text: "Done. Your first brief is ready." });
        } else {
          setMsg({ kind: "bad", text: `The run failed: ${g.error ?? Object.values(g.stages ?? {}).find((s) => s.startsWith("failed")) ?? "see log"}` });
        }
      }
    }, 2000);
  };
  const report = run?.status?.report_path;
  const reportHref = report ? `/briefs/${report.replace(/^reports\//, "").replace(/\.md$/, "")}` : null;

  return (
    <StepFrame href="/setup/first-run" title="Run it once" nextLabel="Go to Today"
      intro="This captures holdings, pulls the ledger, runs the analytics, and asks the AI for a first daily brief. It takes a minute or two.">
      <div className="flex flex-wrap items-center gap-3">
        <button type="button" className={btnCls} disabled={busy} onClick={start}>{busy ? "Running…" : "Run the daily brief now"}</button>
        {run?.stages ? <span className="text-[12px] text-muted">{Object.entries(run.stages).map(([k, v]) => `${k}: ${v}`).join(" · ")}</span> : null}
      </div>
      {run?.log?.length ? (
        <pre className="mt-3 max-h-[260px] overflow-auto rounded-[6px] bg-panel-2 p-3 text-[11px] leading-relaxed text-secondary">{run.log.join("\n")}</pre>
      ) : null}
      {msg ? <Msg kind={msg.kind}>{msg.text}</Msg> : null}
      {run?.finished && run.ok ? (
        <div className="mt-3 flex flex-wrap gap-2 text-[13px]">
          {reportHref ? <Link href={reportHref} className={btnCls}>Read the brief</Link> : null}
          <Link href="/" className={btnCls}>Open Today</Link>
          <Link href="/health" className="text-secondary underline">Health page</Link>
        </div>
      ) : null}
    </StepFrame>
  );
}
