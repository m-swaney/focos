"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { STEPS } from "@/components/setup/StepFrame";
import { Icon } from "@/components/ui/Icon";

type Steps = Record<string, "done" | "todo" | "skipped">;

/** Left rail listing the setup steps with their completion state (from /setup/status). */
export function Rail() {
  const pathname = usePathname();
  const [steps, setSteps] = useState<Steps>({});
  const [label, setLabel] = useState<string>("");
  useEffect(() => {
    let alive = true;
    api<{ steps: Steps; home_label: string }>("/setup/status").then((r) => {
      if (alive && r && !r.error) {
        setSteps(r.steps ?? {});
        setLabel(r.home_label ?? "");
      }
    });
    return () => {
      alive = false;
    };
  }, [pathname]);
  return (
    <nav aria-label="Setup steps" className="card p-3 lg:sticky lg:top-6">
      <div className="label mb-2 px-1 text-ink">Setup{label ? ` · ${label}` : ""}</div>
      <ol className="flex flex-col gap-0.5">
        {STEPS.map((s, i) => {
          const state = steps[s.key];
          const active = pathname === s.href;
          return (
            <li key={s.href}>
              <Link
                href={s.href}
                aria-current={active ? "step" : undefined}
                className={`flex items-center gap-2 rounded-[4px] px-2 py-1.5 text-[12px] ${active ? "bg-panel-2 font-semibold text-ink" : "text-secondary hover:bg-panel-2 hover:text-ink"}`}
              >
                <span className={`inline-flex h-4 w-4 items-center justify-center rounded-full text-[10px] ${state === "done" ? "bg-gain text-page" : "border border-hairline text-muted"}`}>
                  {state === "done" ? <Icon name="check" size={10} /> : i + 1}
                </span>
                <span className="flex-1">{s.label}</span>
                <span className="hidden text-[10px] text-muted lg:inline">{state === "skipped" ? "skipped" : ""}</span>
              </Link>
            </li>
          );
        })}
      </ol>
      <div className="mt-3 border-t border-hairline px-2 pt-2 text-[11px] text-muted">
        Everything stays on this computer. <Link href="/health" className="underline hover:text-ink">Health</Link>
      </div>
    </nav>
  );
}
