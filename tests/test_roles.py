"""Role-based lookups replace the hard-coded individual/roth/agentic keys."""
from pathlib import Path

import yaml

from focos import settings
from focos.analytics import run as analytics_run
from focos.ledger import entities as ent
from focos.sources import robinhood_snapshot as rh

V2_ACCOUNTS = {"version": 2, "brokerage": [
    {"key": "brk_a", "label": "Brokerage A", "role": "taxable", "match": {"last4": "1111"}, "entity": "personal"},
    {"key": "brk_b", "label": "Brokerage B", "role": "taxable", "match": {"last4": "4444"}, "entity": "shop"},
    {"key": "ira", "label": "Roth", "role": "roth_ira", "match": {"last4": "2222"}},
    {"key": "play", "label": "Play", "role": "sandbox", "match": {"last4": "3333"}, "agent_access": "trade",
     "ledger_account_id": "sure:uuid-play"},
]}


def _write_accounts(home: Path, data: dict) -> None:
    (home / "config" / "accounts.yml").write_text(yaml.safe_dump(data), encoding="utf-8")
    settings.reset()


def test_accounts_by_role_v2(initialized_home: Path):
    _write_accounts(initialized_home, V2_ACCOUNTS)
    assert settings.accounts_by_role("taxable") == ["brk_a", "brk_b"]
    assert settings.accounts_by_role("sandbox") == ["play"]
    assert settings.account_role("ira") == "roth_ira"
    assert settings.account_role("nope") is None


def test_accounts_by_role_v1_layout(initialized_home: Path):
    _write_accounts(initialized_home, {"robinhood": {"main": {"last4": "9999", "role": "taxable"},
                                                     "agentic": {"last4": "8888", "role": "sandbox", "agent_access": "trade"}}})
    assert settings.accounts_by_role("taxable") == ["main"]
    assert settings.accounts_by_role("sandbox") == ["agentic"]


def test_account_key_matching():
    assert rh.account_key({"account_number": "90001111"}, V2_ACCOUNTS) == "brk_a"
    assert rh.account_key({"account_number": "90007777", "agentic_allowed": True}, V2_ACCOUNTS) == "play"
    assert rh.account_key({"account_number": "90007777"}, V2_ACCOUNTS) == "acct7777"
    # v1 shape still accepted
    assert rh.account_key({"account_number": "90005555"}, {"robinhood": {"old": {"last4": "5555"}}}) == "old"


def test_lots_for_tax_uses_every_taxable_account():
    snap = {"tax_lots": [{"account": "brk_a", "symbol": "X"}, {"account": "brk_b", "symbol": "Y"}, {"account": "ira", "symbol": "Z"}]}
    assert [l["symbol"] for l in rh.lots_for_tax(snap, ["brk_a", "brk_b"])] == ["X", "Y"]


def test_drift_combines_accounts_sharing_a_role():
    cw = {"brk_a": {"us_broad_index": 1.0}, "brk_b": {"individual_stocks": 1.0}, "ira": {"international": 1.0}}
    targets = {"taxable": {"us_broad_index": 50, "individual_stocks": 50}, "roth_ira": {"international": 100}}
    out = analytics_run._drift(cw, targets, {"brk_a": 300.0, "brk_b": 100.0, "ira": 50.0},
                               role_to_accounts={"taxable": ["brk_a", "brk_b"], "roth_ira": ["ira"]})
    tax = {r["asset_class"]: r for r in out["taxable"]}
    assert abs(tax["us_broad_index"]["current"] - 0.75) < 1e-9
    assert abs(tax["individual_stocks"]["current"] - 0.25) < 1e-9
    assert abs(tax["us_broad_index"]["drift"] - 0.25) < 1e-9
    assert out["roth_ira"][0]["drift"] == 0.0
    assert "sandbox" not in out


def test_entity_map_prefix_insensitive_and_per_entity_hints():
    cfg = {"version": 2, "entities": {
        "personal": {"label": "Personal", "kind": "household", "account_ids": ["sure:s-1"], "name_hints": "(BIG BANK)"},
        "shop": {"label": "Shop", "kind": "business", "account_ids": ["simplefin:sf-9"], "aliases": ["sure:s-9"],
                 "name_hints": "(SHOP)"},
    }}
    accounts = [{"id": "s-1", "name": "Checking"}, {"id": "s-9", "name": "Old shop acct"},
                {"id": "sf-9", "name": "New shop acct"}, {"id": "x", "name": "Big Bank Savings"},
                {"id": "y", "name": "Corner Shop Card"}, {"id": "z", "name": "Mystery"}]
    m = ent.account_entity_map(cfg, accounts)
    assert m == {"s-1": "personal", "s-9": "shop", "sf-9": "shop", "x": "personal", "y": "shop"}


def test_entity_map_v1_config_still_works():
    cfg = {"entities": {"personal": {"sure_account_ids": ["rh-1"]}, "biz": {"sure_account_ids": []}},
           "name_hints": {"biz": "(BIZ)", "personal": "(CARD)"}}
    m = ent.account_entity_map(cfg, [{"id": "rh-1", "name": "x"}, {"id": "b", "name": "Biz Checking"},
                                     {"id": "c", "name": "Card Co", "institution_name": "Card Co"}])
    assert m == {"rh-1": "personal", "b": "biz", "c": "personal"}


def test_corridors_default_to_business_household_pairs():
    cfg = {"version": 2, "entities": {"personal": {"label": "P"}, "a": {"label": "A", "kind": "business"},
                                      "b": {"label": "B", "kind": "business"}}, "corridors": []}
    assert ent.corridors(cfg) == {("a", "personal"), ("personal", "a"), ("b", "personal"), ("personal", "b")}


def test_balance_sheets_credit_broker_to_owning_entity():
    cfg = {"version": 2, "entities": {"personal": {"label": "P"}, "shop": {"label": "S", "kind": "business"}}}
    sheets = ent.balance_sheets([], {}, {"brk_a": 100.0, "brk_b": 50.0}, False, entities_cfg=cfg,
                                broker_entity_of={"brk_a": "personal", "brk_b": "shop"})
    assert sheets["entities"]["personal"]["assets"] == 100.0
    assert sheets["entities"]["shop"]["assets"] == 50.0
    assert sheets["consolidated"]["net_worth"] == 150.0
