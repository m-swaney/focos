"""Forward-looking plan numbers (deterministic). Degrades to "not available" when profile fields are missing.

Produces plan.json: savings rate, emergency fund coverage, contribution pacing, debt schedule summary,
and a Monte Carlo projection of investable assets to the retirement target using the portfolio's own
backtested return/volatility (shrunk toward long-run market assumptions).

Reads the v2 profile/goals views (settings.profile_v2 / goals_v2) so v1 data dirs keep working.
"""
from __future__ import annotations

import re
from datetime import date

import numpy as np

from . import paths, settings
from .config.models import HOUSEHOLD

LONG_RUN_RETURN = 0.07
LONG_RUN_VOL = 0.16
SHRINK = 0.25  # weight on the portfolio's own (short, hot) history vs long-run assumptions
INFLATION = 0.025
DEFAULT_ROTH_LIMIT = 7000.0


def _num(x) -> float | None:
    try:
        return None if x is None else float(x)
    except (TypeError, ValueError):
        return None


def _liability_accounts(entities: dict | None) -> list[dict]:
    out = []
    for ekey, e in ((entities or {}).get("entities") or {}).items():
        for a in e.get("accounts", []):
            if a.get("classification") == "liability":
                out.append({**a, "entity": ekey})
    return out


def _goal_funded(goal: dict, ctx: dict) -> tuple[float | None, float | None]:
    """Return (target, funded) for a goal by kind. ctx: cash, core, target_months, contributions, entities."""
    kind = goal.get("kind") or "custom"
    params = goal.get("params") or {}
    tgt = _num(goal.get("target_amount"))
    if kind == "emergency_fund":
        months = _num(params.get("months")) or ctx["target_months"]
        if not tgt and ctx["core"]:
            tgt = months * ctx["core"]
        return tgt, ctx["cash"]
    if kind == "retirement_contribution":
        owner = str(params.get("owner") or "self")
        role = str(params.get("account_role") or "roth_ira")
        c = ((ctx["contributions"].get(owner) or {}).get(role)) or {}
        if not tgt:
            tgt = _num(c.get("limit"))
        return tgt, _num(c.get("ytd"))
    if kind == "debt_payoff":
        pat = params.get("match")
        bal = None
        if pat:
            for a in ctx["liabilities"]:
                if re.search(str(pat), str(a.get("name") or ""), re.I):
                    bal = abs(float(a.get("balance") or 0))
                    break
        if bal is not None:
            if not tgt:
                tgt = bal
            return tgt, max(0.0, tgt - bal)
        return tgt, None
    return tgt, _num(params.get("funded_amount"))


def build(portfolio: dict | None, consolidated: dict | None, risk: dict | None, asof: str,
          entities: dict | None = None) -> dict:
    prof = settings.profile_v2()
    owner, income, spending = prof.get("owner") or {}, prof.get("income") or {}, prof.get("spending") or {}
    cash_policy, retirement = prof.get("cash_policy") or {}, prof.get("retirement") or {}
    out: dict = {"asof": asof, "assumptions": {}, "missing": []}

    # --- cash flow & savings rate (household: every income source plus the spouse's W-2 when in household)
    spouse = prof.get("spouse") or {}
    sources = [s for s in (income.get("sources") or []) if isinstance(s, dict)]
    breakdown: dict[str, float] = {}
    for s in sources:
        amt = _num(s.get("annual"))
        if amt:
            breakdown[str(s.get("label") or s.get("kind") or "income")] = breakdown.get(str(s.get("label")), 0.0) + amt
    spouse_income = (_num(spouse.get("annual_gross")) or 0.0) if spouse.get("in_household") else 0.0
    if spouse_income:
        breakdown["spouse_w2"] = spouse_income
    gross = sum(breakdown.values())
    core = _num(spending.get("monthly_core_expenses"))
    disc = _num(spending.get("monthly_discretionary")) or 0
    # annual debt service from profile minimums where we have them (rough)
    debt_service = 12 * sum(_num(t.get("min_payment")) or 0 for t in (prof.get("debt_terms") or []))
    debt_service_source = "profile minimums"
    if consolidated and consolidated.get("available"):
        cf = (consolidated.get("cash_flow") or {}).get("90d") or {}
        ledger_ds = sum((e.get("transfers_by_class") or {}).get("debt_payment", 0.0) for e in (cf.get("per_entity") or {}).values())
        if ledger_ds > debt_service / 4:
            debt_service = ledger_ds * 4
            debt_service_source = "ledger 90d debt payments x4 (grows as history fills in)"
    if gross and core is not None:
        annual_spend = 12 * (core + disc)
        est_tax = gross * (float(owner.get("federal_bracket_pct") or 22) / 100) * 0.75  # effective ~ 3/4 of marginal
        out["savings"] = {"annual_income": gross, "income_breakdown": breakdown,
                          "annual_spend": annual_spend, "est_income_tax": est_tax, "known_debt_service": debt_service,
                          "debt_service_source": debt_service_source,
                          "savings_rate": (gross - annual_spend) / gross if gross else None,
                          "after_tax_surplus_est": gross - est_tax - annual_spend - debt_service,
                          "note": "spend is core+discretionary excluding debt; tax is a rough effective estimate, CPA to confirm"}
    else:
        if not gross:
            out["missing"].append("income.sources")
        if core is None:
            out["missing"].append("spending.monthly_core_expenses")

    # --- protection gaps
    prot = prof.get("protection") or {}
    fam = prof.get("family") or {}
    gaps = [k for k in ("term_life", "will_or_trust", "umbrella_liability", "disability") if prot.get(k) is False]
    out["protection"] = {"gaps": gaps, "planning_children": bool(fam.get("planning_children")),
                         "priority": "high" if gaps and fam.get("planning_children") else ("medium" if gaps else "none")}
    out["tax_agenda"] = prof.get("tax_agenda") or []

    # --- emergency fund
    cash = None
    if consolidated and consolidated.get("available"):
        cash = (consolidated.get("by_entity") or {}).get(HOUSEHOLD, {}).get("cash")
    target_m = _num(cash_policy.get("emergency_fund_months")) or 6
    biz_cash = 0.0
    if consolidated and consolidated.get("available"):
        biz_cash = sum(float(v.get("cash") or 0) for k, v in (consolidated.get("by_entity") or {}).items() if k != HOUSEHOLD)
    biz_is_reserve = bool(cash_policy.get("business_cash_is_reserve"))
    if core and cash is not None:
        out["emergency_fund"] = {"cash": cash, "months_covered": cash / core, "target_months": target_m,
                                 "gap": max(0.0, target_m * core - cash),
                                 "business_cash": biz_cash, "months_covered_incl_business": (cash + biz_cash) / core,
                                 "business_cash_is_reserve": biz_is_reserve,
                                 "note": ("household cash vs target; business cash counts as the working reserve "
                                          "(cash_policy.business_cash_is_reserve)" if biz_is_reserve else
                                          "household cash vs target; business cash shown for reference only")}
    else:
        out["missing"].append("household cash (needs ledger bank accounts) and spending.monthly_core_expenses")

    # --- contribution pacing (Roth kept as a named block for the dashboard; every configured account listed)
    contributions = retirement.get("contributions") or {}
    today = date.fromisoformat(asof)
    year_frac = (today.timetuple().tm_yday) / 365.0
    rows = []
    for who, by_role in contributions.items():
        for role, c in (by_role or {}).items():
            limit = _num((c or {}).get("limit"))
            ytd = _num((c or {}).get("ytd"))
            if limit is None and role == "roth_ira":
                limit = DEFAULT_ROTH_LIMIT
            if ytd is None or limit is None:
                continue
            rows.append({"owner": who, "account_role": role, "limit": limit, "contributed": ytd,
                         "remaining": max(0.0, limit - ytd), "on_pace": ytd >= limit * year_frac * 0.9,
                         "monthly_to_max": max(0.0, limit - ytd) / max(1, 12 - today.month + 1)})
    out["contributions"] = rows
    self_roth = next((r for r in rows if r["owner"] == "self" and r["account_role"] == "roth_ira"), None)
    if self_roth:
        out["roth"] = {k: self_roth[k] for k in ("limit", "contributed", "remaining", "on_pace", "monthly_to_max")}
    else:
        out["missing"].append("retirement.contributions.self.roth_ira.ytd")

    # --- debts: profile entries win; otherwise derive from liability accounts in the ledger
    debts = list(prof.get("debts") or [])
    ents_used = entities
    if not debts and consolidated and consolidated.get("available"):
        ents_used = entities or settings.read_json(paths.LATEST / "entities.json", {}) or {}
        for a in _liability_accounts(ents_used):
            if a.get("type") in ("loan", "Loan", "credit_card", "CreditCard"):
                is_card = a.get("type") in ("credit_card", "CreditCard")
                debts.append({"name": a.get("name"), "entity": a["entity"], "balance": a.get("balance"),
                              "rate_pct": 22.0 if is_card else None, "kind": "card" if is_card else "loan",
                              "min_payment": None, "source": "ledger"})
    # merge rate/term details from profile.debt_terms onto ledger-derived debts (regex on name)
    for d in debts:
        for term in prof.get("debt_terms") or []:
            if term.get("match") and re.search(term["match"], str(d.get("name") or ""), re.I):
                for k, v in term.items():
                    if k != "match" and (d.get(k) is None or k in ("rate_pct", "rate_type", "min_payment", "note")):
                        d[k] = v
                break
    if debts:
        rows = []
        for d in debts:
            bal, rate = _num(d.get("balance")) or 0, _num(d.get("rate_pct")) or 0
            rate_known = _num(d.get("rate_pct")) is not None
            rows.append({"name": d.get("name"), "entity": d.get("entity"), "balance": bal, "rate_pct": rate if rate_known else None,
                         "annual_interest": (bal * rate / 100) if rate_known else None, "min_payment": _num(d.get("min_payment")),
                         "kind": d.get("kind"), "source": d.get("source", "profile"),
                         "payoff_vs_invest": ("rate unknown: add rate_pct in profile.yml" if not rate_known else
                                              "pay down" if rate > 100 * LONG_RUN_RETURN else "invest first (rate below expected return)")})
        out["debts"] = {"total": sum(r["balance"] for r in rows),
                        "annual_interest": sum(r["annual_interest"] or 0 for r in rows),
                        "rates_missing": [r["name"] for r in rows if r["rate_pct"] is None], "items": rows}
    else:
        out["debts"] = {"total": 0.0, "items": [], "note": "no debts listed in profile.yml"}

    # --- retirement projection
    birth_year = _num(owner.get("birth_year"))
    target_age = _num(retirement.get("target_age"))
    target_spend = _num(retirement.get("target_annual_spend_today_dollars"))
    investable = None
    if portfolio and portfolio.get("meta"):
        investable = _num(portfolio["meta"].get("broker_total_value") or portfolio["meta"].get("total_value"))
    if birth_year and target_age and investable:
        years = max(1, int(target_age - (today.year - birth_year)))
        mu_hist = (risk or {}).get("cagr")
        vol_hist = (risk or {}).get("volatility")
        mu = SHRINK * mu_hist + (1 - SHRINK) * LONG_RUN_RETURN if mu_hist is not None else LONG_RUN_RETURN
        vol = SHRINK * vol_hist + (1 - SHRINK) * LONG_RUN_VOL if vol_hist is not None else LONG_RUN_VOL
        mu = min(mu, 0.09)  # cap optimism from a hot 3-year window (nominal)
        annual_contrib = 0.0
        if out.get("savings") and out["savings"].get("after_tax_surplus_est") is not None:
            annual_contrib = max(0.0, out["savings"]["after_tax_surplus_est"]) * 0.5  # assume half of the surplus gets invested
        rng = np.random.default_rng(42)
        n = 5000
        wealth = np.full(n, investable, dtype=float)
        for _ in range(years):
            r = rng.normal(mu - 0.5 * vol ** 2, vol, n)
            wealth = wealth * np.exp(r) + annual_contrib
        real = wealth / ((1 + INFLATION) ** years)
        pct = {f"p{p}": float(np.percentile(real, p)) for p in (10, 25, 50, 75, 90)}
        need = (target_spend * 25) if target_spend else None
        out["retirement"] = {
            "years_to_target": years, "target_age": target_age, "starting_investable": investable,
            "assumed_return": mu, "assumed_vol": vol, "annual_contribution_assumed": annual_contrib,
            "real_wealth_percentiles": pct,
            "target_nest_egg_4pct_rule": need,
            "probability_hit_target": float((real >= need).mean()) if need else None,
            "note": "real (today's) dollars; contributions assume half of the after-tax surplus is invested; 4% rule for the target",
        }
        out["assumptions"] = {"long_run_return": LONG_RUN_RETURN, "long_run_vol": LONG_RUN_VOL, "shrink_to_history": SHRINK,
                              "inflation": INFLATION, "paths": n}
    else:
        out["missing"] += [k for k, v in (("owner.birth_year", birth_year), ("retirement.target_age", target_age)) if not v]
        if not target_spend:
            out["missing"].append("retirement.target_annual_spend_today_dollars (for the hit-probability)")
        if not investable:
            out["missing"].append("holdings (connect a brokerage or upload data/holdings.csv)")

    # --- goals
    ctx = {"cash": cash, "core": core, "target_months": target_m, "contributions": contributions,
           "liabilities": _liability_accounts(ents_used) if (ents_used or entities) else []}
    grows = []
    for g in (settings.goals_v2() or {}).get("goals") or []:
        tgt, funded = _goal_funded(g, ctx)
        grows.append({"id": g.get("id"), "kind": g.get("kind"), "name": g.get("name"), "target": tgt, "funded": funded,
                      "progress": (funded / tgt) if (funded is not None and tgt) else None, "deadline": g.get("deadline")})
    out["goals"] = grows
    out["missing"] = sorted(set(out["missing"]))
    out["available"] = True
    return out
