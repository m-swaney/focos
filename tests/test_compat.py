"""v1 -> v2 config transforms with made-up values."""
from focos.config import compat
from focos.config.models import Accounts, Entities, Goals, Profile

V1_ACCOUNTS = {
    "robinhood": {
        "brokerage": {"last4": "1111", "label": "Brokerage", "role": "taxable", "agent_access": "read"},
        "ira": {"last4": "2222", "label": "IRA", "role": "roth_ira", "agent_access": "read"},
        "play": {"last4": "3333", "label": "Play money", "role": "sandbox", "agent_access": "trade"},
    },
    "sure": {"robinhood_brokerage": "aaaa-1", "robinhood_ira": "aaaa-2", "robinhood_play": "aaaa-3"},
}

V1_ENTITIES = {
    "entities": {
        "personal": {"label": "Personal", "sure_account_ids": ["s-1", "s-2"]},
        "shop": {"label": "Corner Shop LLC", "institution": "Some Bank", "sure_account_ids": ["s-9"]},
    },
    "name_hints": {"shop": "(CORNER SHOP)", "personal": "(BIG BANK|CARD CO)"},
    "corridors": [["shop", "personal"]],
}

V1_PROFILE = {
    "person": {"name": "Sam", "birth_year": 1990, "state": "TX", "filing_status": "single", "federal_bracket_pct": 24},
    "spouse": {"in_household": True, "annual_gross": 40000, "roth_contributed_this_year": 1000},
    "income": {"annual_business_income": 120000, "annual_business_income_range": [100000, 140000], "annual_gross_w2": None,
               "notes": "draws fund spending"},
    "spending": {"monthly_core_expenses": 4000},
    "cash_policy": {"emergency_fund_months": 3},
    "retirement": {"target_age": 60, "roth_ira_contribution_limit": 7000, "roth_contributed_this_year": 3500},
    "risk": {"tolerance": "moderate"},
    "targets": {"taxable": {"us_broad_index": 60, "individual_stocks": 40}},
}

V1_GOALS = {"goals": [
    {"id": "emergency_fund", "name": "Emergency fund", "entity": "personal"},
    {"id": "heloc_payoff", "name": "Kill the HELOC", "target_amount": 20000},
    {"id": "spouse_roth", "name": "Spouse Roth", "target_amount": 7000},
    {"id": "roth_max", "name": "Max Roth"},
    {"id": "boat_payoff", "name": "Boat loan gone"},
    {"id": "dream_home", "name": "Bigger house", "deadline": "2030-01-01", "funded_by": ["cash"]},
]}


def test_accounts_v1_to_v2_roles_and_ledger_ids():
    out = compat.accounts_v2(V1_ACCOUNTS)
    Accounts.model_validate(out)
    by_key = {a["key"]: a for a in out["brokerage"]}
    assert by_key["brokerage"]["role"] == "taxable" and by_key["brokerage"]["match"] == {"last4": "1111"}
    assert by_key["ira"]["role"] == "roth_ira"
    assert by_key["play"]["role"] == "sandbox" and by_key["play"]["agent_access"] == "trade"
    assert by_key["play"]["ledger_account_id"] == "sure:aaaa-3"
    assert all(a["source"] == "robinhood_mcp" and a["entity"] == "personal" for a in out["brokerage"])


def test_accounts_v2_passthrough():
    v2 = {"version": 2, "brokerage": [{"key": "x", "label": "X", "role": "taxable"}]}
    assert compat.accounts_v2(v2)["brokerage"][0]["key"] == "x"
    assert compat.accounts_v2({})["brokerage"] == []


def test_entities_v1_to_v2():
    out = compat.entities_v2(V1_ENTITIES)
    Entities.model_validate(out)
    assert out["entities"]["personal"]["kind"] == "household"
    assert out["entities"]["shop"]["kind"] == "business"
    assert out["entities"]["shop"]["account_ids"] == ["sure:s-9"]
    assert out["entities"]["shop"]["name_hints"] == "(CORNER SHOP)"
    assert out["entities"]["shop"]["institution"] == "Some Bank"
    assert out["corridors"] == [["shop", "personal"]]


def test_entities_v2_adds_household_when_missing():
    out = compat.entities_v2({"version": 2, "entities": {"biz": {"label": "Biz", "kind": "business"}}})
    assert list(out["entities"])[0] == "personal"


def test_profile_v1_to_v2():
    out = compat.profile_v2(V1_PROFILE)
    Profile.model_validate(out)
    assert out["owner"]["name"] == "Sam" and "state" not in out["owner"]
    assert out["household"]["state"] == "TX" and out["household"]["timezone"]
    src = out["income"]["sources"]
    assert len(src) == 1 and src[0]["kind"] == "business" and src[0]["annual"] == 120000
    assert out["income"]["notes"] == "draws fund spending"
    c = out["retirement"]["contributions"]
    assert c["self"]["roth_ira"] == {"limit": 7000, "ytd": 3500}
    assert c["spouse"]["roth_ira"]["ytd"] == 1000
    assert "roth_contributed_this_year" not in out["spouse"]
    assert out["cash_policy"]["business_cash_is_reserve"] is True
    assert out["targets"] == V1_PROFILE["targets"]


def test_profile_v2_passthrough_gets_timezone():
    out = compat.profile_v2({"version": 2, "owner": {"name": "Ann"}})
    assert out["household"]["timezone"] == compat.DEFAULT_TZ


def test_goals_v1_ids_to_kinds():
    out = compat.goals_v2(V1_GOALS)
    Goals.model_validate(out)
    by_id = {g["id"]: g for g in out["goals"]}
    assert by_id["emergency_fund"]["kind"] == "emergency_fund"
    assert by_id["heloc_payoff"]["kind"] == "debt_payoff" and by_id["heloc_payoff"]["params"] == {"match": "HELOC"}
    assert by_id["spouse_roth"]["params"] == {"owner": "spouse", "account_role": "roth_ira"}
    assert by_id["roth_max"]["params"]["owner"] == "self"
    assert by_id["boat_payoff"]["kind"] == "debt_payoff" and by_id["boat_payoff"]["params"] == {"match": "BOAT"}
    assert by_id["dream_home"]["kind"] == "custom" and by_id["dream_home"]["funded_by"] == ["cash"]
