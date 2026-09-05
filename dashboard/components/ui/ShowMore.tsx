"use client";

import { useState, type ReactNode } from "react";
import { Icon } from "@/components/ui/Icon";

/**
 * Curated, then drill down. Both halves are rendered on the server;
 * this only decides whether the rest is mounted.
 *
 * With `head`, preview and rest are expected to be <tbody> nodes and are
 * wrapped in one table so the columns stay aligned.
 */
export function ShowMore({
  preview,
  rest,
  moreLabel,
  lessLabel = "Show less",
  head,
  tableClassName = "tbl",
  wrapClassName,
}: {
  preview: ReactNode;
  rest: ReactNode;
  moreLabel: string;
  lessLabel?: string;
  head?: ReactNode;
  tableClassName?: string;
  /** Wraps the table only (not the button), e.g. "overflow-x-auto". */
  wrapClassName?: string;
}) {
  const [open, setOpen] = useState(false);
  const body = (
    <>
      {preview}
      {open ? rest : null}
    </>
  );
  return (
    <>
      {head ? (
        <div className={wrapClassName}>
          <table className={tableClassName}>
            <thead>{head}</thead>
            {body}
          </table>
        </div>
      ) : (
        body
      )}
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="mt-2 inline-flex items-center gap-1 rounded-[6px] px-1.5 py-1 text-xs font-medium text-secondary hover:bg-panel-2 hover:text-ink"
        aria-expanded={open}
      >
        <Icon name="chevron" size={14} className={open ? "rotate-180" : ""} />
        {open ? lessLabel : moreLabel}
      </button>
    </>
  );
}
