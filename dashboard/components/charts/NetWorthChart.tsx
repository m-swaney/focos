"use client";

import { useState } from "react";
import { StackedAreaChart, type AreaPoint, type ChartSeries } from "@/components/charts/StackedAreaChart";

const RANGES: { key: string; days: number | null }[] = [
  { key: "1M", days: 31 },
  { key: "3M", days: 92 },
  { key: "1Y", days: 366 },
  { key: "ALL", days: null },
];

/** Net worth over time with Monarch-style range tabs. */
export function NetWorthChart({ data, series, stacked, height = 240 }: { data: AreaPoint[]; series: ChartSeries[]; stacked: boolean; height?: number }) {
  const [range, setRange] = useState("ALL");
  const days = RANGES.find((r) => r.key === range)?.days ?? null;
  const last = data.length ? data[data.length - 1].date : null;
  const cutoff = days && last ? new Date(new Date(last + "T12:00:00").getTime() - days * 864e5).toISOString().slice(0, 10) : null;
  const filtered = cutoff ? data.filter((d) => d.date >= cutoff) : data;
  const shown = filtered.length >= 2 ? filtered : data;
  return (
    <div>
      <div className="mb-3 flex items-center justify-between gap-3">
        <div className="text-[11px] text-muted">{shown.length} points</div>
        <div role="tablist" className="inline-flex gap-0.5 rounded-[3px] border border-hairline p-0.5">
          {RANGES.map((r) => (
            <button
              key={r.key}
              role="tab"
              aria-selected={range === r.key}
              type="button"
              onClick={() => setRange(r.key)}
              className={`rounded-[2px] px-2 py-0.5 text-[11px] ${range === r.key ? "bg-panel-2 text-ink" : "text-muted hover:text-ink"}`}
            >
              {r.key}
            </button>
          ))}
        </div>
      </div>
      <StackedAreaChart data={shown} series={series} stacked={stacked} height={height} />
    </div>
  );
}
