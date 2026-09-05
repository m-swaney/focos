import Link from "next/link";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Chip, Empty, PageHeader } from "@/components/ui";
import { Segmented } from "@/components/ui/Segmented";
import { briefText, briefs, decisions } from "@/lib/data/briefs";
import { dateMonthYear, dateShort } from "@/lib/format";
import type { BriefRef, Mode } from "@/lib/types";

const KIND: Record<Mode, string> = { daily: "Daily", weekly: "Weekly", monthly: "Monthly" };

export function BriefsShell({ kind, id }: { kind?: string; id?: string }) {
  const list = briefs();
  const selected = kind && id ? list.find((b) => b.kind === kind && b.id === id) ?? { kind: kind as Mode, id, file: "", mtime: 0 } : list[0];
  const text = selected ? briefText(selected.kind, selected.id) : null;
  const dec = decisions(50);

  const groups = new Map<string, BriefRef[]>();
  for (const b of list) {
    const g = dateMonthYear(b.id) || "Other";
    groups.set(g, [...(groups.get(g) ?? []), b]);
  }

  const briefList = list.length ? (
    <nav aria-label="Briefs" className="space-y-4">
      {[...groups.entries()].map(([g, items]) => (
        <div key={g}>
          <div className="mb-1 text-xs font-medium text-secondary">{g}</div>
          <ul>
            {items.map((b) => {
              const active = selected && b.kind === selected.kind && b.id === selected.id;
              return (
                <li key={`${b.kind}-${b.id}`}>
                  <Link
                    href={`/briefs/${b.kind}/${b.id}`}
                    aria-current={active ? "page" : undefined}
                    className={`flex items-center justify-between gap-3 rounded-[6px] px-2 py-1.5 text-[13px] ${active ? "bg-panel-2 font-medium" : "hover:bg-panel-2"}`}
                  >
                    <span>{dateShort(b.id) || b.id}</span>
                    <Chip>{KIND[b.kind]}</Chip>
                  </Link>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </nav>
  ) : (
    <Empty>No briefs yet.</Empty>
  );

  const decisionList = dec.length ? (
    <ul className="divide-y divide-hairline">
      {dec.map((d, i) => (
        <li key={i} className="py-2.5 text-[13px]">
          <div className="flex items-center justify-between gap-3 text-xs text-muted">
            <span>
              {dateShort(d.date)}
              {d.kind ? ` ${d.kind}` : ""}
            </span>
            {d.review_on ? <span>review {dateShort(d.review_on)}</span> : null}
          </div>
          <div className="mt-0.5 leading-snug">{d.text}</div>
        </li>
      ))}
    </ul>
  ) : (
    <Empty>No decisions logged yet.</Empty>
  );

  return (
    <>
      <PageHeader title="Briefs" sub={`${list.length} written`} />
      <div className="grid gap-4 md:grid-cols-12">
        <aside className="card max-h-[45dvh] overflow-y-auto p-3 md:col-span-4 md:max-h-none xl:col-span-3 3xl:col-span-2">
          <Segmented options={["Briefs", "Decisions"]} panels={[briefList, decisionList]} />
        </aside>
        <article className="card order-first p-4 md:order-none md:col-span-8 md:p-6 xl:col-span-9 3xl:col-span-10">
          {text ? (
            <div className="md">
              <Markdown remarkPlugins={[remarkGfm]}>{text}</Markdown>
            </div>
          ) : selected ? (
            <Empty>That brief was not found.</Empty>
          ) : (
            <Empty>
              The first brief appears after a daily run. Run <code className="rounded bg-panel-2 px-1">scripts\run_agent.ps1 -Mode daily</code>.
            </Empty>
          )}
        </article>
      </div>
    </>
  );
}
