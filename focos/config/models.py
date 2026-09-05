"""Pydantic models for every config file (v2 layout).

Profile-style files allow extra keys so free-form notes survive; structural files are strict enough for
the wizard and `focos doctor` to catch mistakes.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Role = Literal["taxable", "roth_ira", "traditional_ira", "401k", "hsa", "529", "sandbox", "other"]
ROLES: tuple[str, ...] = ("taxable", "roth_ira", "traditional_ira", "401k", "hsa", "529", "sandbox", "other")
HOUSEHOLD = "personal"
AccountTypeName = Literal["depository", "credit_card", "loan", "investment", "property", "vehicle", "other"]


class _Lenient(BaseModel):
    model_config = ConfigDict(extra="allow")


def _compile(pattern: str | None, where: str) -> None:
    if pattern is None:
        return
    try:
        re.compile(pattern)
    except re.error as e:
        raise ValueError(f"{where}: invalid regex {pattern!r}: {e}") from e


# ---------------------------------------------------------------- focos.yml
class SureSettings(_Lenient):
    api_url: str = "http://127.0.0.1:3000"
    autostart_docker: bool = False
    compose_dir: str | None = None


class LedgerSettings(_Lenient):
    provider: Literal["simplefin", "sure", "none"] = "simplefin"
    refresh_min_hours: float = 20
    history_days_initial: int = 365
    sure: SureSettings = SureSettings()


class HoldingsSettings(_Lenient):
    source: Literal["robinhood_mcp", "simplefin_holdings", "csv", "none"] = "none"


class BudgetSettings(_Lenient):
    daily: float = 1.0
    weekly: float = 3.0
    monthly: float = 4.0
    interview: float = 1.0


class AISettings(_Lenient):
    mode: Literal["api", "agent"] = "api"
    provider: Literal["anthropic", "openai", "gemini", "ollama"] = "anthropic"
    model: str | None = None
    model_heavy: str | None = None
    base_url: str | None = None
    max_output_tokens: int = 8192
    max_input_tokens: int = 60000
    temperature: float = 0.2
    budget_usd: BudgetSettings = BudgetSettings()


class AgentBudget(_Lenient):
    snapshot: float = 3.0
    daily: float = 5.0
    weekly: float = 10.0
    monthly: float = 12.0


class AgentSettings(_Lenient):
    claude_cli: str = "auto"
    sandbox_enabled: bool = False
    model_snapshot: str = "sonnet"
    model_daily: str = "sonnet"
    model_heavy: str = "opus"
    budget_usd: AgentBudget = AgentBudget()


def _coerce_time(v):
    if isinstance(v, int) and not isinstance(v, bool):
        return f"{v // 60:02d}:{v % 60:02d}"
    return v


class DailySchedule(_Lenient):
    days: Literal["weekdays", "daily"] = "weekdays"
    time: str = "16:35"
    _t = field_validator("time", mode="before")(_coerce_time)


class WeeklySchedule(_Lenient):
    day: Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"] = "sun"
    time: str = "18:00"
    _t = field_validator("time", mode="before")(_coerce_time)


class MonthlySchedule(_Lenient):
    day: int = Field(default=1, ge=1, le=28)
    time: str = "19:00"
    _t = field_validator("time", mode="before")(_coerce_time)


_TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class ScheduleSettings(_Lenient):
    daily: DailySchedule = DailySchedule()
    weekly: WeeklySchedule = WeeklySchedule()
    monthly: MonthlySchedule = MonthlySchedule()

    @model_validator(mode="after")
    def _times(self):
        for name in ("daily", "weekly", "monthly"):
            t = getattr(self, name).time
            if not _TIME.match(str(t)):
                raise ValueError(f"schedule.{name}.time must be HH:MM (24h), got {t!r}")
        return self


class GitSettings(_Lenient):
    commit_each_run: bool = True
    push: bool = False
    author_name: str | None = None      # default: the data dir's git config, else "focos <focos@localhost>"
    author_email: str | None = None
    commit_paths: list[str] = ["state", "reports", "config"]


class DashboardSettings(_Lenient):
    port: int = 3100
    api_port: int = 3101


class FocosSettings(_Lenient):
    version: int = 1
    home_label: str = "My household"
    ledger: LedgerSettings = LedgerSettings()
    holdings: HoldingsSettings = HoldingsSettings()
    ai: AISettings = AISettings()
    agent: AgentSettings = AgentSettings()
    schedule: ScheduleSettings = ScheduleSettings()
    git: GitSettings = GitSettings()
    dashboard: DashboardSettings = DashboardSettings()
    setup_completed_at: str | None = None


# ---------------------------------------------------------------- profile.yml
class Owner(_Lenient):
    name: str | None = None
    birth_year: int | None = Field(default=None, ge=1900, le=2100)
    filing_status: str | None = None
    federal_bracket_pct: float | None = Field(default=None, ge=0, le=60)
    employment: str | None = None
    cpa: bool | None = None


class Household(_Lenient):
    timezone: str = "America/New_York"
    currency: str = "USD"
    country: str = "US"
    state: str | None = None

    @field_validator("timezone")
    @classmethod
    def _tz(cls, v: str) -> str:
        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, ValueError) as e:
            raise ValueError(f"unknown timezone {v!r}") from e
        return v


class Spouse(_Lenient):
    in_household: bool = False
    employment: str | None = None
    annual_gross: float | None = None
    accounts_linked: bool = False


class IncomeSource(_Lenient):
    label: str
    kind: Literal["business", "w2", "rental", "other"] = "other"
    annual: float | None = None
    range: list[float] | None = None
    entity: str = HOUSEHOLD
    notes: str | None = None


class Income(_Lenient):
    sources: list[IncomeSource] = []
    notes: str | None = None


class Spending(_Lenient):
    monthly_core_expenses: float | None = None
    monthly_discretionary: float | None = None
    excludes_debt_payments: bool = True


class CashPolicy(_Lenient):
    emergency_fund_months: float = 3
    min_checking_buffer: float | None = None
    business_cash_is_reserve: bool = False
    notes: str | None = None


class DebtTerm(_Lenient):
    match: str
    rate_pct: float | None = None
    rate_type: Literal["fixed", "variable"] | None = None
    rate_cap_pct: float | None = None
    min_payment: float | None = None
    autopay: float | None = None
    draw_period_ends: date | None = None
    available_credit: float | None = None
    note: str | None = None

    @field_validator("match")
    @classmethod
    def _re(cls, v: str) -> str:
        _compile(v, "debt_terms.match")
        return v


class Contribution(_Lenient):
    limit: float | None = None
    ytd: float | None = None


class Retirement(_Lenient):
    target_age: float | None = None
    target_age_range: list[float] | None = None
    target_annual_spend_today_dollars: float | None = None
    contributions: dict[str, dict[str, Contribution]] = {}
    employer_plan: str | None = None
    business_plan: str | None = None


class Family(_Lenient):
    dependents: int = 0
    planning_children: bool = False
    notes: str | None = None


class Protection(_Lenient):
    term_life: bool | None = None
    will_or_trust: bool | None = None
    umbrella_liability: bool | None = None
    disability: bool | None = None


class Risk(_Lenient):
    tolerance: Literal["conservative", "moderate", "aggressive"] | None = None
    max_single_stock_weight_pct: float = 20
    max_sector_weight_pct: float = 45
    notes: str | None = None


class Profile(_Lenient):
    version: int = 2
    owner: Owner = Owner()
    household: Household = Household()
    spouse: Spouse = Spouse()
    income: Income = Income()
    spending: Spending = Spending()
    cash_policy: CashPolicy = CashPolicy()
    debts: list[dict[str, Any]] = []
    debt_terms: list[DebtTerm] = []
    retirement: Retirement = Retirement()
    family: Family = Family()
    protection: Protection = Protection()
    tax_agenda: list[str] = []
    risk: Risk = Risk()
    targets: dict[str, dict[str, float]] = {}

    @field_validator("targets")
    @classmethod
    def _target_roles(cls, v: dict[str, dict[str, float]]) -> dict[str, dict[str, float]]:
        for role in v:
            if role not in ROLES:
                raise ValueError(f"targets.{role}: unknown account role (expected one of {', '.join(ROLES)})")
        return v


# ---------------------------------------------------------------- goals.yml
GoalKind = Literal["emergency_fund", "debt_payoff", "retirement_contribution", "purchase", "custom"]


def slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return s or "goal"


class Goal(_Lenient):
    id: str | None = None
    kind: GoalKind = "custom"
    name: str
    entity: str = HOUSEHOLD
    target_amount: float | None = None
    deadline: date | None = None
    funded_by: list[str] = []
    params: dict[str, Any] = {}
    notes: str | None = None

    @model_validator(mode="after")
    def _fill_id(self):
        if not self.id:
            self.id = slug(self.name)
        if self.kind == "debt_payoff":
            _compile(self.params.get("match"), f"goals[{self.id}].params.match")
        return self


class Goals(_Lenient):
    version: int = 2
    goals: list[Goal] = []

    @model_validator(mode="after")
    def _unique(self):
        seen: set[str] = set()
        for g in self.goals:
            if g.id in seen:
                raise ValueError(f"duplicate goal id {g.id!r}")
            seen.add(g.id or "")
        return self


# ---------------------------------------------------------------- accounts.yml
class BrokerageAccount(_Lenient):
    key: str
    label: str
    role: Role = "taxable"
    entity: str = HOUSEHOLD
    source: Literal["robinhood_mcp", "simplefin_holdings", "csv"] = "csv"
    match: dict[str, Any] = {}
    agent_access: Literal["read", "trade"] = "read"
    ledger_account_id: str | None = None

    @field_validator("key")
    @classmethod
    def _key(cls, v: str) -> str:
        if not re.match(r"^[a-z][a-z0-9_]{0,39}$", v):
            raise ValueError(f"account key {v!r} must be lowercase letters, digits, underscores")
        return v

    @model_validator(mode="after")
    def _trade_only_sandbox(self):
        if self.agent_access == "trade" and self.role != "sandbox":
            raise ValueError(f"account {self.key}: agent_access 'trade' requires role 'sandbox'")
        return self


class Accounts(_Lenient):
    version: int = 2
    brokerage: list[BrokerageAccount] = []

    @model_validator(mode="after")
    def _checks(self):
        keys = [a.key for a in self.brokerage]
        dupes = {k for k in keys if keys.count(k) > 1}
        if dupes:
            raise ValueError(f"duplicate brokerage keys: {sorted(dupes)}")
        if sum(1 for a in self.brokerage if a.role == "sandbox") > 1:
            raise ValueError("at most one brokerage account may have role 'sandbox'")
        return self

    def by_role(self, role: str) -> list[str]:
        return [a.key for a in self.brokerage if a.role == role]


# ---------------------------------------------------------------- entities.yml
class Entity(_Lenient):
    label: str
    kind: Literal["household", "business", "trust", "other"] = "household"
    account_ids: list[str] = []
    name_hints: str | None = None
    color: str | None = None
    institution: str | None = None

    @field_validator("name_hints")
    @classmethod
    def _hints(cls, v: str | None) -> str | None:
        _compile(v, "entities.name_hints")
        return v


class AccountTypeOverride(_Lenient):
    type: AccountTypeName
    subtype: str | None = None
    classification: Literal["asset", "liability"] | None = None


class Entities(_Lenient):
    version: int = 2
    entities: dict[str, Entity] = {}
    corridors: list[list[str]] = []
    account_types: dict[str, AccountTypeOverride] = {}   # ledger account id -> type confirmed in the wizard

    @model_validator(mode="after")
    def _household(self):
        if HOUSEHOLD not in self.entities:
            raise ValueError(f"entities must include the household entity {HOUSEHOLD!r}")
        for pair in self.corridors:
            if len(pair) != 2 or any(p not in self.entities for p in pair):
                raise ValueError(f"corridor {pair} must name two known entities")
        return self


# ---------------------------------------------------------------- transfer_rules.yml
class TransferRule(_Lenient):
    name: str
    match: str
    direction: Literal["inflow", "outflow"] | None = None
    entity: str
    counterparty: str | None = None
    classify_as: str

    @field_validator("match")
    @classmethod
    def _re(cls, v: str) -> str:
        _compile(v, "transfer_rules.rules.match")
        return v


class IncomeLabel(_Lenient):
    label: str
    match: str | None = None
    amount: float | None = None

    @field_validator("match")
    @classmethod
    def _re(cls, v: str | None) -> str | None:
        _compile(v, "transfer_rules.income_labels.match")
        return v


class TransferRules(_Lenient):
    rules: list[TransferRule] = []
    ignore_patterns: list[str] = []
    income_labels: dict[str, list[IncomeLabel]] = {}

    @field_validator("ignore_patterns")
    @classmethod
    def _ignore(cls, v: list[str]) -> list[str]:
        for p in v:
            _compile(p, "transfer_rules.ignore_patterns")
        return v


# ---------------------------------------------------------------- sandbox_rules.yml
class SandboxRules(_Lenient):
    broker: Literal["robinhood"] = "robinhood"
    mode_default: Literal["paper", "live"] = "paper"
    warmup_runs: int = 10
    require_approval_first_n: int = 5
    budget_usd: float = 500
    budget_growth_per_week_usd: float = 0
    funded_on: date | None = None
    max_position_weight: float = Field(default=0.25, gt=0, le=1)
    max_order_usd: float = 250
    weekly_budget_usd: float = 500
    cash_floor_pct: float = Field(default=0.05, ge=0, le=1)
    max_orders_per_run: int = 2
    max_orders_per_week: int = 4
    instruments: list[Literal["stock", "etf"]] = ["stock", "etf"]
    min_price: float = 5.0
    blocklist_patterns: list[str] = []
    market_orders_only_during_rth: bool = True
    no_trading_days: list[date] = []

    @field_validator("blocklist_patterns")
    @classmethod
    def _bl(cls, v: list[str]) -> list[str]:
        for p in v:
            _compile(p, "sandbox_rules.blocklist_patterns")
        return v


# ---------------------------------------------------------------- analytics.yml
class Analytics(_Lenient):
    benchmark: str = "SPY"
    max_weight: float = 0.15
    years: int = 3
    weekly_years: int = 3
    monthly_years: int = 5
    big_move_pct: float = 5.0
    classes: dict[str, str] = {}
    etf_labels: dict[str, str] = {}


# ---------------------------------------------------------------- properties.yml
class Property(_Lenient):
    key: str
    name: str
    address: str | None = None
    entity: str = HOUSEHOLD
    source: Literal["zillow", "manual"] = "manual"
    zpid: str | int | None = None
    ledger_account_id: str | None = None
    sure_account_id: str | None = None
    linked_loan: str | None = None
    last_value: float | None = None
    last_rent_estimate: float | None = None
    last_refreshed: str | None = None
    manual_value: float | None = None


class Properties(_Lenient):
    properties: list[Property] = []


MODELS: dict[str, type[BaseModel]] = {
    "focos.yml": FocosSettings,
    "profile.yml": Profile,
    "goals.yml": Goals,
    "accounts.yml": Accounts,
    "entities.yml": Entities,
    "transfer_rules.yml": TransferRules,
    "sandbox_rules.yml": SandboxRules,
    "analytics.yml": Analytics,
    "properties.yml": Properties,
}
