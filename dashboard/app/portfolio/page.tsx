import { HBars, type HBarRow } from "@/components/charts/HBars";
import { Empty, Figure, FigureStrip, InlineBar, Kv, Note, PageHeader, Section, Symbol, TextLink } from "@/components/ui";
import { Segmented } from "@/components/ui/Segmented";
import { ShowMore } from "@/components/ui/ShowMore";
import { artifacts, diff, drift, optimizer, portfolio, risk, taxLots } from "@/lib/data/latest";
import { dateMDY, dateShort, humanize, money, num, pct, plural, signed, tone } from "@/lib/format";
import { accountLabel, etfLabels, riskLimits } from "@/lib/labels";
import type { Position } from "@/lib/types";

export const dynamic = "force-dynamic";

export default function PortfolioPage() {
  const p = portfolio();
  if (!p) {
    return (
      <>
        <PageHeader title="Portfolio" />
        <Empty>No portfolio data yet. Run the daily pipeline.</Empty>
      </>
    );
  }
  const r = risk();
  const opt = optimizer();
  const tax = taxLots();
  const dr = drift();
  const df = diff();
  const art = artifacts();
  const etf = etfLabels();
  const limits = riskLimits();

  const total = p.meta.broker_total_value ?? p.meta.total_value;
  const gain = p.meta.total_value - p.meta.total_cost;
  const gainPct = p.meta.total_cost ? gain / p.meta.total_cost : null;
  const change = df?.total_change ?? null;
  const c = p.concentration;

  const sectorRows: HBarRow[] = Object.entries(p.sectors)
    .sort((a, b) => b[1].weight - a[1].weight)
    .map(([k, v]) => ({ label: k, valueText: pct(v.weight), share: v.weight, sub: money(v.value) }));

  const lt = Object.entries(p.look_through).sort((a, b) => b[1].weight - a[1].weight);
  const ltTop = lt.slice(0, 12);
  const ltRest = lt.slice(12);
  const ltRows: HBarRow[] = ltTop.map(([k, v]) => ({ label: k, valueText: pct(v.weight), share: v.weight, sub: money(v.value) }));
  if (ltRest.length) {
    const w = ltRest.reduce((s, [, v]) => s + v.weight, 0);
    const val = ltRest.reduce((s, [, v]) => s + v.value, 0);
    ltRows.push({ label: `Other (${ltRest.length})`, valueText: pct(w), share: w, sub: money(val), color: "var(--dim)" });
  }

  const classPanels = Object.entries(p.class_weights ?? {}).map(([acct, w]) => (
    <div key={acct} className="mb-4 last:mb-0">
      <div className="mb-1.5 text-xs font-medium text-secondary">{accountLabel(acct)}</div>
      <HBars
        rows={Object.entries(w)
          .sort((a, b) => b[1] - a[1])
          .map(([k, v]) => ({ label: humanize(k), valueText: pct(v), share: v }))}
      />
    </div>
  ));

  const byAccount = p.accounts.map((a) => ({
    ...a,
    positions: p.positions.filter((x) => x.account === a.account).sort((x, y) => y.value - x.value),
  }));

  return (
    <>
      <PageHeader
        title="Portfolio"
        sub={`${plural(p.positions.length, "position")}, prices ${dateShort(p.meta.asof)}${p.meta.prices_stale ? " (cached)" : ""}`}
      />

      <FigureStrip className="mb-4">
        <Figure size="lg" label="Investments" value={money(total)} sub={p.meta.broker_total_value ? "broker total including cash and pending deposits" : undefined} />
        <Figure label="Day change" value={signed(change, (x) => money(x))} tone={tone(change)} sub={df?.previous_date ? `since ${dateShort(df.previous_date)}` : undefined} />
        <Figure label="Unrealized gain" value={signed(gain, (x) => money(x))} tone={tone(gain)} sub={gainPct != null ? `${pct(gainPct)} on ${money(p.meta.total_cost)} cost` : undefined} />
      </FigureStrip>

      <div className="grid gap-4 md:grid-cols-12">
        <Section title="Exposure" description="share of combined portfolio" className="md:col-span-7">
          <Segmented
            options={["Sectors", "Look-through", "Asset class"]}
            panels={[
              <HBars key="s" rows={sectorRows} cap={limits.maxSector} capLabel={limits.maxSector ? `cap ${pct(limits.maxSector, 0)}` : undefined} />,
              <HBars key="l" rows={ltRows} cap={limits.maxSingleStock} capLabel={limits.maxSingleStock ? `cap ${pct(limits.maxSingleStock, 0)}` : undefined} />,
              <div key="c">{classPanels.length ? classPanels : <Empty>Asset classes are assigned in config/analytics.yml.</Empty>}</div>,
            ]}
          />
          {ltRest.length ? <Note>Look-through unpacks ETF top holdings; a name can appear directly and inside a fund.</Note> : null}
        </Section>

        <Section
          title="Concentration and risk"
          description={r?.start ? `backtest ${dateMDY(r.start)} to ${dateMDY(r.end)} vs ${p.meta.benchmark ?? "SPY"}` : undefined}
          className="md:col-span-5"
        >
          <Kv
            rows={[
              {
                k: "Top holding",
                v: c.top1 ? (
                  <>
                    <Symbol>{c.top1.symbol}</Symbol> {pct(c.top1.weight)}
                  </>
                ) : (
                  "n/a"
                ),
                sub: limits.maxSingleStock ? `cap ${pct(limits.maxSingleStock, 0)} of the taxable account` : undefined,
                tone: limits.maxSingleStock && c.top1 && c.top1.weight > limits.maxSingleStock ? "text-warn" : "",
              },
              { k: "Top 3", v: pct(c.top3_weight), sub: c.top3?.join(", ") },
              { k: "Top 5", v: pct(c.top5_weight) },
              { k: "Effective positions", v: num(c.effective_positions, 1), sub: c.hhi != null ? `HHI ${num(c.hhi, 3)}` : undefined },
            ]}
          />
          {r?.cagr != null ? (
            <Kv
              className="mt-4"
              rows={[
                { k: "Annual return", v: `${pct(r.cagr)} vs ${pct(r.benchmark_cagr)}` },
                { k: "Volatility", v: pct(r.volatility) },
                { k: "Sharpe, Sortino", v: `${num(r.sharpe)}, ${num(r.sortino)}` },
                { k: "Max drawdown", v: `${pct(r.max_drawdown)} vs ${pct(r.benchmark_max_drawdown)}` },
                { k: "Beta", v: num(r.beta) },
                { k: "Worst day, worst month", v: `${pct(r.worst_day)}, ${pct(r.worst_month)}` },
                { k: "Average pairwise correlation", v: num(r.avg_pairwise_correlation) },
              ]}
            />
          ) : (
            <Empty>Risk statistics unavailable{r?.error ? `: ${r.error}` : ""}.</Empty>
          )}
        </Section>
      </div>

      <Section title="Positions" description="by account, largest first" className="mt-4">
        <PositionsTable groups={byAccount} etf={etf} />
      </Section>

      <div className="grid gap-4 xl:grid-cols-2">
        <Section title="Drift from targets" description="asset class vs profile target">
          {dr && Object.keys(dr).length ? (
            <div className="space-y-4">
              {Object.entries(dr).map(([acct, rows]) => (
                <div key={acct}>
                  <div className="mb-1 text-xs font-medium text-secondary">{accountLabel(acct)}</div>
                  <table className="tbl">
                    <tbody>
                      {rows.map((row) => (
                        <tr key={row.asset_class}>
                          <td>{humanize(row.asset_class)}</td>
                          <td className="num">{pct(row.current)}</td>
                          <td className="num hidden text-muted sm:table-cell">target {pct(row.target, 0)}</td>
                          <td className="w-16 sm:w-24">
                            <DriftMark drift={row.drift} />
                          </td>
                          <td className={`num ${Math.abs(row.drift) > 0.05 ? "text-warn" : "text-secondary"}`}>{signed(row.drift, (x) => pct(x))}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ))}
            </div>
          ) : (
            <Empty>Set targets in config/profile.yml to see drift.</Empty>
          )}
        </Section>

        <Section title="Taxable gains by term" description="taxable accounts">
          {tax?.available && tax.totals ? (
            <>
              <Kv
                rows={[
                  { k: "Short-term gain", v: money(tax.totals.st_gain), tone: tone(tax.totals.st_gain) },
                  { k: "Long-term gain", v: money(tax.totals.lt_gain), tone: tone(tax.totals.lt_gain) },
                  { k: "Long-term share", v: pct(tax.totals.lt_share_of_gain) },
                  { k: "Lots crossing to long-term in 30 days", v: String(tax.crossing_to_lt?.length ?? 0) },
                  { k: "Harvestable losers", v: String(tax.harvestable?.length ?? 0) },
                ]}
              />
              {tax.crossing_to_lt?.length ? (
                <ul className="mt-3 space-y-1 text-[13px]">
                  {tax.crossing_to_lt.map((x) => (
                    <li key={`${x.symbol}-${x.lt_on}`} className="flex justify-between">
                      <span>
                        <Symbol>{x.symbol}</Symbol> {num(x.quantity, 3)} shares
                      </span>
                      <span className="text-secondary">long-term on {dateShort(x.lt_on)}</span>
                    </li>
                  ))}
                </ul>
              ) : null}
              {tax.by_symbol?.length ? (
                <div className="mt-3">
                  <ShowMore
                    preview={null}
                    rest={
                      <div className="overflow-x-auto">
                      <table className="tbl min-w-[420px]">
                        <thead>
                          <tr>
                            <th>Symbol</th>
                            <th className="num">ST shares</th>
                            <th className="num">ST gain</th>
                            <th className="num">LT shares</th>
                            <th className="num">LT gain</th>
                          </tr>
                        </thead>
                        <tbody>
                          {[...tax.by_symbol]
                            .sort((a, b) => b.lt_gain + b.st_gain - (a.lt_gain + a.st_gain))
                            .map((s) => (
                              <tr key={s.symbol}>
                                <td>
                                  <Symbol>{s.symbol}</Symbol>
                                </td>
                                <td className="num">{num(s.st_shares, 2)}</td>
                                <td className={`num ${tone(s.st_gain)}`}>{signed(s.st_gain, (x) => money(x))}</td>
                                <td className="num">{num(s.lt_shares, 2)}</td>
                                <td className={`num ${tone(s.lt_gain)}`}>{signed(s.lt_gain, (x) => money(x))}</td>
                              </tr>
                            ))}
                        </tbody>
                      </table>
                      </div>
                    }
                    moreLabel="Show by symbol"
                    lessLabel="Hide by symbol"
                  />
                </div>
              ) : null}
              {tax.approximate ? <Note>Approximate until a weekly run pulls every lot.</Note> : null}
            </>
          ) : (
            <Empty>Tax lots arrive with the weekly run.</Empty>
          )}
        </Section>
      </div>

      <Section title="Weekly deep dive" description="optimizer, tear sheet, correlations" className="mt-4">
        {opt?.current ? (
          <div className="overflow-x-auto">
          <table className="tbl min-w-[640px]">
            <thead>
              <tr>
                <th>Portfolio</th>
                <th className="num">Expected return</th>
                <th className="num">Volatility</th>
                <th className="num">Sharpe</th>
                <th>Largest weights</th>
              </tr>
            </thead>
            <tbody>
              {(["current", "min_vol", "max_sharpe"] as const).map((k) => {
                const o = opt[k];
                if (!o) return null;
                return (
                  <tr key={k}>
                    <td>{k === "current" ? "Current" : k === "min_vol" ? "Minimum volatility" : "Maximum Sharpe"}</td>
                    <td className="num">{pct(o.expected_return)}</td>
                    <td className="num">{pct(o.volatility)}</td>
                    <td className="num">{num(o.sharpe)}</td>
                    <td className="text-xs text-secondary">
                      {Object.entries(o.weights)
                        .sort((a, b) => b[1] - a[1])
                        .slice(0, 6)
                        .map(([s, w]) => `${s} ${(w * 100).toFixed(0)}%`)
                        .join(", ")}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          </div>
        ) : (
          <Empty>Runs with the weekly deep dive on Sundays.</Empty>
        )}
        {art.tearsheet || art.heatmap ? (
          <div className="mt-3 flex flex-wrap gap-4 text-[13px]">
            {art.tearsheet ? (
              <TextLink href="/api/asset?name=tearsheet.html" external>
                Tear sheet
              </TextLink>
            ) : null}
            {art.heatmap ? (
              <TextLink href="/api/asset?name=correlation.png" external>
                Correlation heatmap
              </TextLink>
            ) : null}
          </div>
        ) : null}
      </Section>
    </>
  );
}

function DriftMark({ drift }: { drift: number }) {
  const max = 0.3;
  const share = Math.max(-1, Math.min(1, drift / max));
  const cls = Math.abs(drift) > 0.05 ? "bg-warn" : "bg-secondary";
  return (
    <span className="relative block h-1.5 w-full rounded-full bg-panel-2" aria-hidden="true">
      <span className="absolute left-1/2 top-0 h-full w-px bg-muted" />
      <span
        className={`absolute top-0 h-full rounded-full ${cls}`}
        style={share >= 0 ? { left: "50%", width: `${share * 50}%` } : { right: "50%", width: `${-share * 50}%` }}
      />
    </span>
  );
}

const PREVIEW = 8;

function PositionsTable({
  groups,
  etf,
}: {
  groups: { account: string; value: number; cost: number; gain: number; gain_pct: number | null; share_of_total: number; positions: Position[] }[];
  etf: Record<string, string>;
}) {
  const head = (
    <tr>
      <th>Symbol</th>
      <th className="num">Quantity</th>
      <th className="num">Price</th>
      <th className="num">Value</th>
      <th className="num">Weight</th>
      <th className="num">Cost</th>
      <th className="num">Gain</th>
      <th className="num">Gain %</th>
    </tr>
  );
  const row = (x: Position) => (
    <tr key={`${x.account}-${x.symbol}`}>
      <td>
        <Symbol>{x.symbol}</Symbol>
        {etf[x.symbol] ? <span className="ml-1.5 text-xs text-muted">{etf[x.symbol]}</span> : null}
      </td>
      <td className="num text-secondary">{num(x.quantity, 3)}</td>
      <td className="num">{money(x.price, 2)}</td>
      <td className="num">{money(x.value)}</td>
      <td className="num">
        <InlineBar share={x.weight_total / 0.25} className="mr-2 w-12" />
        {pct(x.weight_total)}
      </td>
      <td className="num text-secondary">{money(x.cost)}</td>
      <td className={`num ${tone(x.gain)}`}>{signed(x.gain, (v) => money(v))}</td>
      <td className={`num ${tone(x.gain_pct)}`}>{pct(x.gain_pct)}</td>
    </tr>
  );
  const groupRow = (g: (typeof groups)[number]) => (
    <tr key={`${g.account}-g`} className="subtotal">
      <td>{accountLabel(g.account)}</td>
      <td className="num text-secondary">{plural(g.positions.length, "position")}</td>
      <td />
      <td className="num">{money(g.value)}</td>
      <td className="num">{pct(g.share_of_total)}</td>
      <td className="num text-secondary">{money(g.cost)}</td>
      <td className={`num ${tone(g.gain)}`}>{signed(g.gain, (v) => money(v))}</td>
      <td className={`num ${tone(g.gain_pct)}`}>{pct(g.gain_pct)}</td>
    </tr>
  );
  const hidden = groups.reduce((n, g) => n + Math.max(0, g.positions.length - PREVIEW), 0);
  const preview = <tbody>{groups.flatMap((g) => [groupRow(g), ...g.positions.slice(0, PREVIEW).map(row)])}</tbody>;
  const rest = (
    <tbody>
      {groups.flatMap((g) =>
        g.positions.length > PREVIEW
          ? [
              <tr key={`${g.account}-more`} className="group">
                <td colSpan={8}>{accountLabel(g.account)}, remaining positions</td>
              </tr>,
              ...g.positions.slice(PREVIEW).map(row),
            ]
          : [],
      )}
    </tbody>
  );
  return (
    <div>
      {hidden > 0 ? (
        <ShowMore head={head} preview={preview} rest={rest} moreLabel={`Show all ${groups.reduce((n, g) => n + g.positions.length, 0)} positions`} lessLabel="Show largest only" wrapClassName="overflow-x-auto" tableClassName="tbl min-w-[720px]" />
      ) : (
        <div className="overflow-x-auto">
          <table className="tbl min-w-[720px]">
            <thead>{head}</thead>
            {preview}
          </table>
        </div>
      )}
    </div>
  );
}
