"use client";

import { useId, useState, type ReactNode } from "react";

/** One server-rendered panel visible at a time. */
export function Segmented({ options, panels, className = "" }: { options: string[]; panels: ReactNode[]; className?: string }) {
  const [i, setI] = useState(0);
  const id = useId();
  return (
    <div className={className}>
      <div role="tablist" className="mb-4 inline-flex rounded-[7px] bg-panel-2 p-0.5">
        {options.map((o, k) => (
          <button
            key={o}
            role="tab"
            id={`${id}-tab-${k}`}
            aria-selected={i === k}
            aria-controls={`${id}-panel-${k}`}
            type="button"
            onClick={() => setI(k)}
            className={`rounded-[6px] px-3 py-1 text-xs font-medium ${i === k ? "bg-panel text-ink shadow-[0_0_0_1px_var(--hairline)]" : "text-secondary hover:text-ink"}`}
          >
            {o}
          </button>
        ))}
      </div>
      {panels.map((p, k) => (
        <div key={k} role="tabpanel" id={`${id}-panel-${k}`} aria-labelledby={`${id}-tab-${k}`} hidden={i !== k}>
          {p}
        </div>
      ))}
    </div>
  );
}
