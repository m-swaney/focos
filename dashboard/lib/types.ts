export type EntityKey = string;
export type AccountKey = string;
export type Severity = "info" | "warn" | "critical";
export type Mode = "daily" | "weekly" | "monthly";

export interface BrokerPortfolio {
  total_value: number;
  equity_value?: number;
  options_value?: number;
  crypto_value?: number;
  cash?: number;
  buying_power?: number;
  pending_deposits?: number;
}

export interface Position {
  account: AccountKey;
  symbol: string;
  quantity: number;
  avg_cost?: number;
  price: number;
  value: number;
  cost: number;
  gain: number;
  gain_pct: number | null;
  weight_account: number;
  weight_total: number;
}

export interface Portfolio {
  meta: {
    asof: string;
    years?: number;
    mode?: Mode;
    prices_stale?: boolean;
    benchmark?: string;
    total_value: number;
    total_cost: number;
    broker_total_value?: number;
    broker_accounts?: Record<AccountKey, BrokerPortfolio>;
    valuation_note?: string;
  };
  accounts: { account: AccountKey; value: number; cost: number; gain: number; gain_pct: number | null; share_of_total: number }[];
  positions: Position[];
  concentration: {
    top1?: { symbol: string; weight: number };
    top3?: string[];
    top3_weight?: number;
    top5_weight?: number;
    hhi?: number;
    effective_positions?: number;
    weights?: Record<string, number>;
  };
  look_through: Record<string, { value: number; weight: number }>;
  sectors: Record<string, { value: number; weight: number }>;
  class_weights?: Record<AccountKey, Record<string, number>>;
}

export interface EntitySummary {
  label: string;
  net_worth: number;
  assets: number;
  liabilities: number;
  cash: number;
  n_accounts: number;
}

export interface InterEntityFlow {
  date: string;
  from_entity: EntityKey;
  to_entity: EntityKey;
  amount: number;
  name: string;
  pair_id: string;
  label?: string;
  one_legged?: boolean;
}

export interface UnmatchedTxn {
  id: string;
  date: string;
  entity: EntityKey;
  amount: number;
  name: string;
}

export interface CashFlowEntity {
  income: number;
  expense: number;
  net: number;
  inter_in: number;
  inter_out: number;
  n_transactions?: number;
  n_transfers?: number;
  income_by_label?: Record<string, number>;
  expense_by_category?: Record<string, number>;
  core_expense?: number;
  discretionary_expense?: number;
  uncategorized_expense?: number;
}

export interface SpendingSummary {
  observed_monthly_core_30d?: number;
  observed_monthly_core_90d?: number;
  observed_monthly_discretionary_90d?: number;
  observed_monthly_expense_90d?: number;
  coverage_pct_90d?: number | null;
  history_days?: number;
  configured_monthly_core?: number | null;
  configured_monthly_discretionary?: number | null;
  configured_source?: "user" | "observed" | null;
  observed_asof?: string | null;
  by_category_90d?: Record<string, number>;
  top_uncategorized?: { merchant_key: string; display_name: string; total: number; n: number; sample?: string }[];
  refine?: { eligible?: boolean; reason?: string | null; applied?: string[]; candidates?: Record<string, { observed: number; configured: number; status: string }>; error?: string };
}

export interface CashFlowWindow {
  per_entity: Record<EntityKey, CashFlowEntity>;
  consolidated: { income: number; expense: number; net: number; expense_by_category?: Record<string, number>; core_expense?: number; discretionary_expense?: number; uncategorized_expense?: number };
  inter_entity_flows: InterEntityFlow[];
  unmatched: UnmatchedTxn[];
  counts?: { total: number; transfers: number; unmatched: number };
}

export interface Consolidated {
  available: boolean;
  reason?: string;
  asof?: string;
  net_worth?: number;
  assets?: number;
  liabilities?: number;
  by_entity?: Record<EntityKey, EntitySummary>;
  cash_flow?: Partial<Record<"30d" | "90d", CashFlowWindow>>;
  spending?: SpendingSummary;
  categorize?: { rules_applied?: number; seeded?: number; asked?: number; labeled?: number; low_confidence?: number; skipped?: string | null; provider?: string | null; error?: string | null };
  personal_runway_months?: number | null;
  unmapped_accounts?: { id: string; name: string }[];
  broker_in_ledger?: boolean;
  ledger_sync?: { provider?: string; last_success?: string | null; last_error?: string | null; accounts?: number };
  pushed_valuations?: { account: AccountKey; amount: number; ok: boolean }[];
}

export interface Order {
  account: AccountKey;
  id: string;
  symbol: string;
  side: "buy" | "sell";
  state: string;
  quantity: number;
  average_price: number | null;
  created_at: string;
}

export interface Diff {
  date: string;
  previous_date?: string | null;
  total_value: number;
  total_change: number | null;
  accounts: {
    account: AccountKey;
    value: number;
    previous_value: number | null;
    change: number | null;
    change_pct: number | null;
    cash: number;
    cash_change: number | null;
  }[];
  new_positions: { account: AccountKey; symbol: string; quantity: number; value: number }[];
  closed_positions: { account: AccountKey; symbol: string; quantity: number }[];
  quantity_changes: { account: AccountKey; symbol: string; from: number; to: number }[];
  movers: { account: AccountKey; symbol: string; day_change_pct: number; value: number; value_change: number }[];
  orders: Order[];
}

export type Drift = Record<AccountKey, { asset_class: string; target: number; current: number; drift: number }[]>;

export interface LedgerAccount {
  id: string;
  name: string;
  type: string;
  subtype: string | null;
  classification: "asset" | "liability";
  balance: number;
  institution?: string | null;
  source: string;
}

export interface Entities {
  asof: string;
  entities: Record<
    EntityKey,
    { label: string; assets: number; liabilities: number; net_worth: number; cash: number; accounts: LedgerAccount[]; unmapped?: boolean }
  >;
  corridors?: string[];
}

export interface OptPortfolio {
  expected_return: number;
  volatility: number;
  sharpe: number;
  weights: Record<string, number>;
}

export interface Optimizer {
  available?: boolean;
  current?: OptPortfolio;
  min_vol?: OptPortfolio;
  max_sharpe?: OptPortfolio;
}

export interface Percentiles {
  p10: number;
  p25: number;
  p50: number;
  p75: number;
  p90: number;
}

export interface Debt {
  name: string;
  entity: EntityKey;
  balance: number;
  rate_pct: number | null;
  annual_interest: number | null;
  min_payment?: number | null;
  kind?: string;
  source?: string;
  payoff_vs_invest?: string;
}

export type GoalStatus = "active" | "done" | "paused";

export interface Goal {
  id: string;
  name: string;
  entity?: EntityKey;
  target: number | null;
  funded: number | null;
  progress: number | null;
  deadline: string | null;
  status?: GoalStatus;
  completed_on?: string | null;
}

export interface TaxAgendaItem {
  id: string;
  text: string;
  status?: "open" | "done" | "dropped";
  added_on?: string | null;
  done_on?: string | null;
  notes?: string | null;
}

export interface Plan {
  asof?: string;
  available: boolean;
  missing?: string[];
  savings?: {
    annual_income: number;
    income_breakdown?: Record<string, number>;
    annual_spend: number;
    est_income_tax: number;
    known_debt_service: number;
    debt_service_source?: string;
    savings_rate: number;
    after_tax_surplus_est: number;
    note?: string;
  };
  protection?: { gaps: string[]; planning_children?: boolean; priority?: string };
  tax_agenda?: (TaxAgendaItem | string)[];
  goals_summary?: { active: number; done: number; paused: number };
  emergency_fund?: {
    cash: number;
    months_covered: number;
    target_months: number;
    gap?: number;
    business_cash?: number;
    months_covered_incl_business?: number;
    note?: string;
  };
  roth?: { limit: number; contributed: number; remaining: number; on_pace: boolean; monthly_to_max: number };
  debts?: { total: number; annual_interest?: number; rates_missing?: string[]; items: Debt[] };
  retirement?: {
    years_to_target: number;
    target_age: number;
    starting_investable?: number;
    assumed_return: number;
    assumed_vol: number;
    annual_contribution_assumed: number;
    real_wealth_percentiles: Percentiles;
    target_nest_egg_4pct_rule?: number | null;
    probability_hit_target?: number | null;
    note?: string;
  } | null;
  goals?: Goal[];
}

export interface Property {
  key: string;
  name: string;
  entity: EntityKey;
  source: string;
  zestimate?: number | null;
  rent_zestimate?: number | null;
  tax_assessed_value?: number | null;
  last_sold_price?: number | null;
  bedrooms?: number | null;
  bathrooms?: number | null;
  living_area?: number | null;
  year_built?: number | null;
  value: number;
  pushed?: boolean;
}

export interface Properties {
  asof: string;
  total_value: number;
  properties: Property[];
}

export interface Risk {
  available?: boolean;
  error?: string;
  cagr?: number;
  benchmark_cagr?: number;
  volatility?: number;
  sharpe?: number;
  sortino?: number;
  max_drawdown?: number;
  benchmark_max_drawdown?: number;
  beta?: number;
  worst_day?: number;
  worst_month?: number;
  days?: number;
  start?: string;
  end?: string;
  avg_pairwise_correlation?: number;
  artifacts?: { heatmap?: string; tearsheet?: string };
}

export interface Proposal {
  ref_id: string;
  date: string;
  symbol: string;
  side: "buy" | "sell";
  dollar_amount: number;
  thesis?: string;
  entry_reason?: string;
  stop_loss?: number | string;
  exit_plan?: string;
  horizon_days?: number;
  paper?: boolean;
  approved?: boolean;
  _file?: string;
}

export interface ScorecardPosition {
  ref_id: string;
  symbol: string;
  fill_date: string;
  fill_price: number;
  current_price: number;
  return_pct: number;
  spy_return_pct: number;
  alpha_pct: number;
  status: string;
}

export interface Sandbox {
  mode: "paper" | "live";
  killed: boolean;
  run_count: number;
  warmup_runs: number;
  warmup_remaining: number;
  trading_enabled: boolean;
  live_orders?: number;
  rules?: Record<string, number | string | string[] | number[]>;
  account?: {
    last4?: string;
    portfolio?: BrokerPortfolio;
    positions?: {
      symbol: string;
      quantity: number;
      avg_cost?: number;
      price?: number;
      value: number;
      day_change_pct?: number | null;
      sellable?: boolean;
    }[];
    recent_orders?: Omit<Order, "account">[];
  };
  proposals?: Proposal[];
  scorecard?: {
    available: boolean;
    asof?: string;
    n_positions: number;
    hit_rate: number | null;
    beat_spy_rate: number | null;
    avg_return_pct: number | null;
    avg_alpha_pct: number | null;
    total_pnl_usd: number | null;
    positions: ScorecardPosition[];
  };
}

export interface Alert {
  severity: Severity;
  code: string;
  text: string;
}

export interface Alerts {
  date: string;
  alerts: Alert[];
  tokens?: {
    available: boolean;
    robinhood_access_expires?: string | null;
    robinhood_has_refresh?: boolean;
    claude_access_expires?: string | null;
    claude_refresh_expires?: string | null;
    subscription?: string | null;
    keepalive?: { ts?: string; date?: string; ok: boolean; auth_error?: boolean; refreshed?: boolean; error?: string | null } | null;
  };
}

export interface BriefResult {
  date: string;
  mode?: Mode;
  summary_line?: string;
  report_path?: string;
  alerts?: { severity: Severity; text: string }[];
  needs_user?: string[];
  decisions_logged?: number;
  updates_applied?: number;
  proposals?: string[];
  trades_placed?: string[];
  _meta?: { duration_ms?: number; num_turns?: number };
}

export interface Catalysts {
  date: string;
  earnings: { symbol: string; date: string; time?: string }[];
  news: { symbol: string; title: string; source: string; published_at: string; url: string | null }[];
}

export interface SnapshotSummary {
  date: string;
  captured_at?: string;
  total_value: number;
  accounts: { key: AccountKey; last4?: string; type?: string; agentic_allowed?: boolean; portfolio: BrokerPortfolio; n_positions?: number }[];
}

export interface TaxLots {
  available: boolean;
  approximate?: boolean;
  by_symbol?: { symbol: string; st_shares: number; st_cost: number; lt_shares: number; lt_cost: number; st_gain: number; lt_gain: number }[];
  crossing_to_lt?: { symbol: string; quantity: number; gain: number; lt_on: string }[];
  harvestable?: { symbol: string; quantity: number; loss: number; lots: number }[];
  totals?: { st_gain: number; lt_gain: number; lt_share_of_gain: number | null };
}

export interface StageStatus {
  ok: boolean;
  error?: string | null;
  at?: string;
  duration_ms?: number;
}

export interface RunStatus {
  run_id?: string;
  started?: string;
  finished?: string | null;
  ok: boolean | null;
  stage?: string;
  error?: string | null;
  stages?: Partial<Record<"A" | "B" | "C", StageStatus>>;
  summary_line?: string;
  report_path?: string;
  commit?: string;
}

export type Status = Partial<Record<Mode, RunStatus>>;

export interface IntradayMover {
  symbol: string;
  account: string;
  quantity: number;
  price: number;
  value: number;
  day_change_pct: number | null;
  value_change: number;
  big?: boolean;
}

/** state/cache/intraday.json: the daily snapshot re-priced from delayed quotes between runs. */
export interface Intraday {
  available: boolean;
  reason?: string;
  asof?: string;
  source?: string;
  stale?: boolean;
  delayed_minutes?: number;
  snapshot_date?: string;
  snapshot_captured_at?: string;
  snapshot_total_value?: number;
  total_value?: number;
  change_since_snapshot?: number;
  day_change?: number;
  day_change_pct?: number | null;
  big_move_pct?: number;
  accounts?: { key: string; equity_value: number; total_value: number; change_since_snapshot: number }[];
  movers?: IntradayMover[];
  positions?: IntradayMover[];
  symbols?: number;
  priced?: number;
  skipped?: string[];
  midday?: { date?: string; ok?: boolean; error?: string | null; ts?: string; pull?: Record<string, unknown> | null } | null;
}

export interface Decision {
  id?: string;
  date: string;
  run?: string;
  kind?: string;
  text: string;
  evidence?: string;
  review_on?: string | null;
  /** resolution lines only */
  ref?: string;
  status?: string;
  by?: string;
}

export interface InboxNote {
  id: string;
  ts: string;
  source?: string;
  text: string;
  about?: { type: string; id?: string } | null;
  status: "pending" | "consumed" | "applied" | "answered" | "dismissed";
  consumed_run?: string | null;
  consumed_count?: number;
  resolved_ts?: string | null;
  resolution?: string | null;
}

export interface ChangeRecord {
  ts: string;
  date: string;
  run: string;
  actor: "model" | "user" | "system" | string;
  target: string;
  op?: string;
  id?: string | null;
  before?: Record<string, unknown> | null;
  after?: Record<string, unknown> | null;
  reason?: string;
  source_note_id?: string | null;
  ok: boolean;
  error?: string | null;
}

export interface GateEntry {
  ts: string;
  tool: string;
  ok: boolean;
  reasons: string[];
  symbol?: string;
  side?: string;
  notional?: number;
  order?: { symbol?: string; side?: string; type?: string; dollar_amount?: number; ref_id?: string; account_last4?: string };
}

export type BriefRef = { kind: Mode; id: string; file: string; mtime: number };
