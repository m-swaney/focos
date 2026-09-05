import { PercentileRange } from "@/components/charts/PercentileRange";
import { Empty, EntityDot, Figure, FigureStrip, Meter, Note, PageHeader, Section, TextLink } from "@/components/ui";
import { Icon } from "@/components/ui/Icon";
import { plan } from "@/lib/data/latest";
import { dateShort, humanize, money, moneyCompact, num, pct } from "@/lib/format";

export const dynamic = "force-dynamic";

const INCOME_LABELS: Record<string, string> = { spouse_w2: "Spouse W-2", other_w2: "Other W-2" };

export default function PlanPage() {
  const p = plan();
  if (!p?.available) {
    return (
      <>
        <PageHeader title="Plan" />
        <Empty>The plan is computed by the daily pipeline from config/profile.yml, the ledger, and the portfolio. Run it to see this page.</Empty>
      </>
    );
  }
  const s = p.savings;
  const ef = p.emergency_fund;
  const r = p.retirement;
  const goals = [...(p.goals ?? [])].sort((a, b) => (a.deadline ?? "9999").localeCompare(b.deadline ?? "9999"));
  const gaps = p.protection?.gaps ?? [];

  const flows = s
    ? [
        { key: "spend", label: "Core spending", value: s.annual_spend, color: "var(--dim)" },
        { key: "debt", label: "Debt service", value: s.known_debt_service, color: "var(--dim)" },
        { key: "tax", label: "Income tax", value: s.est_income_tax, color: "var(--dim)" },
        { key: "surplus", label: "After-tax surplus", value: s.after_tax_surplus_est, color: "var(--series-1)" },
      ].filter((f) => f.value > 0)
    : [];
  const flowTotal = flows.reduce((n, f) => n + f.value, 0);

  return (
    <>
      <PageHeader title="Plan" sub="arithmetic on your profile, ledger, and portfolio" />

      {p.missing?.length ? (
        <p className="mb-8 flex items-start gap-2 rounded-[8px] bg-wash-warn px-3 py-2 text-[13px] text-warn">
          <Icon name="warn" size={14} className="mt-0.5" />
          <span>
            Fill in <code className="rounded bg-panel-2 px-1 text-ink">config/profile.yml</code> to unlock more: {p.missing.join("; ")}.
          </span>
        </p>
      ) : null}

      <FigureStrip className="mb-4">
        <Figure size="lg" label="Savings rate" value={s ? pct(s.savings_rate, 0) : "n/a"} sub={s ? `${money(s.annual_income)} income, ${money(s.annual_spend)} core spending` : "needs income and spending"} />
        <Figure label="After-tax surplus" value={s ? money(s.after_tax_surplus_est) : "n/a"} sub="per year, estimated" />
        <Figure
          label="Emergency fund"
          value={ef ? `${num(ef.months_covered, 1)} mo` : "n/a"}
          sub={ef ? `target ${ef.target_months} months, ${num(ef.months_covered_incl_business ?? 0, 1)} with business cash` : "needs bank accounts and core expenses"}
          tone={ef && ef.months_covered < ef.target_months ? "text-warn" : ""}
        />
        <Figure
          label="Roth IRA this year"
          value={p.roth ? money(p.roth.contributed) : "n/a"}
          sub={p.roth ? (p.roth.remaining > 0 ? `${money(p.roth.remaining)} to the ${money(p.roth.limit)} limit, ${money(p.roth.monthly_to_max)} a month` : "maxed for the year") : "needs roth_contributed_this_year"}
          tone={p.roth && !p.roth.on_pace ? "text-warn" : ""}
        />
        {r?.probability_hit_target != null ? (
          <Figure label="Chance of hitting the retirement target" value={pct(r.probability_hit_target, 0)} sub={`${money(r.target_nest_egg_4pct_rule)} by age ${r.target_age}`} tone={r.probability_hit_target >= 0.75 ? "" : "text-warn"} />
        ) : null}
      </FigureStrip>

      <Section
        title="Retirement outcome"
        description={r ? `real wealth at age ${r.target_age}, ${r.years_to_target} years out; bands are the middle 50% and 80%` : undefined}
      >
        {r ? (
          <>
            <PercentileRange p={r.real_wealth_percentiles} target={r.target_nest_egg_4pct_rule} format={moneyCompact} height={84} />
            <table className="tbl mt-2 max-w-[560px]">
              <tbody>
                <tr>
                  <td className="text-secondary">Pessimistic (10th percentile)</td>
                  <td className="num">{money(r.real_wealth_percentiles.p10)}</td>
                </tr>
                <tr>
                  <td className="text-secondary">Median</td>
                  <td className="num">{money(r.real_wealth_percentiles.p50)}</td>
                </tr>
                <tr>
                  <td className="text-secondary">Optimistic (90th percentile)</td>
                  <td className="num">{money(r.real_wealth_percentiles.p90)}</td>
                </tr>
                {r.target_nest_egg_4pct_rule ? (
                  <tr>
                    <td className="text-secondary">Target by the 4% rule</td>
                    <td className="num">{money(r.target_nest_egg_4pct_rule)}</td>
                  </tr>
                ) : null}
              </tbody>
            </table>
            <Note>
              Starts from {money(r.starting_investable)} invested, assumes {pct(r.assumed_return)} return with {pct(r.assumed_vol)} volatility and {money(r.annual_contribution_assumed)} contributed per year. {r.note}
            </Note>
          </>
        ) : (
          <Empty>Needs birth_year and retirement.target_age in config/profile.yml.</Empty>
        )}
      </Section>

      <div className="grid gap-4 md:grid-cols-2">
        <Section title="Where the income goes" description="annual, estimated">
          {s ? (
            <>
              <div className="flex h-3 w-full gap-0.5 overflow-hidden rounded-full" role="img" aria-label="Split of household income">
                {flows.map((f) => (
                  <div key={f.key} style={{ width: `${(f.value / flowTotal) * 100}%`, background: f.color }} title={`${f.label} ${money(f.value)}`} />
                ))}
              </div>
              <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
                {flows.map((f) => (
                  <span key={f.key} className="inline-flex items-center gap-1.5">
                    <span className="inline-block h-2 w-2 rounded-full" style={{ background: f.color }} /> {f.label} {pct(f.value / flowTotal, 0)}
                  </span>
                ))}
              </div>
              <table className="tbl mt-4">
                <tbody>
                  {Object.entries(s.income_breakdown ?? {})
                    .filter(([, v]) => v)
                    .map(([label, v]) => (
                      <tr key={label}>
                        <td className="text-secondary">{INCOME_LABELS[label] ?? label}</td>
                        <td className="num">{money(v)}</td>
                      </tr>
                    ))}
                  <tr>
                    <td className="text-secondary">Core spending</td>
                    <td className="num">-{money(s.annual_spend)}</td>
                  </tr>
                  <tr>
                    <td className="text-secondary">
                      Debt service
                      {s.debt_service_source ? <div className="text-xs text-muted">{s.debt_service_source}</div> : null}
                    </td>
                    <td className="num">-{money(s.known_debt_service)}</td>
                  </tr>
                  <tr>
                    <td className="text-secondary">Income tax, rough</td>
                    <td className="num">-{money(s.est_income_tax)}</td>
                  </tr>
                  <tr className="subtotal">
                    <td>After-tax surplus</td>
                    <td className={`num ${s.after_tax_surplus_est > 0 ? "text-gain" : "text-loss"}`}>{money(s.after_tax_surplus_est)}</td>
                  </tr>
                </tbody>
              </table>
              {s.note ? <Note>{s.note}</Note> : null}
              {p.debts ? (
                <p className="mt-3 text-[13px] text-secondary">
                  Debts total {money(p.debts.total)}, costing {money(p.debts.annual_interest)} a year in interest. <TextLink href="/wealth">See the schedule on Wealth</TextLink>
                </p>
              ) : null}
            </>
          ) : (
            <Empty>Needs income and spending in config/profile.yml.</Empty>
          )}
        </Section>

        <div className="space-y-4">
          <Section title="Goals" description="soonest deadline first">
            {goals.length ? (
              <ul className="divide-y divide-hairline">
                {goals.map((g) => (
                  <li key={g.id} className="py-2.5 text-[13px]">
                    <div className="flex items-baseline justify-between gap-4">
                      <span className="inline-flex items-center gap-2">
                        {g.entity ? <EntityDot entityKey={g.entity} /> : null}
                        {g.name}
                      </span>
                      <span className="shrink-0 text-xs text-secondary">{g.deadline ? dateShort(g.deadline) + ", " + g.deadline.slice(0, 4) : "no deadline"}</span>
                    </div>
                    {g.target ? (
                      <div className="mt-1.5 flex items-center gap-3">
                        <Meter value={g.funded ?? 0} max={g.target} className="max-w-[240px]" tone={g.progress != null && g.progress >= 1 ? "gain" : "series"} />
                        <span className="text-xs text-secondary">
                          {money(g.funded ?? 0)} of {money(g.target)}
                          {g.progress != null ? ` (${pct(g.progress, 0)})` : ""}
                        </span>
                      </div>
                    ) : (
                      <div className="mt-1 text-xs text-muted">No target amount set</div>
                    )}
                  </li>
                ))}
              </ul>
            ) : (
              <Empty>No goals yet. Add them to config/goals.yml.</Empty>
            )}
          </Section>

          <Section title="Protection" description={p.protection ? `${humanize(p.protection.priority ?? "")} priority${p.protection.planning_children ? ", children planned" : ""}.` : undefined}>
            {gaps.length ? (
              <ul className="space-y-1.5 text-[13px]">
                {gaps.map((g) => (
                  <li key={g} className="flex items-center gap-2">
                    <span className="inline-block h-3.5 w-3.5 rounded-[4px] border border-warn" aria-hidden="true" />
                    {humanize(g)}
                    <span className="text-xs text-muted">missing</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="flex items-center gap-2 text-[13px] text-secondary">
                <Icon name="check" size={14} className="text-gain" /> No protection gaps listed.
              </p>
            )}
          </Section>

          {p.tax_agenda?.length ? (
            <Section title="Agenda for the CPA">
              <ol className="ml-5 list-decimal space-y-1.5 text-[13px] marker:text-muted">
                {p.tax_agenda.map((t, i) => (
                  <li key={i}>{t}</li>
                ))}
              </ol>
            </Section>
          ) : null}
        </div>
      </div>
    </>
  );
}
