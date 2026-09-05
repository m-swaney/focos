import type { ReactNode } from "react";
import { ShowMore } from "@/components/ui/ShowMore";

export interface HBarRow {
  label: ReactNode;
  sub?: ReactNode;
  /** Displayed value text, already formatted. */
  valueText: string;
  /** 0..1 share used for bar length. */
  share: number;
  color?: string;
}

const COLS = "sm:grid-cols-[minmax(140px,220px)_1fr_72px]";

/**
 * Sorted horizontal bars in one hue, direct-labeled. A `cap` draws a hairline
 * marker at that share so a limit reads on the same scale as the data.
 * On phones each row is label and value on one line, the bar on the next.
 */
export function HBars({ rows, cap, capLabel, limit, moreLabel }: { rows: HBarRow[]; cap?: number; capLabel?: string; limit?: number; moreLabel?: string }) {
  const maxShare = Math.max(cap ?? 0, ...rows.map((r) => r.share), 0.0001);
  const render = (list: HBarRow[]) => (
    <ul className="space-y-2 sm:space-y-1.5">
      {list.map((r, i) => (
        <li key={i} className={`grid grid-cols-[1fr_auto] items-center gap-x-3 gap-y-1 text-[13px] sm:gap-y-0 ${COLS}`}>
          <div className="min-w-0 truncate">
            {r.label}
            {r.sub ? <span className="ml-1.5 text-xs text-muted">{r.sub}</span> : null}
          </div>
          <div className="relative order-last col-span-2 h-2 rounded-[1px] bg-panel-2 sm:order-none sm:col-span-1">
            <div className="h-full rounded-[1px]" style={{ width: `${(r.share / maxShare) * 100}%`, background: r.color ?? "var(--accent)" }} />
            {cap != null ? <span className="absolute -top-1 h-4 w-px bg-secondary" style={{ left: `${(cap / maxShare) * 100}%` }} aria-hidden="true" /> : null}
          </div>
          <div className="text-right tabular-nums">{r.valueText}</div>
        </li>
      ))}
    </ul>
  );
  const preview = limit ? rows.slice(0, limit) : rows;
  const rest = limit ? rows.slice(limit) : [];
  return (
    <div>
      {cap != null && capLabel ? (
        <div className={`mb-2 grid grid-cols-1 gap-3 text-[11px] text-muted ${COLS}`}>
          <span className="hidden sm:block" />
          <span className="relative h-3">
            <span
              className="absolute whitespace-nowrap"
              style={{ left: `${(cap / maxShare) * 100}%`, transform: cap / maxShare > 0.85 ? "translateX(-100%)" : "translateX(-50%)" }}
            >
              {capLabel}
            </span>
          </span>
          <span className="hidden sm:block" />
        </div>
      ) : null}
      {rest.length ? <ShowMore preview={render(preview)} rest={<div className="mt-1.5">{render(rest)}</div>} moreLabel={moreLabel ?? `Show all ${rows.length}`} /> : render(preview)}
    </div>
  );
}
