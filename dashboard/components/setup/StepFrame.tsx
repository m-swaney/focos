"use client";

import Link from "next/link";
import type { ReactNode } from "react";

export const STEPS: { href: string; key: string; label: string; blurb: string }[] = [
  { href: "/setup", key: "welcome", label: "Welcome", blurb: "where your data lives" },
  { href: "/setup/ai", key: "ai", label: "AI", blurb: "which model writes your briefs" },
  { href: "/setup/ledger", key: "ledger", label: "Banks", blurb: "connect SimpleFIN" },
  { href: "/setup/accounts", key: "accounts", label: "Accounts", blurb: "who owns what" },
  { href: "/setup/holdings", key: "holdings", label: "Holdings", blurb: "investments to analyze" },
  { href: "/setup/profile", key: "profile", label: "Profile", blurb: "a short interview" },
  { href: "/setup/schedule", key: "schedule", label: "Schedule", blurb: "when it runs" },
  { href: "/setup/first-run", key: "first_run", label: "First run", blurb: "see it work" },
];

export function stepIndex(href: string): number {
  return STEPS.findIndex((s) => s.href === href);
}

/** Title, intro, body, and Back/Next links shared by every setup step. */
export function StepFrame({ href, title, intro, children, nextLabel, canNext = true, onNext }: {
  href: string;
  title: string;
  intro?: ReactNode;
  children: ReactNode;
  nextLabel?: string;
  canNext?: boolean;
  onNext?: () => Promise<boolean | void> | boolean | void;
}) {
  const i = stepIndex(href);
  const prev = i > 0 ? STEPS[i - 1] : null;
  const next = i >= 0 && i < STEPS.length - 1 ? STEPS[i + 1] : null;
  return (
    <div className="max-w-[860px]">
      <div className="mb-4">
        <div className="text-[11px] text-muted">
          Step {i + 1} of {STEPS.length}
        </div>
        <h1 className="text-[18px] font-semibold tracking-tight">{title}</h1>
        {intro ? <p className="mt-1 max-w-[640px] text-[13px] text-secondary">{intro}</p> : null}
      </div>
      <div className="card p-4">{children}</div>
      <div className="mt-4 flex items-center justify-between text-xs">
        {prev ? (
          <Link href={prev.href} className="rounded-[6px] px-2 py-1.5 text-secondary hover:bg-panel-2 hover:text-ink">
            ← {prev.label}
          </Link>
        ) : <span />}
        {next ? (
          <Link
            href={next.href}
            aria-disabled={!canNext}
            onClick={async (e) => {
              if (!canNext) { e.preventDefault(); return; }
              if (onNext) {
                const ok = await onNext();
                if (ok === false) e.preventDefault();
              }
            }}
            className={`rounded-[6px] border px-3 py-1.5 font-medium ${canNext ? "border-ink text-ink hover:bg-panel-2" : "border-hairline text-muted"}`}
          >
            {nextLabel ?? `Next: ${next.label}`} →
          </Link>
        ) : null}
      </div>
    </div>
  );
}

export function Field({ label, hint, children }: { label: string; hint?: ReactNode; children: ReactNode }) {
  return (
    <label className="block">
      <span className="label block text-ink">{label}</span>
      {hint ? <span className="mb-1 block text-[11px] text-muted">{hint}</span> : null}
      <span className="mt-1 block">{children}</span>
    </label>
  );
}

export const inputCls = "w-full rounded-[4px] border border-hairline bg-page px-2 py-1.5 text-[13px] focus:border-accent focus:outline-none";
export const btnCls = "inline-flex items-center gap-1.5 rounded-[6px] border border-ink px-3 py-1.5 text-xs font-medium hover:bg-panel-2 disabled:opacity-50";
export const btnQuietCls = "inline-flex items-center gap-1.5 rounded-[6px] border border-hairline px-3 py-1.5 text-xs text-secondary hover:bg-panel-2 hover:text-ink disabled:opacity-50";

export function Msg({ kind = "info", children }: { kind?: "info" | "ok" | "warn" | "bad"; children: ReactNode }) {
  if (!children) return null;
  const cls = { info: "bg-panel-2 text-secondary", ok: "bg-wash-gain text-gain", warn: "bg-wash-warn text-warn", bad: "bg-wash-critical text-critical" }[kind];
  return <div className={`mt-3 rounded-[6px] px-3 py-2 text-[12px] ${cls}`}>{children}</div>;
}
