"use client";

import { Bar, BarChart, CartesianGrid, Tooltip, XAxis, YAxis } from "recharts";
import { ChartTooltip } from "@/components/charts/ChartTooltip";
import type { ChartSeries } from "@/components/charts/StackedAreaChart";
import { moneyCompact, money } from "@/lib/format";

export type BarPoint = { group: string } & Record<string, number | string | null>;

/** Horizontal grouped bars; groups on the Y axis so long names have room. */
export function GroupedBarChart({ data, series, height = 200 }: { data: BarPoint[]; series: ChartSeries[]; height?: number }) {
  const longest = data.reduce((n, d) => Math.max(n, String(d.group).length), 0);
  const axisWidth = Math.min(96, 12 + longest * 7);
  return (
    <div style={{ height }} className="w-full">
      <BarChart responsive style={{ width: "100%", height: "100%" }} data={data} layout="vertical" margin={{ top: 4, right: 16, left: 0, bottom: 0 }} barCategoryGap={12} barGap={2}>
        <CartesianGrid stroke="var(--hairline)" horizontal={false} />
        <XAxis type="number" tickFormatter={moneyCompact} tick={{ fill: "var(--muted)", fontSize: 11 }} tickLine={false} axisLine={false} tickCount={4} />
        <YAxis type="category" dataKey="group" tick={{ fill: "var(--secondary)", fontSize: 11 }} tickLine={false} axisLine={false} width={axisWidth} />
        <Tooltip cursor={{ fill: "var(--panel-2)", opacity: 0.6 }} content={<ChartTooltip format={(v) => money(v)} />} />
        {series.map((s) => (
          <Bar key={s.key} dataKey={s.key} name={s.label} fill={s.color} radius={[0, 2, 2, 0]} maxBarSize={14} isAnimationActive={false} />
        ))}
      </BarChart>
    </div>
  );
}
