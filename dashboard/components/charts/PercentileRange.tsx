import type { Percentiles } from "@/lib/types";

/**
 * One horizontal range: p10 to p90 as a light band, p25 to p75 darker, p50 as a
 * tick, and an optional target as a labeled hairline. Coordinates are
 * percentages of the width so text stays true-size at any screen width.
 */
export function PercentileRange({ p, target, format, height = 84 }: { p: Percentiles; target?: number | null; format: (v: number) => string; height?: number }) {
  const pad = 4; // percent
  const lo = 0;
  const hi = Math.max(p.p90, target ?? 0) * 1.06;
  const x = (v: number) => pad + ((v - lo) / (hi - lo)) * (100 - pad * 2);
  const pct = (v: number) => `${x(v).toFixed(2)}%`;
  const w = (a: number, b: number) => `${(x(b) - x(a)).toFixed(2)}%`;
  const bandY = 26;
  const bandH = 14;
  return (
    <svg width="100%" height={height} role="img" aria-label={`Range ${format(p.p10)} to ${format(p.p90)}, median ${format(p.p50)}`} className="block overflow-visible">
      <line x1={`${pad}%`} x2={`${100 - pad}%`} y1={bandY + bandH / 2} y2={bandY + bandH / 2} stroke="var(--hairline)" strokeWidth={1} />
      <rect x={pct(p.p10)} y={bandY} width={w(p.p10, p.p90)} height={bandH} fill="var(--accent)" opacity={0.22} />
      <rect x={pct(p.p25)} y={bandY} width={w(p.p25, p.p75)} height={bandH} fill="var(--accent)" opacity={0.55} />
      <line x1={pct(p.p50)} x2={pct(p.p50)} y1={bandY - 4} y2={bandY + bandH + 4} stroke="var(--ink)" strokeWidth={2} />
      <text x={pct(p.p50)} y={bandY - 9} textAnchor="middle" fontSize={12} fill="var(--ink)" fontWeight={600}>
        {format(p.p50)}
      </text>
      <text x={pct(p.p10)} y={bandY + bandH + 16} textAnchor="start" fontSize={11} fill="var(--muted)">
        {format(p.p10)}
      </text>
      <text x={pct(p.p90)} y={bandY + bandH + 16} textAnchor="end" fontSize={11} fill="var(--muted)">
        {format(p.p90)}
      </text>
      {target != null ? (
        <>
          <line x1={pct(target)} x2={pct(target)} y1={bandY - 18} y2={bandY + bandH + 20} stroke="var(--secondary)" strokeWidth={1} strokeDasharray="3 3" />
          <text x={pct(target)} y={bandY + bandH + 32} textAnchor="middle" fontSize={11} fill="var(--secondary)">
            target {format(target)}
          </text>
        </>
      ) : null}
    </svg>
  );
}
