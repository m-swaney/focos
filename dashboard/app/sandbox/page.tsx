import { ApproveButton, KillSwitch } from "@/components/SandboxControls";
import { Chip, Empty, Figure, FigureStrip, Kv, Meter, PageHeader, Section, StatusMark, Symbol } from "@/components/ui";
import { Icon } from "@/components/ui/Icon";
import { ShowMore } from "@/components/ui/ShowMore";
import { gateLog } from "@/lib/data/briefs";
import { sandbox } from "@/lib/data/latest";
import { dateShort, dateTime, money, num, pct, plural, signed, tone } from "@/lib/format";
import type { GateEntry } from "@/lib/types";

export const dynamic = "force-dynamic";

const RULES: { key: string; label: string; fmt: (v: unknown) => string }[] = [
  { key: "budget_usd", label: "Total budget", fmt: (v) => money(Number(v)) },
  { key: "weekly_budget_usd", label: "Weekly buy budget", fmt: (v) => money(Number(v)) },
  { key: "max_order_usd", label: "Largest single order", fmt: (v) => money(Number(v)) },
  { key: "max_position_weight", label: "Largest position", fmt: (v) => `${pct(Number(v), 0)} of the account` },
  { key: "max_orders_per_run", label: "Orders per run", fmt: (v) => String(v) },
  { key: "max_orders_per_week", label: "Orders per week", fmt: (v) => String(v) },
  { key: "instruments", label: "Instruments", fmt: (v) => (Array.isArray(v) ? v.map((x) => (x === "etf" ? "ETF" : String(x))).join(", ") : String(v)) },
  { key: "min_price", label: "Minimum share price", fmt: (v) => money(Number(v)) },
];

export default function SandboxPage() {
  const sb = sandbox();
  const log = gateLog(30);
  if (!sb) {
    return (
      <>
        <PageHeader title="Sandbox" />
        <Empty>No sandbox state yet. It appears after the first daily run.</Empty>
      </>
    );
  }
  const acct = sb.account ?? {};
  const sc = sb.scorecard;
  const proposals = [...(sb.proposals ?? [])].sort((a, b) => {
    const pa = !a.paper && !a.approved ? 0 : 1;
    const pb = !b.paper && !b.approved ? 0 : 1;
    return pa - pb || b.date.localeCompare(a.date);
  });
  const pending = proposals.filter((p) => !p.paper && !p.approved).length;
  const orders = acct.recent_orders ?? [];
  const positions = acct.positions ?? [];
  const modeLabel = sb.killed ? "Killed" : sb.mode === "live" ? "Live" : "Paper";

  return (
    <>
      <PageHeader title="Sandbox" sub="the only account the agent can trade; every order passes the rules gate" />

      <FigureStrip className="mb-8">
        <Figure
          size="lg"
          label="Mode"
          value={
            <span className="inline-flex items-center gap-2">
              {sb.killed ? <Icon name="critical" size={28} className="text-critical" /> : null}
              {modeLabel}
            </span>
          }
          tone={sb.killed ? "text-critical" : sb.mode === "live" ? "text-warn" : ""}
          sub={sb.trading_enabled ? "trade tools enabled for the agent" : "trade tools off"}
        />
        <Figure
          label="Warmup runs"
          value={`${sb.run_count} of ${sb.warmup_runs}`}
          sub={
            <>
              <Meter value={sb.run_count} max={sb.warmup_runs} className="mb-1.5 mt-0.5 max-w-[160px]" tone={sb.warmup_remaining === 0 ? "gain" : "series"} />
              {sb.warmup_remaining > 0 ? `${plural(sb.warmup_remaining, "paper run")} remaining` : "warmup complete"}
            </>
          }
        />
        <Figure label="Agentic account" value={money(acct.portfolio?.total_value ?? 0)} sub={`${money(acct.portfolio?.cash ?? 0)} cash, ending ${acct.last4 ?? "????"}`} />
        <Figure label="Live orders placed" value={String(sb.live_orders ?? 0)} sub="the first five need approval" />
        <Figure
          label="Paper score"
          value={sc?.available && sc.n_positions ? signed(sc.avg_alpha_pct, (x) => pct(x)) : "n/a"}
          tone={tone(sc?.avg_alpha_pct)}
          sub={sc?.available && sc.n_positions ? `alpha vs SPY across ${plural(sc.n_positions, "position")}, hit rate ${pct(sc.hit_rate, 0)}` : "no scored positions yet"}
        />
      </FigureStrip>

      <div className="card mb-4 p-4">
        <KillSwitch killed={!!sb.killed} />
        <p className="mt-2 text-[11px] text-muted">
          The token is FOCOS_DASH_TOKEN in the repo .env. Going live is a deliberate step: <code className="rounded bg-panel-2 px-1">python -m focos sandbox set-mode live</code>.
        </p>
      </div>

      <Section title="Proposals" description={pending ? `${plural(pending, "proposal")} awaiting approval` : "none pending"}>
        {proposals.length ? (
          <div className="overflow-x-auto">
            <table className="tbl min-w-[960px]">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Order</th>
                  <th className="num">Amount</th>
                  <th>Thesis</th>
                  <th>Exit plan</th>
                  <th>Kind</th>
                  <th>Approval</th>
                </tr>
              </thead>
              <tbody>
                {proposals.map((p) => (
                  <tr key={p._file ?? p.ref_id}>
                    <td className="text-secondary">{dateShort(p.date)}</td>
                    <td>
                      <span className={p.side === "buy" ? "text-gain" : "text-loss"}>{p.side}</span> <Symbol>{p.symbol}</Symbol>
                      <div className="text-xs text-muted">{p.ref_id}</div>
                    </td>
                    <td className="num">{money(p.dollar_amount)}</td>
                    <td className="max-w-[360px] text-xs">{p.thesis}</td>
                    <td className="max-w-[240px] text-xs text-secondary">
                      {p.exit_plan}
                      {p.stop_loss != null ? <div className="text-muted">stop {typeof p.stop_loss === "number" ? money(p.stop_loss, 2) : p.stop_loss}</div> : null}
                      {p.horizon_days ? <div className="text-muted">{plural(p.horizon_days, "day")} horizon</div> : null}
                    </td>
                    <td>
                      <Chip>{p.paper ? "paper" : "live"}</Chip>
                    </td>
                    <td>{p.paper ? <span className="text-xs text-muted">not needed</span> : <ApproveButton refId={p.ref_id} approved={!!p.approved} />}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty>No proposals yet.</Empty>
        )}
      </Section>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3 3xl:grid-cols-4">
        <Section title="Limits" description="config/sandbox_rules.yml">
          <Kv rows={RULES.filter((r) => sb.rules && r.key in sb.rules).map((r) => ({ k: r.label, v: r.fmt(sb.rules?.[r.key]) }))} />
        </Section>

        <Section title="Positions">
          {positions.length ? (
            <table className="tbl">
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th className="num">Quantity</th>
                  <th className="num">Value</th>
                  <th className="num">Day</th>
                </tr>
              </thead>
              <tbody>
                {positions.map((p) => (
                  <tr key={p.symbol}>
                    <td>
                      <Symbol>{p.symbol}</Symbol>
                    </td>
                    <td className="num text-secondary">{num(p.quantity, 4)}</td>
                    <td className="num">{money(p.value, 2)}</td>
                    <td className={`num ${tone(p.day_change_pct)}`}>{signed(p.day_change_pct, (x) => pct(x))}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <Empty>{(acct.portfolio?.total_value ?? 0) > 0 ? "Funded, no positions yet. The warmup has to finish before live orders." : "Fund the Agentic account to start."}</Empty>
          )}
        </Section>

        <Section title="Recent orders" className="md:col-span-2 xl:col-span-1">
          {orders.length ? (
            <div className="overflow-x-auto">
            <table className="tbl min-w-[420px]">
              <thead>
                <tr>
                  <th>When</th>
                  <th>Order</th>
                  <th className="num">Quantity</th>
                  <th>State</th>
                </tr>
              </thead>
              <tbody>
                {orders.map((o) => (
                  <tr key={o.id}>
                    <td className="text-secondary">{dateTime(o.created_at)}</td>
                    <td>
                      <span className={o.side === "buy" ? "text-gain" : "text-loss"}>{o.side}</span> <Symbol>{o.symbol}</Symbol>
                    </td>
                    <td className="num">
                      {num(o.quantity, 4)}
                      {o.average_price != null ? <span className="text-muted"> at {money(o.average_price, 2)}</span> : null}
                    </td>
                    <td className="text-secondary">{o.state}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            </div>
          ) : (
            <Empty>No orders in the Agentic account.</Empty>
          )}
        </Section>
      </div>

      <div className="mt-4 grid gap-4 md:grid-cols-2">
        <Section
          title="Scorecard"
          description={
            sc?.available && sc.n_positions
              ? `beat SPY ${pct(sc.beat_spy_rate, 0)}, avg ${signed(sc.avg_return_pct, (x) => pct(x))}, P&L ${signed(sc.total_pnl_usd, (x) => money(x))}`
              : "marked to market vs SPY"
          }
         
        >
          {sc?.available && sc.positions?.length ? (
            <div className="overflow-x-auto">
              <table className="tbl min-w-[640px]">
                <thead>
                  <tr>
                    <th>Symbol</th>
                    <th>Filled</th>
                    <th className="num">Fill</th>
                    <th className="num">Now</th>
                    <th className="num">Return</th>
                    <th className="num">SPY</th>
                    <th className="num">Alpha</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {sc.positions.map((p) => (
                    <tr key={p.ref_id}>
                      <td>
                        <Symbol>{p.symbol}</Symbol>
                      </td>
                      <td className="text-secondary">{dateShort(p.fill_date)}</td>
                      <td className="num">{money(p.fill_price, 2)}</td>
                      <td className="num">{money(p.current_price, 2)}</td>
                      <td className={`num ${tone(p.return_pct)}`}>{signed(p.return_pct, (x) => pct(x))}</td>
                      <td className="num text-secondary">{signed(p.spy_return_pct, (x) => pct(x))}</td>
                      <td className={`num ${tone(p.alpha_pct)}`}>{signed(p.alpha_pct, (x) => pct(x))}</td>
                      <td className="text-secondary">{p.status}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <Empty>Fills in after proposals are marked to market.</Empty>
          )}
        </Section>

        <Section title="Gate log" description="every order attempt">
          {log.length > 10 ? (
            <ShowMore preview={<GateList entries={log.slice(0, 10)} />} rest={<GateList entries={log.slice(10)} className="mt-3" />} moreLabel={`Show all ${log.length}`} />
          ) : log.length ? (
            <GateList entries={log} />
          ) : (
            <Empty>No order attempts yet.</Empty>
          )}
        </Section>
      </div>
    </>
  );
}

function GateList({ entries, className = "" }: { entries: GateEntry[]; className?: string }) {
  return (
    <ul className={`divide-y divide-hairline ${className}`}>
      {entries.map((e, i) => (
        <li key={i} className="py-2.5 text-[13px]">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <StatusMark ok={e.ok} label={e.ok ? "allowed" : "blocked"} />
            <span>
              {e.tool} <span className={e.side === "buy" ? "text-gain" : e.side === "sell" ? "text-loss" : ""}>{e.side}</span> <Symbol>{e.symbol}</Symbol>
              {e.notional != null ? <span className="text-secondary"> {money(e.notional)}</span> : null}
            </span>
            <span className="ml-auto text-xs text-muted">{dateTime(e.ts)}</span>
          </div>
          {e.reasons?.length ? (
            <ul className="mt-1.5 flex flex-wrap gap-1">
              {e.reasons.map((r, k) => (
                <li key={k} className="min-w-0 max-w-full rounded-[5px] bg-panel-2 px-1.5 py-0.5 text-[11px] text-secondary [overflow-wrap:anywhere]">
                  {r}
                </li>
              ))}
            </ul>
          ) : null}
        </li>
      ))}
    </ul>
  );
}
