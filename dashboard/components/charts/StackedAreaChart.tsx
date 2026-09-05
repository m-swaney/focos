"use client";

import type { CSSProperties } from "react";
import { Area, AreaChart, CartesianGrid, Tooltip, XAxis, YAxis } from "recharts";
import { ChartTooltip } from "@/components/charts/ChartTooltip";
import { dateShort, moneyCompact, money } from "@/lib/format";

export interface ChartSeries {
  key: string;
  label: string;
  /** A CSS variable reference, e.g. var(--series-1). */
  color: string;
}

export type AreaPoint = { date: string } & Record<string, number | string | null>;

/**
 * Height is the desktop height; phones get at most 220px and 3xl screens
 * 20% more, through CSS variables so no media query runs in JS.
 */
export function StackedAreaChart({ data, series, height = 260, stacked = true }: { data: AreaPoint[]; series: ChartSeries[]; height?: number; stacked?: boolean }) {
  const order = series.map((s) => s.key);
  const vars = { "--h": `${height}px`, "--h-sm": `${Math.min(height, 220)}px`, "--h-3xl": `${Math.round(height * 1.2)}px` } as CSSProperties;
  return (
    <div style={vars} className="h-[var(--h-sm)] w-full md:h-[var(--h)] 3xl:h-[var(--h-3xl)]">
      <AreaChart responsive style={{ width: "100%", height: "100%" }} data={data} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
        <CartesianGrid stroke="var(--hairline)" vertical={false} />
        <XAxis dataKey="date" tickFormatter={dateShort} tick={{ fill: "var(--muted)", fontSize: 11 }} tickLine={false} axisLine={false} minTickGap={40} interval="preserveStartEnd" />
        <YAxis tickFormatter={moneyCompact} tick={{ fill: "var(--muted)", fontSize: 11 }} tickLine={false} axisLine={false} width={48} domain={["auto", "auto"]} />
        <Tooltip cursor={{ stroke: "var(--muted)", strokeWidth: 1 }} content={<ChartTooltip format={(v) => money(v)} labelFormat={dateShort} total={stacked} order={order} />} />
        {series.map((s) => (
          <Area
            key={s.key}
            type="linear"
            dataKey={s.key}
            name={s.label}
            stackId={stacked ? "stack" : undefined}
            stroke={s.color}
            strokeWidth={2}
            fill={s.color}
            fillOpacity={0.16}
            connectNulls={false}
            dot={data.length < 3 ? { r: 3, strokeWidth: 0, fill: s.color } : false}
            activeDot={{ r: 4, strokeWidth: 2, stroke: "var(--panel)" }}
            isAnimationActive={false}
          />
        ))}
      </AreaChart>
    </div>
  );
}
