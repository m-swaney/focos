"""Brokerage totals from the holdings snapshot are added exactly once, whatever ledger_account_id says."""
from focos import settings
from focos.config import writer
from focos.ledger import consolidate

ACCOUNTS = [{"id": "simplefin:A", "name": "Checking", "balance": 1000.0, "balance_cents": 100000, "classification": "asset",
             "account_type": "depository", "subtype": "checking", "institution_name": "Bank", "source": "simplefin"}]
SNAP = {"date": "2026-03-01", "accounts": [{"key": "brokerage", "portfolio": {"total_value": 50000.0}}]}


def _setup(ledger_id, account_ids):
    entry = {"key": "brokerage", "label": "Brokerage", "role": "taxable", "entity": "personal", "source": "csv"}
    if ledger_id:
        entry["ledger_account_id"] = ledger_id
    assert not writer.write_file("accounts.yml", {"version": 2, "brokerage": [entry]})
    assert not writer.write_file("entities.yml", {"version": 2, "corridors": [], "entities": {
        "personal": {"label": "Personal", "kind": "household", "account_ids": account_ids}}})
    settings.reset()


def test_broker_total_added_when_ledger_id_points_nowhere(initialized_home):
    _setup("sure:gone", ["simplefin:A"])
    cons, _ = consolidate.build(ACCOUNTS, [], SNAP, "2026-03-01", sync={"provider": "simplefin"})
    assert cons["net_worth"] == 51000.0 and cons["broker_in_ledger"] is False
    assert cons["ledger_sync"]["provider"] == "simplefin" and "sure_sync" not in cons and "robinhood_in_sure" not in cons


def test_broker_total_not_double_counted_when_mirrored(initialized_home):
    _setup("simplefin:B", ["simplefin:A", "simplefin:B"])
    accounts = ACCOUNTS + [{"id": "simplefin:B", "name": "Brokerage", "balance": 50000.0, "balance_cents": 5000000, "classification": "asset",
                            "account_type": "investment", "subtype": "brokerage", "source": "simplefin"}]
    cons, _ = consolidate.build(accounts, [], SNAP, "2026-03-01")
    assert cons["net_worth"] == 51000.0 and cons["broker_in_ledger"] is True
