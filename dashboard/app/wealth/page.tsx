import { GroupedBarChart, type BarPoint } from "@/components/charts/GroupedBarChart";
import { Sparkline } from "@/components/charts/Sparkline";
import { Empty, EntityDot, EntityTag, Figure, FigureStrip, Note, PageHeader, Panel, Section, Severity } from "@/components/ui";
import { ShowMore } from "@/components/ui/ShowMore";
import { consolidated, entitiesData, plan, properties } from "@/lib/data/latest";
import { series } from "@/lib/data/series";
import { dateShort, dateTime, humanize, money, num, plural, signed, tone } from "@/lib/format";
import { accountLabel, entities, entity } from "@/lib/labels";
import type { CashFlowWindow, Debt, LedgerAccount } from "@/lib/types";

export const dynamic = "force-dynamic";

const WINDOWS: { key: "30d" | "90d"; label: string }[] = [
  { key: "30d", label: "Trailing 30 days" },
  { key: "90d", label: "Trailing 90 days" },
];

export default function Wealth() {
  const cons = consolidated();
  const ents = entitiesData();
  const props = properties();
  const pl = plan();
  const { points } = series();
  const order = entities();

  if (!cons?.available) {
    return (
      <>
        <PageHeader title="Wealth" />
        <Empty>
          The bank ledger is not available{cons?.reason ? `: ${cons.reason}` : ""}. Connect a feed in Setup and run the daily pipeline.
        </Empty>
      </>
    );
  }

  const byEntity = cons.by_entity ?? {};
  const entityKeys = [...order.map((e) => e.key).filter((k) => byEntity[k]), ...Object.keys(byEntity).filter((k) => !order.some((e) => e.key === k))];
  const debts = pl?.debts;
  const cf90 = cons.cash_flow?.["90d"];
  const cf30 = cons.cash_flow?.["30d"];
  const flows = cf90?.inter_entity_flows ?? [];
  const unmatched = cf30?.unmatched ?? [];
  const sync = cons.ledger_sync;
  const pushed = cons.pushed_valuations ?? [];

  return (
    <>
      <PageHeader title="Wealth" sub={`as of ${dateShort(cons.asof)}, inter-entity transfers netted`} />

      <FigureStrip className="mb-4">
        <Figure size="lg" label="Net worth" value={money(cons.net_worth)} />
        <Figure label="Assets" value={money(cons.assets)} />
        <Figure label="Liabilities" value={money(cons.liabilities)} />
        <Figure
          label="Personal cash runway"
          value={cons.personal_runway_months != null ? `${num(cons.personal_runway_months, 1)} mo` : "n/a"}
          sub={pl?.emergency_fund ? `target ${pl.emergency_fund.target_months} months` : undefined}
          tone={pl?.emergency_fund && pl.emergency_fund.months_covered < pl.emergency_fund.target_months ? "text-warn" : ""}
        />
      </FigureStrip>

      <Section title="By entity">
        <div className="grid gap-4 md:grid-cols-3">
          {entityKeys.map((k) => {
            const e = byEntity[k];
            const info = entity(k);
            const hist = points.map((p) => p.byEntity[k] ?? null);
            return (
              <Panel key={k}>
                <div className="flex items-center justify-between gap-3">
                  <div className="inline-flex items-center gap-2 text-sm font-medium">
                    <EntityDot entityKey={k} />
                    {info.label}
                  </div>
                  <Sparkline values={hist} label={`${info.label} net worth trend`} />
                </div>
                <div className="figure mt-3 text-[22px] font-semibold leading-none">{money(e.net_worth)}</div>
                <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
                  <dt className="text-secondary">Assets</dt>
                  <dd className="text-right tabular-nums">{money(e.assets)}</dd>
                  <dt className="text-secondary">Liabilities</dt>
                  <dd className="text-right tabular-nums">{money(e.liabilities)}</dd>
                  <dt className="text-secondary">Cash</dt>
                  <dd className="text-right tabular-nums">{money(e.cash)}</dd>
                  <dt className="text-secondary">Accounts</dt>
                  <dd className="text-right tabular-nums">{e.n_accounts}</dd>
                </dl>
              </Panel>
            );
          })}
        </div>
      </Section>

      <Section title="Cash flow" description="per entity, transfers netted">
        <div className="grid gap-4 md:grid-cols-2">
          {WINDOWS.map((w) => {
            const cf = cons.cash_flow?.[w.key];
            return (
              <div key={w.key}>
                <div className="label mb-2">{w.label}</div>
                {cf ? <CashFlowBlock cf={cf} entityKeys={entityKeys} /> : <Empty>No transactions in this window yet.</Empty>}
              </div>
            );
          })}
        </div>
      </Section>

      <div className="grid gap-4 xl:grid-cols-2">
        <Section title="Properties" description={props ? `${plural(props.properties.length, "property", "properties")} worth ${money(props.total_value)}` : undefined}>
          {props?.properties.length ? (
            <div className="overflow-x-auto">
            <table className="tbl min-w-[520px]">
              <thead>
                <tr>
                  <th>Property</th>
                  <th>Entity</th>
                  <th className="num">Value</th>
                  <th className="num">Rent est.</th>
                  <th>Source</th>
                </tr>
              </thead>
              <tbody>
                {props.properties.map((p) => (
                  <tr key={p.key}>
                    <td>
                      {p.name}
                      {p.year_built || p.living_area ? (
                        <div className="text-xs text-muted">
                          {[p.living_area ? `${num(p.living_area, 0)} sq ft` : null, p.year_built ? `built ${p.year_built}` : null].filter(Boolean).join(", ")}
                        </div>
                      ) : null}
                    </td>
                    <td>
                      <EntityTag entityKey={p.entity} />
                    </td>
                    <td className="num">{money(p.value)}</td>
                    <td className="num text-secondary">{p.rent_zestimate != null ? `${money(p.rent_zestimate)}/mo` : "n/a"}</td>
                    <td className="text-secondary">{p.source === "zillow" ? "Zillow" : humanize(p.source)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            </div>
          ) : (
            <Empty>No properties. Add them to config/properties.yml.</Empty>
          )}
          {props?.asof ? <Note>Values refreshed {dateShort(props.asof)}.</Note> : null}
        </Section>

        <Section
          title="Debts"
          description={debts ? `${money(debts.total)} outstanding, ${money(debts.annual_interest)} interest per year` : undefined}
         
        >
          {debts?.items.length ? <DebtTable items={debts.items} /> : <Empty>No debts in the ledger.</Empty>}
          {debts?.rates_missing?.length ? <Note tone="warn">Rate unknown for {debts.rates_missing.join(", ")}. Add rate_pct in config/profile.yml.</Note> : null}
        </Section>
      </div>

      <Section title="Accounts" description={ents ? `${plural(Object.values(ents.entities).reduce((n, e) => n + e.accounts.length, 0), "account")} in the ledger` : undefined} className="mt-4">
        {ents ? <AccountsByEntity entityKeys={entityKeys} data={ents.entities} /> : <Empty>Account detail arrives with the next daily run.</Empty>}
        {cons.unmapped_accounts?.length ? (
          <Note tone="warn">
            Unmapped ledger accounts: {cons.unmapped_accounts.map((a) => a.name).join(", ")}. Add them to config/entities.yml.
          </Note>
        ) : null}
      </Section>

      <div className="grid gap-4 xl:grid-cols-2">
        <Section title="Owner pay and transfers" description="last 90 days">
          {flows.length ? (
            <ShowMore
              head={
                <tr>
                  <th>Date</th>
                  <th>From</th>
                  <th>To</th>
                  <th className="num">Amount</th>
                  <th className="hidden sm:table-cell">Memo</th>
                </tr>
              }
              preview={<FlowRows rows={flows.slice(0, 5)} />}
              rest={<FlowRows rows={flows.slice(5)} />}
              moreLabel={`Show all ${flows.length}`}
            />
          ) : (
            <Empty>No transfers between entities detected.</Empty>
          )}
        </Section>

        <Section title="Needs review" description="unmatched transfers, 30 days">
          {unmatched.length ? (
            <table className="tbl">
              <tbody>
                {unmatched.map((u) => (
                  <tr key={u.id}>
                    <td className="w-8">
                      <Severity s="warn" iconOnly />
                    </td>
                    <td className="whitespace-nowrap text-secondary">{dateShort(u.date)}</td>
                    <td>
                      <EntityTag entityKey={u.entity} />
                    </td>
                    <td className={`num ${tone(u.amount)}`}>{money(u.amount)}</td>
                    <td className="text-xs">{u.name}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <Empty>Nothing needs review.</Empty>
          )}
        </Section>
      </div>

      <p className="mt-4 text-[11px] text-muted">
        Ledger ({sync?.provider ?? "feed"}) last synced {sync?.last_success ? dateTime(sync.last_success) : "never"}
        {sync?.last_error ? ` (last error: ${sync.last_error})` : ""}.{" "}
        {pushed.length ? `Brokerage values mirrored ${pushed.filter((p) => p.ok).length} of ${pushed.length} (${pushed.map((p) => accountLabel(p.account)).join(", ")}).` : ""}
      </p>
    </>
  );
}

function CashFlowBlock({ cf, entityKeys }: { cf: CashFlowWindow; entityKeys: string[] }) {
  const rows = entityKeys.filter((k) => cf.per_entity[k]);
  const data: BarPoint[] = rows.map((k) => ({ group: entity(k).short, income: cf.per_entity[k].income, expense: cf.per_entity[k].expense }));
  data.push({ group: "All entities", income: cf.consolidated.income, expense: cf.consolidated.expense });
  return (
    <>
      <GroupedBarChart
        data={data}
        series={[
          { key: "income", label: "Income", color: "var(--series-1)" },
          { key: "expense", label: "Expense", color: "var(--dim)" },
        ]}
        height={44 + data.length * 40}
      />
      <table className="tbl mt-2">
        <thead>
          <tr>
            <th>Entity</th>
            <th className="num">Income</th>
            <th className="num">Expense</th>
            <th className="num">Net</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((k) => {
            const e = cf.per_entity[k];
            return (
              <tr key={k}>
                <td>
                  <EntityTag entityKey={k} />
                </td>
                <td className="num">{money(e.income)}</td>
                <td className="num">{money(e.expense)}</td>
                <td className={`num ${tone(e.net)}`}>{signed(e.net, (x) => money(x))}</td>
              </tr>
            );
          })}
          <tr className="subtotal">
            <td>All entities</td>
            <td className="num">{money(cf.consolidated.income)}</td>
            <td className="num">{money(cf.consolidated.expense)}</td>
            <td className={`num ${tone(cf.consolidated.net)}`}>{signed(cf.consolidated.net, (x) => money(x))}</td>
          </tr>
        </tbody>
      </table>
      <div className="mt-2 flex gap-4 text-xs text-muted">
        <span className="inline-flex items-center gap-1.5">
          <span className="inline-block h-2 w-2 rounded-full bg-series-1" /> Income
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="inline-block h-2 w-2 rounded-full bg-dim" /> Expense
        </span>
      </div>
    </>
  );
}

function DebtTable({ items }: { items: Debt[] }) {
  const sorted = [...items].sort((a, b) => (b.rate_pct ?? -1) - (a.rate_pct ?? -1));
  const verdict = (d: Debt) => {
    const v = d.payoff_vs_invest ?? "";
    if (v.startsWith("pay down")) return { text: "Pay down", cls: "text-warn" };
    if (v.startsWith("invest")) return { text: "Invest first", cls: "text-secondary" };
    if (v.startsWith("rate unknown")) return { text: "Rate unknown", cls: "text-muted" };
    return { text: v, cls: "text-secondary" };
  };
  return (
    <div className="overflow-x-auto">
    <table className="tbl min-w-[520px]">
      <thead>
        <tr>
          <th>Debt</th>
          <th className="num">Balance</th>
          <th className="num">Rate</th>
          <th className="num">Interest / yr</th>
          <th>Suggestion</th>
        </tr>
      </thead>
      <tbody>
        {sorted.map((d) => {
          const v = verdict(d);
          return (
            <tr key={d.name}>
              <td>
                <div className="min-w-[140px]">{d.name}</div>
                <div className="text-[11px] text-muted">
                  <EntityTag entityKey={d.entity} />
                </div>
              </td>
              <td className="num">{money(d.balance)}</td>
              <td className="num">{d.rate_pct != null ? `${num(d.rate_pct, 2)}%` : "n/a"}</td>
              <td className="num text-secondary">{d.annual_interest != null ? money(d.annual_interest) : "n/a"}</td>
              <td className={`whitespace-nowrap text-[11px] font-semibold ${v.cls}`}>{v.text}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
    </div>
  );
}

function AccountsByEntity({ entityKeys, data }: { entityKeys: string[]; data: Record<string, { accounts: LedgerAccount[]; net_worth: number; assets: number; liabilities: number }> }) {
  const keys = [...entityKeys, ...Object.keys(data).filter((k) => !entityKeys.includes(k))].filter((k) => data[k]);
  const TYPE: Record<string, string> = { depository: "Bank", investment: "Investment", credit_card: "Credit card", loan: "Loan", property: "Property" };
  const head = (
    <tr>
      <th>Account</th>
      <th>Type</th>
      <th className="num">Balance</th>
    </tr>
  );
  const rowsFor = (k: string, list: LedgerAccount[]) =>
    [...list]
      .sort((a, b) => Math.abs(b.balance) - Math.abs(a.balance))
      .map((a) => (
        <tr key={a.id}>
          <td className="pl-6">{a.name}</td>
          <td className="text-secondary">
            {TYPE[a.type] ?? humanize(a.type)}
            {a.subtype && a.subtype !== a.type ? <span className="text-muted"> {humanize(a.subtype).toLowerCase()}</span> : null}
          </td>
          <td className={`num ${a.classification === "liability" ? "text-secondary" : ""}`}>{a.classification === "liability" ? `-${money(Math.abs(a.balance), 2)}` : money(a.balance, 2)}</td>
        </tr>
      ));
  const preview = (
    <tbody>
      {keys.map((k) => (
        <tr key={k} className="subtotal">
          <td>
            <EntityTag entityKey={k} short={false} />
          </td>
          <td className="text-secondary">{plural(data[k].accounts.length, "account")}</td>
          <td className="num">{money(data[k].net_worth)}</td>
        </tr>
      ))}
    </tbody>
  );
  const rest = (
    <tbody>
      {keys.flatMap((k) => [
        <tr key={`${k}-g`} className="group">
          <td colSpan={3}>{entity(k).label}</td>
        </tr>,
        ...rowsFor(k, data[k].accounts),
      ])}
    </tbody>
  );
  return <ShowMore head={head} preview={preview} rest={rest} moreLabel="Show every account" lessLabel="Show subtotals only" />;
}

function FlowRows({ rows }: { rows: { pair_id: string; date: string; from_entity: string; to_entity: string; amount: number; name: string; label?: string }[] }) {
  return (
    <tbody>
      {rows.map((f) => (
        <tr key={f.pair_id}>
          <td className="whitespace-nowrap text-secondary">{dateShort(f.date)}</td>
          <td>
            <EntityTag entityKey={f.from_entity} />
          </td>
          <td>
            <EntityTag entityKey={f.to_entity} />
          </td>
          <td className="num">{money(f.amount)}</td>
          <td className="hidden text-xs text-muted sm:table-cell">{f.label ? humanize(f.label) : f.name}</td>
        </tr>
      ))}
    </tbody>
  );
}
