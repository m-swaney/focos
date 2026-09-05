"""Imported (legacy) history merges with the live feeds without double counting, links, and adoption."""
from datetime import date
from pathlib import Path

from focos import settings
from focos.config import writer
from focos.ledger.legacy import link
from focos.ledger.legacy import sure_dump as sd
from focos.ledger.providers import simplefin as sf
from focos.ledger.providers.base import LedgerAccount, ManualAccountSpec
from focos.ledger.providers.sqlite_store import SQLiteStore

FIX = Path(__file__).parent / "fixtures" / "sure_dump.sql"
ALL = (date(2025, 1, 1), date(2026, 12, 31))


def _live(store, aid="simplefin:ACT-CHK-1", first="2026-01-03"):
    store.upsert_account(LedgerAccount(id=aid, provider="simplefin", name="Everyday Checking", institution_name="Example Bank",
                                       account_type="depository", subtype="checking", classification="asset", balance=1500.0))
    store.upsert_balance(aid, "2026-01-10", 1500.0)
    store.upsert_transactions(aid, [{"id": f"{aid}:n1", "posted_date": first, "amount": 3000.0, "description": "Payroll", "pending": False},
                                    {"id": f"{aid}:n2", "posted_date": "2026-01-08", "amount": -20.0, "description": "Coffee", "pending": False}])
    store.record_pull("simplefin", "2026-01-03", "2026-01-10", 1, 2, [])


def _ids(p):
    return {t.id for t in p.transactions(*ALL)}


def test_aliased_legacy_stops_where_live_history_starts(initialized_home, tmp_path):
    store = SQLiteStore(tmp_path / "l.sqlite")
    sd.import_dump(FIX, store)
    _live(store)
    p = sf.SimpleFINProvider(store=store, access_url="https://u:p@bridge.simplefin.org/simplefin", feeds=[])
    ids = _ids(p)  # nothing linked yet and no cutoff: legacy rows read in full
    assert "sure:acc-chk:e-3" in ids and "simplefin:ACT-CHK-1:n1" in ids
    store.set_aliases("simplefin:ACT-CHK-1", ["sure:acc-chk"])
    cut = store.legacy_cutoffs(sf.PRIMARY_PROVIDERS, ["sure"])
    assert cut["sure:acc-chk"] == "2026-01-03" and cut["sure:acc-biz"] is None
    ids = _ids(p)
    assert "sure:acc-chk:e-1" in ids and "sure:acc-chk:e-7" in ids            # before the live history
    assert "sure:acc-chk:e-2" not in ids and "sure:acc-chk:e-3" not in ids    # on/after: the live feed owns them
    assert "sure:acc-biz:e-4" in ids                                           # unaliased, no cutoff (closed-account semantics)
    store.set_meta("legacy_cutoff", "2026-01-01")
    ids = _ids(p)
    assert "sure:acc-biz:e-4" not in ids and "sure:acc-chk:e-7" in ids
    store.set_meta("legacy_cutoff:sure:acc-biz", "2026-02-01")                 # per-account override
    assert "sure:acc-biz:e-4" in _ids(p)
    # legacy accounts never appear in the live account list, so balances are not double counted either
    assert {a.provider for a in p.accounts()} == {"simplefin"}
    assert p.mirror_broker_value("sure:acc-chk", date(2026, 1, 10), 5.0) is False
    assert p.mirror_broker_value("simplefin:ACT-CHK-1", date(2026, 1, 10), 5.0) is True


def test_link_exact_then_heuristic_and_apply(initialized_home, tmp_path):
    store = SQLiteStore(tmp_path / "l.sqlite")
    sd.import_dump(FIX, store)
    _live(store)
    store.upsert_account(LedgerAccount(id="mercury:m1", provider="mercury", name="Business Checking", institution_name="Mercury",
                                       account_type="depository", subtype="checking", classification="asset", balance=9000.0))
    store.upsert_balance("mercury:m1", "2026-01-10", 9000.0)
    store.record_pull("mercury", "2025-12-01", "2026-01-10", 1, 0, [])
    out = link.propose(store, sf.PRIMARY_PROVIDERS, ["sure"])
    by = {p["live"]: p for p in out["proposals"]}
    assert by["simplefin:ACT-CHK-1"]["legacy"] == "sure:acc-chk" and by["simplefin:ACT-CHK-1"]["how"] == "simplefin_id"
    assert by["mercury:m1"]["legacy"] == "sure:acc-biz" and by["mercury:m1"]["how"] == "heuristic"
    assert {u["id"] for u in out["unmatched_legacy"]} == {"sure:acc-card", "sure:acc-loan", "sure:acc-prop"}
    writer.write_file("entities.yml", {"version": 2, "corridors": [], "entities": {
        "personal": {"label": "Personal", "kind": "household", "account_ids": ["sure:acc-chk"]},
        "biz": {"label": "Biz LLC", "kind": "business", "account_ids": ["sure:acc-biz"]}}})
    settings.reset()
    res = link.apply(store, out["proposals"], sf.PRIMARY_PROVIDERS)
    assert res["legacy_cutoff"] == "2025-12-01" and res["aliased"] == 2
    ents = settings.entities_v2()["entities"]
    assert ents["personal"]["account_ids"] == ["simplefin:ACT-CHK-1"] and ents["biz"]["account_ids"] == ["mercury:m1"]
    assert store.accounts(providers=("mercury",))[0].aliases == ["sure:acc-biz"]
    assert store.legacy_cutoffs(sf.PRIMARY_PROVIDERS, ["sure"])["sure:acc-card"] == "2025-12-01"


def test_adopt_keeps_history(initialized_home, tmp_path):
    store = SQLiteStore(tmp_path / "l.sqlite")
    sd.import_dump(FIX, store)
    spec = ManualAccountSpec(key="student_loans", name="Student loans", entity="personal", account_type="loan", subtype="student",
                             classification="liability", balance=-12000.0)
    acct = store.adopt_account("sure:acc-loan", spec)
    assert (acct.id, acct.provider, acct.balance, acct.balance_date, acct.is_manual) == ("manual:student_loans", "manual", -12000.0, "2026-01-02", True)
    assert store.manual_entities()["manual:student_loans"] == "personal"
    assert not any(a.id == "sure:acc-loan" for a in store.accounts())
    assert store.balances(date(2026, 1, 1), date(2026, 1, 31), ["manual:student_loans"])
    p = sf.SimpleFINProvider(store=store, access_url="", feeds=[])
    assert [a.id for a in p.accounts()] == ["manual:student_loans"]
    # adopting onto an id that already exists (created earlier by property refresh) merges instead of failing
    store.upsert_manual_account(ManualAccountSpec(key="prop_home", name="Primary residence", account_type="property", balance=1.0))
    prop = store.adopt_account("sure:acc-prop", ManualAccountSpec(key="prop_home", name="Primary residence", account_type="property", balance=350000.0))
    assert prop.id == "manual:prop_home" and store.balances(date(2026, 1, 1), date(2026, 1, 31), ["manual:prop_home"])[0].balance == 350000.0
