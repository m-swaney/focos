import { Icon } from "@/components/ui/Icon";
import { StatusMark } from "@/components/ui";
import { intraday } from "@/lib/data/intraday";
import { health } from "@/lib/data/status";
import { ago, dateTime, relTime } from "@/lib/format";

const DOT: Record<string, string> = {
  ok: "bg-gain",
  warn: "bg-warn",
  bad: "bg-critical",
  none: "bg-muted",
};

/**
 * Run health with a native popover holding the system panel.
 * Rendered once in the sidebar and once in the mobile header, so each
 * instance needs its own id.
 */
export function StatusPopover({ id, compact = false }: { id: string; compact?: boolean }) {
  const h = health();
  const intra = intraday();
  const line1 = h.daily ? (h.tone === "bad" ? h.label : "Daily run ok") : "No runs yet";
  const line2 = h.daily ? ago(h.hoursSinceDaily) : "run focos run --mode daily";

  return (
    <>
      {compact ? (
        <button
          type="button"
          popoverTarget={id}
          className="inline-flex items-center gap-1.5 rounded-[4px] border border-hairline px-2 py-1 text-[11px] text-secondary hover:bg-panel-2"
          aria-label="System status"
        >
          <span className={`inline-block h-2 w-2 shrink-0 rounded-full ${DOT[h.tone]}`} aria-hidden="true" />
          {h.daily ? (h.tone === "bad" ? "run failed" : ago(h.hoursSinceDaily)) : "no runs"}
        </button>
      ) : (
        <button
          type="button"
          popoverTarget={id}
          className="flex w-full items-start gap-2 rounded-[4px] border border-hairline px-2.5 py-2 text-left hover:bg-panel-2"
          aria-label="System status"
        >
          <span className={`mt-1.5 inline-block h-2 w-2 shrink-0 rounded-full ${DOT[h.tone]}`} aria-hidden="true" />
          <span className="min-w-0 flex-1">
            <span className="block truncate text-[12px] text-ink">{line1}</span>
            <span className="block truncate text-[11px] text-muted">{line2}</span>
          </span>
          <Icon name="chevron" size={12} className="mt-1 -rotate-90 text-muted" />
        </button>
      )}

      <div
        id={id}
        popover="auto"
        className="fixed inset-x-3 top-[calc(3.25rem+env(safe-area-inset-top))] z-30 max-h-[75dvh] w-auto overflow-y-auto rounded-[4px] border border-hairline bg-panel text-[12px] shadow-[0_16px_48px_-16px_rgba(0,0,0,0.5)] lg:inset-x-auto lg:bottom-4 lg:left-[228px] lg:top-auto lg:max-h-none lg:w-[400px]"
      >
        <div className="flex items-center justify-between border-b border-hairline px-4 py-2.5">
          <span className="label">System</span>
          <span className="text-[11px] text-muted">{h.label}</span>
        </div>
        <div className="p-4">
          {h.detail ? <p className="mb-3 rounded-[4px] bg-wash-critical px-2.5 py-2 text-[11px] text-critical">{h.detail}</p> : null}

          <table className="w-full">
            <thead>
              <tr>
                <th className="label pb-1.5 text-left">Run</th>
                <th className="label pb-1.5 text-left">Status</th>
                <th className="label pb-1.5 text-left">Finished</th>
              </tr>
            </thead>
            <tbody>
              {h.runs.map(({ mode, run }) => (
                <tr key={mode} className="border-t border-hairline">
                  <td className="py-1.5 capitalize">{mode}</td>
                  <td className="py-1.5">{run ? <StatusMark ok={run.ok} /> : <span className="text-muted">never</span>}</td>
                  <td className="py-1.5 text-secondary">{run?.finished ? dateTime(run.finished) : run?.started ? `started ${dateTime(run.started)}` : ""}</td>
                </tr>
              ))}
            </tbody>
          </table>

          {h.daily?.stages ? (
            <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-secondary">
              {(["A", "B", "C"] as const).map((k) => {
                const s = h.daily?.stages?.[k];
                if (!s) return null;
                const name = k === "A" ? "Snapshot" : k === "B" ? "Pipeline" : "Brief";
                return (
                  <span key={k} className="inline-flex items-center gap-1">
                    <StatusMark ok={s.ok} label={name} />
                  </span>
                );
              })}
              {h.daily.commit ? <span className="ml-auto text-muted">{h.daily.commit}</span> : null}
            </div>
          ) : null}

          {h.tokens.length ? (
            <div className="mt-4 border-t border-hairline pt-3">
              <div className="label mb-1.5">Credentials</div>
              <ul className="space-y-1 text-[11px]">
                {h.tokens.map((t) => (
                  <li key={t.label} className="flex justify-between">
                    <span>{t.label}</span>
                    <span className={t.tone === "bad" ? "text-critical" : t.tone === "warn" ? "text-warn" : "text-secondary"}>
                      {t.expires ? (t.hoursLeft != null && t.hoursLeft <= 0 ? "expired" : `expires ${relTime(t.expires)}`) : "unknown"}
                    </span>
                  </li>
                ))}
                {h.keepalive ? (
                  <li className="flex justify-between">
                    <span>Robinhood keep-alive</span>
                    <span className={h.keepalive.tone === "bad" ? "text-critical" : h.keepalive.tone === "warn" ? "text-warn" : "text-secondary"}>
                      {h.keepalive.label}
                      {h.keepalive.when ? ` ${relTime(h.keepalive.when)}` : ""}
                    </span>
                  </li>
                ) : null}
                {h.tokens.some((t) => t.label === "Robinhood access" && t.tone === "bad") ? (
                  <li className="text-[11px] text-muted">
                    Reconnect: run <code className="rounded-[3px] bg-panel-2 px-1 text-ink">focos auth robinhood</code> in a terminal.
                  </li>
                ) : null}
                {h.subscription ? (
                  <li className="flex justify-between text-muted">
                    <span>Claude plan</span>
                    <span>{h.subscription}</span>
                  </li>
                ) : null}
              </ul>
            </div>
          ) : null}

          <div className="mt-4 border-t border-hairline pt-3 text-[11px] text-secondary">
            {intra ? (
              <div className="mb-1.5 flex justify-between">
                <span>Intraday prices</span>
                <span className={intra.stale ? "text-warn" : "text-secondary"}>
                  {intra.available && intra.asof
                    ? `${relTime(intra.asof)}${intra.stale ? ", last good quotes" : ""}`
                    : intra.reason ?? "not available"}
                </span>
              </div>
            ) : null}
            <div className="mb-1.5">
              Manual run <code className="rounded-[3px] bg-panel-2 px-1.5 py-0.5 text-ink">focos run --mode daily</code>
            </div>
            <div className="text-muted">Scheduled runs are managed in Setup → Schedule.</div>
          </div>
        </div>
      </div>
    </>
  );
}
