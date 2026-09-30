import Link from "next/link";
import type { ReactNode } from "react";
import { NetWorthChart } from "@/components/charts/NetWorthChart";
import type { AreaPoint, ChartSeries } from "@/components/charts/StackedAreaChart";
import { NoteBox } from "@/components/inbox/NoteBox";
import { ItemActions, StartFresh } from "@/components/inbox/ItemActions";
import { Card, CardLink, Chip, Empty, EntityDot, Meter, PageHeader, Severity, Symbol } from "@/components/ui";
import { Icon, type IconName } from "@/components/ui/Icon";
import { ShowMore } from "@/components/ui/ShowMore";
import { ACTOR_LABEL, describeChange, pendingNotes, recentChanges } from "@/lib/data/changes";
import { intradayView } from "@/lib/data/intraday";
import { alerts, briefResult, catalysts, consolidated, diff, entitiesData, needsYou, plan, portfolio, sandbox } from "@/lib/data/latest";
import { series } from "@/lib/data/series";
import { health } from "@/lib/data/status";
import { clean, dateLong, dateShort, money, num, pct, plural, relTime, signed, timeShort, tone } from "@/lib/format";
import { accountLabel, entities, entity, seriesVar } from "@/lib/labels";
import type { LedgerAccount, NeedsYouItem } from "@/lib/types";

export const dynamic = "force-dynamic";

const PAGE_NAME: Record<string, string> = {
  "/wealth": "Wealth",
  "/portfolio": "Portfolio",
  "/sandbox": "Sandbox",
  "/plan": "Plan",
  "/health": "Health",
};

function KindMark({ item }: { item: NeedsYouItem }) {
  const label = (icon: IconName, text: string, cls: string) => (
    <span className={`inline-flex items-center gap-1 text-[11px] font-medium uppercase tracking-wide ${cls}`}>
      <Icon name={icon} size={13} /> {text}
    </span>
  );
  if (item.kind === "approve") return label("clock", "Approve", "text-warn");
  if (item.kind === "decide") return label("question", "Decide", item.severity === "warn" ? "text-warn" : "text-secondary");
  return <Severity s={item.severity} />;
}

function ageText(it: NeedsYouItem): string {
  const d = it.days_open ?? 0;
  if (it.kind === "decide") return d >= 1 ? `waiting ${plural(d, "day")}` : "new today";
  return d >= 1 ? `open ${plural(d, "day")}` : "new";
}

const TYPE_GROUPS: { key: string; label: string; types: string[]; liability?: boolean }[] = [
  { key: "cash", label: "Cash", types: ["depository"] },
  { key: "invest", label: "Investments", types: ["investment"] },
  { key: "property", label: "Real estate", types: ["property"] },
  { key: "vehicle", label: "Vehicles", types: ["vehicle"] },
  { key: "cards", label: "Credit cards", types: ["credit_card"], liability: true },
  { key: "loans", label: "Loans", types: ["loan"], liability: true },
];

export default function Today() {
  const cons = consolidated();
  const pf = portfolio();
  const df = diff();
  const al = alerts();
  const br = briefResult();
  const sb = sandbox();
  const cat = catalysts();
  const pl = plan();
  const ents = entitiesData();
  const { points, entityKeys } = series();
  const order = entities();
  const h = health();

  // Between daily runs the service re-prices holdings, so the page is showing today even though the newest
  // brief is yesterday's. Title the page by the freshest thing on it, and let the brief card carry its own date.
  const iv = intradayView();
  const live = iv?.usable ? iv.data : null;
  const date = live?.asof?.slice(0, 10) ?? br?.date ?? pf?.meta.asof ?? null;
  const briefIsOlder = !!(live && br?.date && date && br.date < date);
  // Needs you: one list built in code (focos/needs_you.py), each item with its own way out. The brief's prose and
  // FYI alerts are not tasks; the first lives in the brief, the second under "Watching".
  const ny = needsYou();
  const items = ny?.items ?? [];
  const watching = ny?.watching ?? [];
  const approvals = items.filter((i) => i.kind === "approve").length;
  const waiting = pendingNotes();
  const updates = recentChanges(8);

  // Net worth. Between daily runs the service re-prices the same holdings from delayed quotes, so prefer those
  // marks when they are fresh and say so; the broker's own totals are the headline right after a run.
  const snapshotInvestments = pf?.meta.broker_total_value ?? pf?.meta.total_value ?? null;
  const investments = live?.total_value ?? snapshotInvestments;
  const netWorth = cons?.available ? (cons.net_worth ?? 0) + (live?.change_since_snapshot ?? 0) : null;
  const change = live ? live.day_change ?? null : df?.total_change ?? null;
  const changePct = live
    ? live.day_change_pct ?? null
    : change != null && investments
      ? change / (investments - change)
      : null;
  const priceNote = live ? `prices ${timeShort(live.asof)}${live.stale ? ", last good quotes" : ""}` : null;
  const hasLedger = points.some((p) => p.netWorth != null);
  const chartSeries: ChartSeries[] = hasLedger
    ? entityKeys.map((k) => ({ key: k, label: entity(k).short, color: seriesVar(entity(k).slot) }))
    : [{ key: "investments", label: "Investments", color: "var(--series-1)" }];
  const chartData: AreaPoint[] = points.map((p) => {
    const row: AreaPoint = { date: p.date };
    if (hasLedger) for (const k of entityKeys) row[k] = p.byEntity[k] ?? null;
    else row.investments = p.brokerTotal;
    return row;
  });

  // Accounts by type (Monarch style).
  const allAccounts: (LedgerAccount & { entity: string })[] = ents
    ? Object.entries(ents.entities).flatMap(([k, e]) => e.accounts.map((a) => ({ ...a, entity: k })))
    : [];
  const groups = TYPE_GROUPS.map((g) => {
    const list = allAccounts.filter((a) => g.types.includes(a.type));
    return { ...g, list, total: list.reduce((n, a) => n + Math.abs(a.balance), 0) };
  }).filter((g) => g.list.length);

  // Cash flow, trailing 30 days.
  const cf = cons?.cash_flow?.["30d"];
  const cfEntities = cf ? order.map((e) => e.key).filter((k) => cf.per_entity[k]) : [];

  // What changed.
  const todaysOrders = (df?.orders ?? []).filter((o) => o.created_at?.slice(0, 10) === df?.date);
  const changed = (df?.movers.length ?? 0) + (df?.new_positions.length ?? 0) + (df?.closed_positions.length ?? 0) + (df?.quantity_changes.length ?? 0) + todaysOrders.length > 0;

  // News.
  const liveMovers = (live?.movers ?? []).filter((m) => m.day_change_pct != null).slice(0, 5);
  const news = [...(cat?.news ?? [])].sort((a, b) => (b.published_at ?? "").localeCompare(a.published_at ?? ""));
  const earnings = cat?.earnings ?? [];

  const ef = pl?.emergency_fund;
  const ret = pl?.retirement;

  return (
    <>
      <PageHeader
        title={date ? dateLong(date) : "Today"}
        sub={
          briefIsOlder
            ? `live prices, newest brief ${dateShort(br!.date)}`
            : h.daily
              ? `${h.label.toLowerCase()}${h.daily.finished ? `, ${timeShort(h.daily.finished)}` : ""}`
              : undefined
        }
      />

      <div className="grid grid-cols-12 gap-4">
        {/* Row 1: attention and headline */}
        <Card title="Needs you" meta={items.length ? plural(items.length, "item") : "all clear"} className="col-span-12 md:col-span-7 3xl:col-span-4" padded={false}>
          {items.length ? (
            <ul className="divide-y divide-hairline">
              {items.map((it) => (
                <li key={it.id} className="flex items-start gap-3 px-4 py-3">
                  <div className="w-[70px] shrink-0 pt-0.5">
                    <KindMark item={it} />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="text-[12.5px] font-medium leading-snug">
                      {clean(it.title)}
                      {it.kind === "approve" && it.amount ? <span className="font-normal text-secondary"> {money(it.amount)}</span> : null}
                    </div>
                    {it.detail && it.detail !== it.title ? (
                      <div className="mt-0.5 text-[12px] leading-snug text-secondary">{clean(it.detail)}</div>
                    ) : null}
                    {it.how ? <div className="mt-0.5 text-[11.5px] leading-snug text-muted">{it.how}</div> : null}
                    <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1.5">
                      <ItemActions item={it} />
                      <span className="text-[11px] text-muted">{ageText(it)}</span>
                      {it.href ? (
                        <Link href={it.href} className="inline-flex items-center gap-1 text-[11px] text-accent hover:underline">
                          {PAGE_NAME[it.href] ?? "Open"} <span aria-hidden>&gt;</span>
                        </Link>
                      ) : null}
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <p className="flex items-center gap-2 px-4 py-4 text-[12px] text-secondary">
              <Icon name="check" size={14} className="text-gain" /> Nothing needs you. focos will tell you when something does.
            </p>
          )}
          {watching.length ? (
            <details className="border-t border-hairline px-4 py-2.5">
              <summary className="cursor-pointer select-none text-[11.5px] text-secondary">
                Watching ({watching.length}), no action needed
              </summary>
              <ul className="mt-2 space-y-2">
                {watching.map((w) => (
                  <li key={w.id} className="flex items-start justify-between gap-3 text-[12px] leading-snug">
                    <span className="text-secondary">{clean(w.title)}</span>
                    <ItemActions item={w} />
                  </li>
                ))}
              </ul>
            </details>
          ) : null}
          {ny?.counts.handled ? (
            <div className="flex items-center gap-2 border-t border-hairline px-4 py-2 text-[11px] text-muted">
              {plural(ny.counts.handled, "item")} handled or snoozed. <StartFresh />
            </div>
          ) : null}
          <div className="border-t border-hairline px-4 py-3">
            <div className="label mb-1">Tell your chief of staff</div>
            <p className="mb-2 text-[11px] text-muted">
              Anything that changed, a correction, or a question. It is read on the next run and shows up under &ldquo;What I updated&rdquo;.
              {waiting.length ? ` ${plural(waiting.length, "note")} waiting for the next run.` : ""}
            </p>
            <NoteBox />
          </div>
        </Card>

        <Card
          title="Today's brief"
          meta={br ? `${br.mode ?? "daily"}, ${dateShort(br.date)}` : undefined}
          right={br ? <CardLink href={`/briefs/${br.mode ?? "daily"}/${br.date}`}>Read</CardLink> : undefined}
          className="col-span-12 md:col-span-5 3xl:col-span-3"
        >
          {br?.summary_line ? (
            <p className="text-[13px] leading-relaxed">{clean(br.summary_line)}</p>
          ) : (
            <Empty>
              No brief yet. Run <code className="rounded-[3px] bg-panel-2 px-1">focos run --mode daily</code>.
            </Empty>
          )}
          {br ? (
            <dl className="mt-4 grid grid-cols-4 gap-2 border-t border-hairline pt-3">
              <div>
                <dt className="label">Alerts</dt>
                <dd className="mt-0.5 text-[13px]">{(al?.alerts.length ?? 0) + (br.alerts?.length ?? 0)}</dd>
              </div>
              <div>
                <dt className="label">Decisions</dt>
                <dd className="mt-0.5 text-[13px]">{br.decisions_logged ?? 0}</dd>
              </div>
              <div>
                <dt className="label">Proposals</dt>
                <dd className="mt-0.5 text-[13px]">{br.proposals?.length ?? 0}</dd>
              </div>
              <div>
                <dt className="label">Updates</dt>
                <dd className="mt-0.5 text-[13px]">{br.updates_applied ?? 0}</dd>
              </div>
            </dl>
          ) : null}
          <div className="mt-4 border-t border-hairline pt-3">
            <div className="label mb-1.5">Recent updates</div>
            {updates.length ? (
              <ul className="space-y-1.5 text-[12px]">
                {updates.map((c, i) => (
                  <li key={i} className="flex items-start gap-2">
                    <span className={`mt-0.5 shrink-0 text-[11px] ${c.ok ? "text-secondary" : "text-critical"}`}>{ACTOR_LABEL[c.actor] ?? c.actor}</span>
                    <span className="min-w-0 flex-1 leading-snug">
                      {describeChange(c)}
                      <span className="text-muted"> {dateShort(c.date)}</span>
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-[11px] text-muted">Nothing changed yet. Done buttons on Plan and your notes land here.</p>
            )}
          </div>
        </Card>

        {/* Row 2: net worth and accounts */}
        <Card
          title={hasLedger ? "Net worth" : "Investments"}
          meta={cons?.asof ? `as of ${dateShort(cons.asof)}` : pf ? `prices ${dateShort(pf.meta.asof)}` : undefined}
          right={<CardLink href="/wealth">Wealth</CardLink>}
          className="col-span-12 md:col-span-7 xl:col-span-8 3xl:col-span-5"
        >
          <div className="mb-4 flex flex-wrap items-end justify-between gap-x-8 gap-y-3">
            <div>
              <div className="text-[28px] font-semibold leading-none tracking-tight sm:text-[34px]">{money(netWorth ?? investments)}</div>
              <div className="mt-2 text-[11px] text-secondary">
                Investments {money(investments)}
                {change != null ? (
                  <span className={`ml-2 ${tone(change)}`}>
                    {signed(change, (x) => money(x))}
                    {changePct != null ? ` (${signed(changePct, (x) => pct(x, 2))})` : ""}
                  </span>
                ) : null}
                {live ? (
                  <span className="text-muted"> today</span>
                ) : df?.previous_date ? (
                  <span className="text-muted"> since {dateShort(df.previous_date)}</span>
                ) : null}
              </div>
              {priceNote ? (
                <div className="mt-1 text-[11px] text-muted">
                  {priceNote}, {live?.delayed_minutes ?? 15}-min delayed
                </div>
              ) : null}
            </div>
            {hasLedger && cons?.by_entity ? (
              <ul className="flex flex-wrap gap-x-5 gap-y-1 text-[11px]">
                {order.map((e) => {
                  const v = cons.by_entity?.[e.key];
                  if (!v) return null;
                  return (
                    <li key={e.key} className="inline-flex items-center gap-1.5">
                      <EntityDot entityKey={e.key} />
                      <span className="text-secondary">{e.short}</span>
                      <span>{money(v.net_worth)}</span>
                    </li>
                  );
                })}
              </ul>
            ) : null}
          </div>
          {chartData.length ? <NetWorthChart data={chartData} series={chartSeries} stacked={hasLedger} height={300} /> : <Empty>History builds one point per daily run.</Empty>}
        </Card>

        <Card title="Accounts" meta={allAccounts.length ? plural(allAccounts.length, "account") : undefined} right={<CardLink href="/wealth">All</CardLink>} className="col-span-12 md:col-span-5 xl:col-span-4 3xl:col-span-3" padded={false}>
          {groups.length ? (
            <ul className="divide-y divide-hairline">
              {groups.map((g) => (
                <li key={g.key} className="px-4 py-2.5">
                  <div className="flex items-baseline justify-between text-[12px]">
                    <span className="font-semibold">{g.label}</span>
                    <span className={g.liability ? "text-secondary" : ""}>{g.liability ? `-${money(g.total)}` : money(g.total)}</span>
                  </div>
                  <ul className="mt-1 space-y-0.5">
                    {[...g.list]
                      .sort((a, b) => Math.abs(b.balance) - Math.abs(a.balance))
                      .slice(0, 3)
                      .map((a) => (
                        <li key={a.id} className="flex items-baseline justify-between gap-3 text-[11px] text-muted">
                          <span className="truncate">{a.name}</span>
                          <span className="shrink-0">{money(Math.abs(a.balance))}</span>
                        </li>
                      ))}
                    {g.list.length > 3 ? <li className="text-[11px] text-muted">+{g.list.length - 3} more</li> : null}
                  </ul>
                </li>
              ))}
            </ul>
          ) : (
            <div className="px-4">
              <Empty>Accounts appear once a bank feed is connected.</Empty>
            </div>
          )}
        </Card>

        {/* Row 3: cash flow, changes, news */}
        <Card title="Cash flow" meta="trailing 30 days" right={<CardLink href="/wealth">Detail</CardLink>} className="col-span-12 md:col-span-6 xl:col-span-4 3xl:col-span-3">
          {cf ? (
            <>
              <div className="grid grid-cols-3 gap-2">
                <div>
                  <div className="label">Income</div>
                  <div className="mt-1 text-[15px] font-semibold">{money(cf.consolidated.income)}</div>
                </div>
                <div>
                  <div className="label">Expense</div>
                  <div className="mt-1 text-[15px] font-semibold">{money(cf.consolidated.expense)}</div>
                </div>
                <div>
                  <div className="label">Net</div>
                  <div className={`mt-1 text-[15px] font-semibold ${tone(cf.consolidated.net)}`}>{signed(cf.consolidated.net, (x) => money(x))}</div>
                </div>
              </div>
              <div className="mt-3 space-y-1">
                <div className="flex h-1.5 overflow-hidden rounded-[1px] bg-panel-2">
                  <div className="h-full bg-series-1" style={{ width: `${(cf.consolidated.income / Math.max(cf.consolidated.income, cf.consolidated.expense, 1)) * 100}%` }} />
                </div>
                <div className="flex h-1.5 overflow-hidden rounded-[1px] bg-panel-2">
                  <div className="h-full bg-dim" style={{ width: `${(cf.consolidated.expense / Math.max(cf.consolidated.income, cf.consolidated.expense, 1)) * 100}%` }} />
                </div>
              </div>
              <table className="tbl mt-3">
                <thead>
                  <tr>
                    <th>Entity</th>
                    <th className="num">Income</th>
                    <th className="num">Net</th>
                  </tr>
                </thead>
                <tbody>
                  {cfEntities.map((k) => (
                    <tr key={k}>
                      <td>
                        <span className="inline-flex items-center gap-1.5">
                          <EntityDot entityKey={k} />
                          {entity(k).short}
                        </span>
                      </td>
                      <td className="num text-secondary">{money(cf.per_entity[k].income)}</td>
                      <td className={`num ${tone(cf.per_entity[k].net)}`}>{signed(cf.per_entity[k].net, (x) => money(x))}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          ) : (
            <Empty>No ledger transactions yet.</Empty>
          )}
        </Card>

        <Card
          title="What changed"
          meta={priceNote ?? (df?.previous_date ? `since ${dateShort(df.previous_date)}` : undefined)}
          className="col-span-12 md:col-span-6 xl:col-span-4 3xl:col-span-3"
        >
          {liveMovers.length ? (
            <div className="mb-3 space-y-3 text-[12px]">
              <ChangeGroup title="Movers today" icon="bolt">
                {liveMovers.map((m) => (
                  <li key={`${m.account}-${m.symbol}`} className="flex items-baseline justify-between gap-3">
                    <span>
                      <Symbol>{m.symbol}</Symbol> <span className="text-muted">{accountLabel(m.account)}</span>
                    </span>
                    <span>
                      <span className={tone(m.day_change_pct)}>{signed(m.day_change_pct, (x) => pct(x, 1))}</span>
                      <span className="ml-2 text-secondary">{money(m.value)}</span>
                    </span>
                  </li>
                ))}
              </ChangeGroup>
            </div>
          ) : null}
          {df && changed ? (
            <div className="space-y-3 text-[12px]">
              {!liveMovers.length && df.movers.length ? (
                <ChangeGroup title="Movers" icon="bolt">
                  {[...df.movers]
                    .sort((a, b) => Math.abs(b.day_change_pct) - Math.abs(a.day_change_pct))
                    .map((m) => (
                      <li key={`${m.account}-${m.symbol}`} className="flex items-baseline justify-between gap-3">
                        <span>
                          <Symbol>{m.symbol}</Symbol> <span className="text-muted">{accountLabel(m.account)}</span>
                        </span>
                        <span>
                          <span className={tone(m.day_change_pct)}>{signed(m.day_change_pct, (x) => pct(x, 1))}</span>
                          <span className="ml-2 text-secondary">{signed(m.value_change, (x) => money(x))}</span>
                        </span>
                      </li>
                    ))}
                </ChangeGroup>
              ) : null}
              {df.new_positions.length ? (
                <ChangeGroup title="Opened" icon="arrow">
                  {df.new_positions.map((p) => (
                    <li key={`${p.account}-${p.symbol}`} className="flex items-baseline justify-between gap-3">
                      <span>
                        <Symbol>{p.symbol}</Symbol> <span className="text-muted">{accountLabel(p.account)}</span>
                      </span>
                      <span>{money(p.value)}</span>
                    </li>
                  ))}
                </ChangeGroup>
              ) : null}
              {df.closed_positions.length ? (
                <ChangeGroup title="Closed" icon="x">
                  {df.closed_positions.map((p) => (
                    <li key={`${p.account}-${p.symbol}`}>
                      <Symbol>{p.symbol}</Symbol> <span className="text-muted">{accountLabel(p.account)}</span>
                    </li>
                  ))}
                </ChangeGroup>
              ) : null}
              {df.quantity_changes.length ? (
                <ChangeGroup title="Quantity" icon="dot">
                  {df.quantity_changes.map((q) => (
                    <li key={`${q.account}-${q.symbol}`} className="flex items-baseline justify-between gap-3">
                      <span>
                        <Symbol>{q.symbol}</Symbol> <span className="text-muted">{accountLabel(q.account)}</span>
                      </span>
                      <span className="text-secondary">
                        {num(q.from, 3)} to {num(q.to, 3)}
                      </span>
                    </li>
                  ))}
                </ChangeGroup>
              ) : null}
              {todaysOrders.length ? (
                <ChangeGroup title="Orders" icon="check">
                  {todaysOrders.map((o) => (
                    <li key={o.id} className="flex items-baseline justify-between gap-3">
                      <span>
                        <span className={o.side === "buy" ? "text-gain" : "text-loss"}>{o.side}</span> <Symbol>{o.symbol}</Symbol>{" "}
                        <span className="text-muted">{accountLabel(o.account)}</span>
                      </span>
                      <span className="text-secondary">
                        {num(o.quantity, 4)} {o.average_price != null ? `@ ${money(o.average_price, 2)}` : ""}
                      </span>
                    </li>
                  ))}
                </ChangeGroup>
              ) : null}
            </div>
          ) : liveMovers.length ? null : (
            <Empty>{df ? "No changes since yesterday." : "Changes appear after the second daily run."}</Empty>
          )}
        </Card>

        <Card title="News" meta={news.length ? plural(news.length, "item") : undefined} className="col-span-12 xl:col-span-4 3xl:col-span-3" padded={false}>
          {news.length ? (
            <div className="px-4 py-1">
              <ShowMore preview={<NewsList items={news.slice(0, 5)} />} rest={<NewsList items={news.slice(5)} />} moreLabel={news.length > 5 ? `Show all ${news.length}` : "Show all"} />
            </div>
          ) : (
            <div className="px-4">
              <Empty>No news in the latest snapshot.</Empty>
            </div>
          )}
          <div className="border-t border-hairline px-4 py-2.5">
            <div className="label mb-1">Earnings, next 14 days</div>
            {earnings.length ? (
              <ul className="space-y-0.5 text-[12px]">
                {earnings.map((e) => (
                  <li key={`${e.symbol}-${e.date}`} className="flex justify-between">
                    <Symbol>{e.symbol}</Symbol>
                    <span className="text-secondary">
                      {dateShort(e.date)} {e.time ?? ""}
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-[11px] text-muted">None for held names.</p>
            )}
          </div>
        </Card>

        {/* Row 4: sandbox and plan snapshot */}
        <Card title="Sandbox" meta={sb ? (sb.killed ? "killed" : sb.mode) : undefined} right={<CardLink href="/sandbox">Detail</CardLink>} className="col-span-12 md:col-span-4 3xl:col-span-3">
          {sb ? (
            <div className="space-y-3 text-[12px]">
              <div className="flex items-baseline justify-between">
                <span className="text-secondary">Mode</span>
                <span className={sb.killed ? "font-semibold text-critical" : sb.mode === "live" ? "font-semibold text-warn" : ""}>{sb.killed ? "Killed" : sb.mode === "live" ? "Live" : "Paper"}</span>
              </div>
              <div>
                <div className="flex items-baseline justify-between">
                  <span className="text-secondary">Warmup</span>
                  <span>
                    {sb.run_count} of {sb.warmup_runs}
                  </span>
                </div>
                <Meter value={sb.run_count} max={sb.warmup_runs} className="mt-1.5" tone={sb.warmup_remaining === 0 ? "gain" : "series"} />
              </div>
              <div className="flex items-baseline justify-between">
                <span className="text-secondary">Agentic account</span>
                <span>{money(sb.account?.portfolio?.total_value ?? 0)}</span>
              </div>
              <div className="flex items-baseline justify-between">
                <span className="text-secondary">Awaiting approval</span>
                <span className={approvals ? "text-warn" : ""}>{approvals}</span>
              </div>
            </div>
          ) : (
            <Empty>No sandbox state yet.</Empty>
          )}
        </Card>

        <Card title="Plan" meta="snapshot" right={<CardLink href="/plan">Detail</CardLink>} className="col-span-12 md:col-span-8 3xl:col-span-9">
          {pl?.available ? (
            <div className="grid gap-x-8 gap-y-3 sm:grid-cols-2 3xl:grid-cols-4">
              <PlanRow label="Emergency fund" value={ef ? `${num(ef.months_covered, 1)} of ${ef.target_months} mo` : "n/a"} share={ef ? ef.months_covered / ef.target_months : 0} tone={ef && ef.months_covered < ef.target_months ? "warn" : "gain"} />
              <PlanRow label="Roth IRA this year" value={pl.roth ? `${money(pl.roth.contributed)} of ${money(pl.roth.limit)}` : "n/a"} share={pl.roth ? pl.roth.contributed / pl.roth.limit : 0} tone={pl.roth?.on_pace ? "gain" : "warn"} />
              <PlanRow label="Savings rate" value={pl.savings ? pct(pl.savings.savings_rate, 0) : "n/a"} share={pl.savings?.savings_rate ?? 0} tone="series" />
              <PlanRow label="Retirement target odds" value={ret?.probability_hit_target != null ? pct(ret.probability_hit_target, 0) : "n/a"} share={ret?.probability_hit_target ?? 0} tone={ret && (ret.probability_hit_target ?? 0) >= 0.75 ? "gain" : "warn"} />
            </div>
          ) : (
            <Empty>The plan is computed by the daily pipeline.</Empty>
          )}
        </Card>
      </div>
    </>
  );
}

function PlanRow({ label, value, share, tone }: { label: string; value: string; share: number; tone: "series" | "gain" | "warn" | "loss" }) {
  return (
    <div>
      <div className="flex items-baseline justify-between text-[12px]">
        <span className="text-secondary">{label}</span>
        <span>{value}</span>
      </div>
      <Meter value={share} max={1} className="mt-1.5" tone={tone} />
    </div>
  );
}

function ChangeGroup({ title, icon, children }: { title: string; icon: IconName; children: ReactNode }) {
  return (
    <div>
      <div className="label mb-1 inline-flex items-center gap-1.5">
        <Icon name={icon} size={12} /> {title}
      </div>
      <ul className="space-y-1">{children}</ul>
    </div>
  );
}

function NewsList({ items }: { items: { symbol: string; title: string; source: string; published_at: string }[] }) {
  return (
    <ul className="divide-y divide-hairline">
      {items.map((n, i) => (
        <li key={i} className="flex gap-3 py-2 text-[12px]">
          <Chip className="mt-0.5 w-12 shrink-0 self-start text-center">{n.symbol}</Chip>
          <div className="min-w-0">
            <div className="leading-snug">{clean(n.title)}</div>
            <div className="text-[11px] text-muted">
              {n.source}
              {relTime(n.published_at) ? `, ${relTime(n.published_at)}` : ""}
            </div>
          </div>
        </li>
      ))}
    </ul>
  );
}
