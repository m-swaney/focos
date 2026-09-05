import Link from "next/link";
import type { ReactNode } from "react";
import { Icon, type IconName } from "@/components/ui/Icon";
import { entity, seriesVar } from "@/lib/labels";
import type { EntityKey, Severity as SeverityKind } from "@/lib/types";

/** Page title row. Keep `sub` to a few words; it renders as meta on the right. */
export function PageHeader({ title, sub, right }: { title: string; sub?: ReactNode; right?: ReactNode }) {
  return (
    <div className="mb-4 flex flex-col gap-y-0.5 sm:mb-5 sm:flex-row sm:flex-wrap sm:items-baseline sm:justify-between sm:gap-x-6">
      <h1 className="text-[17px] font-semibold tracking-tight sm:text-[18px]">{title}</h1>
      <div className="flex flex-wrap items-baseline gap-x-4 text-[11px] text-muted">
        {sub ? <span>{sub}</span> : null}
        {right}
      </div>
    </div>
  );
}

/**
 * Every module lives in a Card: a bordered panel with a title bar so it is
 * always clear what you are looking at.
 */
export function Card({
  title,
  meta,
  right,
  children,
  className = "",
  padded = true,
  description,
}: {
  title: string;
  meta?: ReactNode;
  right?: ReactNode;
  children: ReactNode;
  className?: string;
  padded?: boolean;
  /** Alias for meta, kept for older call sites. */
  description?: ReactNode;
}) {
  const m = meta ?? description;
  return (
    <section className={`card flex min-w-0 flex-col ${className}`}>
      <header className="flex items-center justify-between gap-3 border-b border-hairline px-4 py-2.5">
        <h2 className="label shrink-0 text-ink">{title}</h2>
        {m || right ? (
          <div className="flex min-w-0 items-center gap-3 text-right text-[11px] text-muted">
            {m ? <span className="min-w-0 md:truncate">{m}</span> : null}
            {right}
          </div>
        ) : null}
      </header>
      <div className={`min-w-0 flex-1 ${padded ? "p-4" : ""}`}>{children}</div>
    </section>
  );
}

export const Section = Card;

export function Panel({ children, className = "", inset = false }: { children: ReactNode; className?: string; inset?: boolean }) {
  return <div className={`card ${inset ? "" : "p-4"} ${className}`}>{children}</div>;
}

const COLS: Record<number, string> = {
  2: "md:grid-cols-2",
  3: "md:grid-cols-3",
  4: "md:grid-cols-4",
  5: "md:grid-cols-5",
  6: "md:grid-cols-6",
};

/**
 * A row of stats separated by hairlines. Two columns on phones, then as many
 * 150px cells as fit. Each cell carries its own top and left border and the
 * outer edge is hidden by the negative margins, so wrapped rows stay ruled.
 */
export function StatRow({ children, className = "", cols }: { children: ReactNode; className?: string; cols?: number }) {
  const md = cols && COLS[cols] ? COLS[cols] : "md:grid-cols-[repeat(auto-fit,minmax(150px,1fr))]";
  return (
    <div className={`overflow-hidden rounded-[4px] ${className}`}>
      <div className={`-ml-px -mt-px grid grid-cols-2 ${md}`}>{children}</div>
    </div>
  );
}

export function Stat({
  label,
  value,
  sub,
  tone = "",
  size = "md",
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  tone?: string;
  size?: "md" | "lg";
}) {
  return (
    <div className="min-w-0 border-l border-t border-hairline px-3 py-3 sm:px-4">
      <div className="label mb-1.5">{label}</div>
      <div className={`truncate font-semibold leading-none ${size === "lg" ? "text-[22px] sm:text-[30px]" : "text-[18px] sm:text-[22px]"} ${tone}`}>{value}</div>
      {sub ? <div className="mt-1.5 text-[11px] leading-snug text-muted">{sub}</div> : null}
    </div>
  );
}

/** Older names, kept so pages read the same. */
export function FigureStrip({ children, className = "", cols }: { children: ReactNode; className?: string; cols?: number }) {
  return (
    <div className={`card overflow-hidden ${className}`}>
      <StatRow cols={cols}>{children}</StatRow>
    </div>
  );
}
export const Figure = Stat;

export function Empty({ children }: { children: ReactNode }) {
  return <p className="py-3 text-[12px] text-muted">{children}</p>;
}

const SEV: Record<SeverityKind, { icon: IconName; cls: string; label: string }> = {
  critical: { icon: "critical", cls: "text-critical", label: "Critical" },
  warn: { icon: "warn", cls: "text-warn", label: "Warn" },
  info: { icon: "info", cls: "text-secondary", label: "Info" },
};

export function Severity({ s, iconOnly = false }: { s: SeverityKind | string; iconOnly?: boolean }) {
  const d = SEV[(s as SeverityKind) in SEV ? (s as SeverityKind) : "info"];
  return (
    <span className={`inline-flex items-center gap-1 text-[11px] font-medium uppercase tracking-wide ${d.cls}`} title={d.label}>
      <Icon name={d.icon} size={13} />
      {iconOnly ? <span className="sr-only">{d.label}</span> : d.label}
    </span>
  );
}

export function StatusMark({ ok, label }: { ok: boolean | null | undefined; label?: string }) {
  const cls = ok === true ? "text-gain" : ok === false ? "text-loss" : "text-warn";
  const icon: IconName = ok === true ? "check" : ok === false ? "x" : "clock";
  return (
    <span className={`inline-flex items-center gap-1 text-[11px] font-medium ${cls}`}>
      <Icon name={icon} size={13} />
      {label ?? (ok === true ? "ok" : ok === false ? "failed" : "running")}
    </span>
  );
}

export function EntityDot({ entityKey, className = "" }: { entityKey: EntityKey; className?: string }) {
  const e = entity(entityKey);
  return <span className={`inline-block h-2 w-2 shrink-0 rounded-[1px] ${className}`} style={{ background: seriesVar(e.slot) }} aria-hidden="true" />;
}

export function EntityTag({ entityKey, short = true }: { entityKey: EntityKey; short?: boolean }) {
  const e = entity(entityKey);
  return (
    <span className="inline-flex items-center gap-1.5 whitespace-nowrap">
      <EntityDot entityKey={entityKey} />
      {short ? e.short : e.label}
    </span>
  );
}

export function Kv({ rows, className = "" }: { rows: { k: ReactNode; v: ReactNode; tone?: string; sub?: ReactNode }[]; className?: string }) {
  return (
    <dl className={`text-[12px] ${className}`}>
      {rows.map((r, i) => (
        <div key={i} className="flex items-baseline justify-between gap-6 border-b border-hairline py-1.5 last:border-b-0">
          <dt className="text-secondary">{r.k}</dt>
          <dd className={`text-right ${r.tone ?? ""}`}>
            {r.v}
            {r.sub ? <div className="text-[11px] text-muted">{r.sub}</div> : null}
          </dd>
        </div>
      ))}
    </dl>
  );
}

/** A single ratio against a limit. */
export function Meter({ value, max, className = "", tone }: { value: number; max: number; className?: string; tone?: "series" | "gain" | "warn" | "loss" }) {
  const share = max > 0 ? Math.max(0, Math.min(1, value / max)) : 0;
  const bg = tone === "gain" ? "var(--gain)" : tone === "warn" ? "var(--warn)" : tone === "loss" ? "var(--loss)" : "var(--accent)";
  return (
    <div className={`h-1.5 w-full overflow-hidden rounded-[1px] bg-panel-2 ${className}`} role="presentation">
      <div className="h-full" style={{ width: `${share * 100}%`, background: bg }} />
    </div>
  );
}

export function InlineBar({ share, className = "", color = "var(--accent)" }: { share: number; className?: string; color?: string }) {
  return (
    <span className={`inline-block h-1.5 w-16 overflow-hidden rounded-[1px] bg-panel-2 align-middle ${className}`} aria-hidden="true">
      <span className="block h-full" style={{ width: `${Math.max(0, Math.min(1, share)) * 100}%`, background: color }} />
    </span>
  );
}

export function TextLink({ href, children, external = false, className = "" }: { href: string; children: ReactNode; external?: boolean; className?: string }) {
  const cls = `inline-flex items-center gap-1 text-accent hover:underline ${className}`;
  if (external)
    return (
      <a href={href} target="_blank" rel="noreferrer" className={cls}>
        {children}
        <Icon name="external" size={11} />
      </a>
    );
  return (
    <Link href={href} className={cls}>
      {children}
    </Link>
  );
}

/** Card-header action: "View all" style link. */
export function CardLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <Link href={href} className="inline-flex items-center gap-1 text-[11px] text-accent hover:underline">
      {children}
      <span aria-hidden>&gt;</span>
    </Link>
  );
}

export function Chip({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <span className={`inline-block rounded-[2px] bg-panel-2 px-1.5 py-0.5 text-[10px] font-medium text-secondary ${className}`}>{children}</span>;
}

export function Symbol({ children }: { children: ReactNode }) {
  return <span className="font-semibold">{children}</span>;
}

export function Note({ children, tone = "muted" }: { children: ReactNode; tone?: "muted" | "warn" }) {
  return <p className={`mt-3 text-[11px] ${tone === "warn" ? "text-warn" : "text-muted"}`}>{children}</p>;
}
