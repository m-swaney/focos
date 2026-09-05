"""The Sure adapter must hand netting/entities the same dict shapes the old direct client did."""
from datetime import date

from focos.ledger.providers.sure import SureProvider
from focos.sources.sure import normalize_transaction

SURE_ACCOUNT = {"id": "aaaa-1", "name": "Main Checking", "balance": "$1,200.50", "balance_cents": 120050, "cash_balance": "$1,200.50",
                "cash_balance_cents": 120050, "currency": "USD", "classification": "asset", "account_type": "Depository",
                "subtype": "checking", "institution_name": "Some Bank", "institution_domain": "somebank.example",
                "updated_at": "2026-03-01T10:00:00Z"}
SURE_TX = {"id": "tx-1", "date": "2026-02-20", "account": {"id": "aaaa-1", "name": "Main Checking", "account_type": "Depository"},
           "signed_amount_cents": -4520, "name": "GROCERY", "merchant": {"name": "Grocery"}, "category": {"name": "Food"},
           "tags": [], "transfer": {"id": "tr-1", "other_account": {"id": "bbbb-2"}}, "external_id": "ext", "source": "simplefin"}


class FakeClient:
    base_url = "http://127.0.0.1:3000"
    calls = 0

    def health(self):
        return True

    def accounts(self, include_disabled=False):
        return [SURE_ACCOUNT]

    def transactions(self, start, end=None, account_ids=None):
        self.seen_ids = account_ids
        return [normalize_transaction(SURE_TX)]

    def latest_sync(self):
        return {"completed_at": "2026-03-01T10:05:00Z"}

    def balance_sheet(self):
        return {"net_worth": "x"}


def test_accounts_and_transactions_keep_shapes(monkeypatch):
    monkeypatch.setenv("SURE_API_KEY_RO", "k")
    p = SureProvider(FakeClient())
    assert p.health().ok is True
    a = p.accounts()[0]
    assert a.id == "sure:aaaa-1" and a.balance == 1200.5 and a.balance_cents == 120050
    row = a.as_row()
    assert row["account_type"] == "Depository" and row["subtype"] == "checking" and row["classification"] == "asset"
    assert row["institution_name"] == "Some Bank" and row["source"] == "sure"
    t = p.transactions(date(2026, 2, 1), date(2026, 3, 1), ["sure:aaaa-1"])[0]
    assert p.client.seen_ids == ["aaaa-1"]
    d = t.model_dump()
    for k in ("id", "date", "account_id", "account_name", "account_type", "amount", "name", "merchant", "category", "tags",
              "transfer_id", "other_account_id", "external_id", "source"):
        assert k in d
    assert d["id"] == "sure:tx-1" and d["account_id"] == "sure:aaaa-1" and d["other_account_id"] == "sure:bbbb-2"
    assert d["amount"] == -45.2 and d["account_type"] == "depository"
    assert p.sync_status().last_success == "2026-03-01T10:05:00Z"
    assert p.refresh(date(2026, 3, 1)).skipped is True  # read-only key: no sync trigger
    assert p.refreshes_synchronously is False


def test_not_configured_without_keys(monkeypatch):
    monkeypatch.delenv("SURE_API_KEY_RW", raising=False)
    monkeypatch.delenv("SURE_API_KEY_RO", raising=False)
    assert SureProvider(FakeClient()).health().ok is None
