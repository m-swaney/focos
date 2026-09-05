"""plan.build over a v2 profile with goal kinds, using a made-up household."""
from pathlib import Path

import yaml

from focos import plan, settings


def _cfg(home: Path, name: str, data: dict) -> None:
    (home / "config" / name).write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    settings.reset()


PROFILE = {
    "version": 2,
    "owner": {"name": "Ann", "birth_year": 1988, "federal_bracket_pct": 22},
    "household": {"timezone": "America/Chicago"},
    "spouse": {"in_household": True, "annual_gross": 30000},
    "income": {"sources": [{"label": "Salary", "kind": "w2", "annual": 90000}, {"label": "Side gig", "kind": "other", "annual": 10000}]},
    "spending": {"monthly_core_expenses": 4000},
    "cash_policy": {"emergency_fund_months": 3, "business_cash_is_reserve": False},
    "retirement": {"target_age": 65, "target_annual_spend_today_dollars": 80000,
                   "contributions": {"self": {"roth_ira": {"limit": 7000, "ytd": 3500}},
                                     "spouse": {"roth_ira": {"limit": 7000, "ytd": 7000}}}},
    "debt_terms": [{"match": "CAR LOAN", "rate_pct": 6.0, "rate_type": "fixed", "min_payment": 300}],
}

GOALS = {"version": 2, "goals": [
    {"kind": "emergency_fund", "name": "Emergency fund", "params": {"months": 3}},
    {"kind": "debt_payoff", "name": "Car loan", "params": {"match": "CAR LOAN"}},
    {"kind": "retirement_contribution", "name": "Spouse Roth", "params": {"owner": "spouse", "account_role": "roth_ira"}},
    {"kind": "purchase", "name": "New roof", "target_amount": 12000, "params": {"funded_amount": 3000}},
    {"kind": "custom", "name": "Someday"},
]}

CONSOLIDATED = {"available": True, "by_entity": {"personal": {"cash": 6000.0}, "shop": {"cash": 2000.0}},
                "cash_flow": {"90d": {"per_entity": {}}}}
ENTITIES = {"entities": {"personal": {"accounts": [
    {"name": "Car Loan 1234", "classification": "liability", "type": "loan", "balance": -8000.0},
    {"name": "Checking", "classification": "asset", "type": "depository", "balance": 6000.0},
]}}}
PORTFOLIO = {"meta": {"total_value": 50000.0}}


def test_plan_v2_profile_and_goal_kinds(initialized_home: Path):
    _cfg(initialized_home, "profile.yml", PROFILE)
    _cfg(initialized_home, "goals.yml", GOALS)
    out = plan.build(PORTFOLIO, CONSOLIDATED, {"cagr": 0.08, "volatility": 0.18}, "2026-07-01", entities=ENTITIES)
    assert out["available"]
    s = out["savings"]
    assert s["annual_income"] == 130000
    assert s["income_breakdown"] == {"Salary": 90000, "Side gig": 10000, "spouse_w2": 30000}
    assert s["known_debt_service"] == 3600
    ef = out["emergency_fund"]
    assert ef["cash"] == 6000 and ef["target_months"] == 3 and ef["business_cash"] == 2000
    assert ef["business_cash_is_reserve"] is False
    assert out["roth"]["contributed"] == 3500 and out["roth"]["remaining"] == 3500
    assert {(r["owner"], r["account_role"]) for r in out["contributions"]} == {("self", "roth_ira"), ("spouse", "roth_ira")}
    debt = out["debts"]["items"][0]
    assert debt["name"] == "Car Loan 1234" and debt["rate_pct"] == 6.0 and debt["min_payment"] == 300
    assert out["retirement"]["years_to_target"] == 27
    goals = {g["name"]: g for g in out["goals"]}
    assert goals["Emergency fund"]["target"] == 12000 and goals["Emergency fund"]["funded"] == 6000
    assert goals["Car loan"]["target"] == 8000 and goals["Car loan"]["funded"] == 0
    assert goals["Spouse Roth"]["target"] == 7000 and goals["Spouse Roth"]["progress"] == 1.0
    assert goals["New roof"]["progress"] == 0.25
    assert goals["Someday"]["funded"] is None and goals["Someday"]["kind"] == "custom"
    assert out["missing"] == []


def test_plan_reports_missing_fields_on_empty_profile(initialized_home: Path):
    out = plan.build(None, None, None, "2026-07-01")
    assert out["available"]
    assert "income.sources" in out["missing"]
    assert "spending.monthly_core_expenses" in out["missing"]
    assert any(m.startswith("owner.birth_year") for m in out["missing"])
    assert "retirement.contributions.self.roth_ira.ytd" in out["missing"]
    assert out["goals"][0]["kind"] == "emergency_fund"  # from the template


def test_plan_accepts_v1_profile(initialized_home: Path):
    _cfg(initialized_home, "profile.yml", {
        "person": {"name": "Old", "birth_year": 1980},
        "income": {"annual_business_income": 100000},
        "spending": {"monthly_core_expenses": 3000},
        "retirement": {"target_age": 60, "roth_contributed_this_year": 1000},
    })
    _cfg(initialized_home, "goals.yml", {"goals": [{"id": "roth_max", "name": "Max Roth"}]})
    out = plan.build(PORTFOLIO, None, None, "2026-07-01")
    assert out["savings"]["income_breakdown"] == {"Business income": 100000}
    assert out["roth"]["contributed"] == 1000
    assert out["goals"][0]["kind"] == "retirement_contribution" and out["goals"][0]["funded"] == 1000
