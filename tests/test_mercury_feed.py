"""Mercury direct feed: parsing, number stripping, pull window, and how the ledger provider composes feeds."""
import json
from datetime import date, timedelta

from focos import settings
from focos.config import writer
from focos.ledger.feeds import configured_feeds
from focos.ledger.feeds import mercury as mf
from focos.ledger.providers import simplefin as sf
from focos.ledger.providers.sqlite_store import SQLiteStore

ACCOUNTS = [
    {"id": "m-1", "name": "Ops Checking", "nickname": None, "kind": "checking", "currentBalance": 9000.5, "availableBalance": 8900.0,
     "accountNumber": "1234", "routingNumber": "0210", "status": "active"},
    {"id": "m-2", "name": "Reserve", "kind": "savings", "currentBalance": 25000, "availableBalance": 25000, "accountNumber": "9", "status": "active"},
    {"id": "m-3", "name": "Old", "kind": "checking", "currentBalance": 0, "status": "archived"},
]
TXS = {
    "m-1": [
        {"id": "t1", "amount": -120.0, "postedAt": "2026-03-01T12:00:00Z", "createdAt": "2026-02-28T20:00:00Z", "status": "sent",
         "counterpartyName": "AWS", "bankDescription": "AWS EMEA", "details": {"domesticWireRoutingInfo": {"accountNumber": "555"}}},
        {"id": "t2", "amount": 5000.0, "postedAt": None, "createdAt": "2026-03-02T09:00:00Z", "status": "pending", "counterpartyName": "Customer"},
        {"id": "t3", "amount": -1.0, "postedAt": None, "createdAt": "2026-03-02T09:00:00Z", "status": "cancelled", "counterpartyName": "x"},
    ],
    "m-2": [],
}


class FakeClient:
    def __init__(self):
        self.calls = []

    def accounts(self):
        return [dict(a) for a in ACCOUNTS]

    def transactions(self, aid, start, end):
        self.calls.append((aid, start, end))
        return [dict(t) for t in TXS.get(aid, [])]


def _feed(store):
    client = FakeClient()
    f = mf.MercuryFeed(store, client_factory=lambda: client, token="tok")
    f.history_days_initial = 100
    return f, client


def test_parse_and_ingest_strips_numbers(initialized_home, tmp_path):
    store = SQLiteStore(tmp_path / "l.sqlite")
    f, client = _feed(store)
    res = f.pull(date(2026, 3, 2), force=True)
    assert res.ok and res.accounts == 2 and res.transactions_new == 2
    assert client.calls[0][1] == date(2026, 3, 2) - timedelta(days=100)
    accts = {a.id: a for a in store.accounts()}
    assert accts["mercury:m-1"].subtype == "checking" and accts["mercury:m-2"].subtype == "savings"
    assert accts["mercury:m-1"].balance == 9000.5 and accts["mercury:m-1"].balance_date == "2026-03-02" and "mercury:m-3" not in accts
    raw = store.account_raw("mercury:m-1")
    assert "accountNumber" not in raw and "routingNumber" not in raw
    txs = {t.id: t for t in store.transactions(date(2026, 2, 1), date(2026, 3, 31), include_pending=True)}
    assert set(txs) == {"mercury:m-1:t1", "mercury:m-1:t2"}
    assert txs["mercury:m-1:t1"].amount == -120.0 and txs["mercury:m-1:t1"].date == "2026-03-01" and txs["mercury:m-1:t1"].merchant == "AWS"
    assert txs["mercury:m-1:t2"].pending and txs["mercury:m-1:t2"].date == "2026-03-02"
    row = store.conn.execute("SELECT raw FROM transactions WHERE id='mercury:m-1:t1'").fetchone()
    assert "details" not in json.loads(row["raw"])
    assert f.pull(date(2026, 3, 2)).skipped  # within refresh_min_hours


def test_provider_composes_feeds(initialized_home, tmp_path, monkeypatch):
    store = SQLiteStore(tmp_path / "l.sqlite")
    p = sf.SimpleFINProvider(store=store, access_url="", feeds=[])
    assert p.health().ok is None  # nothing configured
    f, _ = _feed(store)
    p = sf.SimpleFINProvider(store=store, access_url="", feeds=[f])
    assert p.health().ok is True
    res = p.refresh(date(2026, 3, 2), force=True)
    assert res.ok and res.accounts == 2 and res.start == (date(2026, 3, 2) - timedelta(days=100)).isoformat()
    assert {a.provider for a in p.accounts()} == {"mercury"}
    st = p.sync_status()
    assert st.accounts == 2 and st.detail["feeds"] == ["mercury"] and st.last_success
    monkeypatch.setenv("MERCURY_TOKEN", "tok")
    assert [x.name for x in configured_feeds(store)] == ["mercury"]
    writer.write_section("focos.yml", "ledger", {"provider": "simplefin", "mercury": {"enabled": False}})
    settings.reset()
    assert configured_feeds(store) == []
    monkeypatch.delenv("MERCURY_TOKEN")
    writer.write_section("focos.yml", "ledger", {"provider": "simplefin"})
    settings.reset()
    assert configured_feeds(store) == []


def test_merge_results():
    from focos.ledger.providers.base import PullResult

    a = PullResult(ok=True, accounts=3, transactions_new=5, start="2026-01-01", end="2026-03-01")
    b = PullResult(ok=False, accounts=0, errors=["boom"], start="2026-02-01", end="2026-03-02")
    m = sf.merge_results([a, b])
    assert m.ok is False and m.accounts == 3 and m.transactions_new == 5 and m.errors == ["boom"]
    assert m.start == "2026-01-01" and m.end == "2026-03-02" and not m.skipped
    assert sf.merge_results([PullResult(ok=True, skipped=True), PullResult(ok=True, skipped=True)]).skipped
