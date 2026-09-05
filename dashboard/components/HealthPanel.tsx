"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Icon } from "@/components/ui/Icon";
import { btnCls, btnQuietCls } from "@/components/setup/StepFrame";

type Check = { id: string; ok: boolean | null; severity: string; title: string; detail: string; fix: string; fix_action: string | null };

const TONE: Record<string, string> = { ok: "text-gain", warn: "text-warn", error: "text-critical", info: "text-muted" };

export function HealthPanel() {
  const [checks, setChecks] = useState<Check[] | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const load = () => api<{ checks: Check[] }>("/doctor").then((r) => { if (r.error) setErr(r.error); else setChecks(r.checks); });
  useEffect(() => { load(); }, []);

  const fix = async (id: string) => {
    setBusy(id);
    const r = await api(`/doctor/fix/${id}`, { body: {} });
    setBusy(null);
    setNote(r.ok ? "Applied." : `Not applied: ${r.error ?? "see details"}`);
    load();
  };
  const exportZip = async () => {
    setBusy("export");
    const r = await api("/doctor/diagnostics", { body: {} });
    setBusy(null);
    setNote(r.path ? `Diagnostics written to ${r.path}. Names, secrets, account numbers, and amounts are redacted; send that file when asking for help.` : (r.error ?? "failed"));
  };
  if (err) return <div className="text-[13px] text-critical">{err}</div>;
  if (!checks) return <div className="text-[13px] text-muted">Checking…</div>;
  const problems = checks.filter((c) => c.ok === false);
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2 text-[12px]">
        <span className={problems.length ? "text-warn" : "text-gain"}>{problems.length ? `${problems.length} item(s) need attention` : "Everything looks fine"}</span>
        <button type="button" className={btnQuietCls} onClick={load}>Re-check</button>
        <button type="button" className={btnQuietCls} disabled={busy === "export"} onClick={exportZip}>Export diagnostics for support</button>
      </div>
      {note ? <div className="rounded-[6px] bg-panel-2 px-3 py-2 text-[12px] text-secondary">{note}</div> : null}
      <ul className="divide-y divide-hairline rounded-[6px] border border-hairline">
        {checks.map((c) => {
          const tone = c.ok === false ? (c.severity === "error" ? "error" : "warn") : c.ok ? "ok" : "info";
          return (
            <li key={c.id} className="flex flex-wrap items-start gap-3 px-3 py-2 text-[13px]">
              <span className={`mt-0.5 ${TONE[tone]}`}><Icon name={tone === "ok" ? "check" : tone === "error" ? "critical" : tone === "warn" ? "warn" : "info"} size={14} /></span>
              <span className="min-w-[200px] flex-1">
                <span className="text-ink">{c.title}</span>
                <span className="block text-[12px] text-muted">{c.detail}</span>
                {c.ok === false && c.fix ? <span className="block text-[12px] text-secondary">Fix: {c.fix}</span> : null}
              </span>
              {c.ok === false && c.fix_action ? (
                <button type="button" className={btnCls} disabled={busy === c.fix_action} onClick={() => fix(c.fix_action!)}>Try the fix</button>
              ) : null}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
