"use client";

export interface TooltipItem {
  name?: string | number;
  value?: number | string | Array<number | string>;
  color?: string;
  dataKey?: string | number;
}

export interface ChartTooltipProps {
  active?: boolean;
  payload?: TooltipItem[];
  label?: string | number;
  format: (v: number) => string;
  labelFormat?: (l: string) => string;
  total?: boolean;
  /** Series order for display; Recharts stacks report bottom-up. */
  order?: string[];
}

export function ChartTooltip({ active, payload, label, format, labelFormat, total, order }: ChartTooltipProps) {
  if (!active || !payload?.length) return null;
  const items = payload.filter((p) => typeof p.value === "number");
  if (order) items.sort((a, b) => order.indexOf(String(a.dataKey)) - order.indexOf(String(b.dataKey)));
  const sum = items.reduce((s, p) => s + (p.value as number), 0);
  return (
    <div className="rounded-[8px] border border-hairline bg-panel px-3 py-2 text-xs shadow-[0_8px_24px_-8px_rgba(0,0,0,0.3)]">
      <div className="mb-1 text-secondary">{labelFormat ? labelFormat(String(label)) : String(label)}</div>
      <ul className="space-y-0.5">
        {items.map((p) => (
          <li key={String(p.dataKey)} className="flex items-center justify-between gap-6">
            <span className="inline-flex items-center gap-1.5">
              <span className="inline-block h-2 w-2 rounded-full" style={{ background: p.color }} />
              {String(p.name)}
            </span>
            <span className="tabular-nums">{format(p.value as number)}</span>
          </li>
        ))}
        {total && items.length > 1 ? (
          <li className="mt-1 flex items-center justify-between gap-6 border-t border-hairline pt-1 font-medium">
            <span>Total</span>
            <span className="tabular-nums">{format(sum)}</span>
          </li>
        ) : null}
      </ul>
    </div>
  );
}
