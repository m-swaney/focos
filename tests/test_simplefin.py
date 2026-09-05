"""SimpleFIN parsing, SQLite upserts/dedup, provider refresh policy, ledger stage, and holdings source."""
import base64
import json
from datetime import date, timedelta
from pathlib import Path

import pytest
import yaml

from focos import paths, settings
from focos.holdings.simplefin_holdings import SimpleFINHoldingsSource
from focos.ledger import stage
from focos.ledger.providers import simplefin as sf
from focos.ledger.providers.base import ManualAccountSpec, ProviderError
from focos.ledger.providers.sqlite_store import SQLiteStore

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "simplefin_accounts.json").read_text(encoding="utf-8"))
ASOF = date(2026, 3, 2)


def _payload():
    return json.loads(json.dumps(FIXTURE))


def _provider(home: Path, payload=None, min_hours=20.0):
    calls = []

    def fetcher(start, end, balances_only):
        calls.append((start, end, balances_only))
        return json.loads(json.dumps(payload if payload is not None else FIXTURE))

    p = sf.SimpleFINProvider(store=SQLiteStore(home / "state" / "ledger.sqlite"), fetcher=fetcher, access_url="https://u:p@bridge.simplefin.org/simplefin")
    p.refresh_min_hours = min_hours
    p._calls = calls
    return p


# ---------------------------------------------------------------- parsing
def test_parse_account_types_and_local_dates(initialized_home: Path):
    accts = [sf.parse_account(a) for a in FIXTURE["accounts"]]
    by = {a.id: a for a in accts}
    chk, card, brk = by["simplefin:ACT-CHK-1"], by["simplefin:ACT-CARD-1"], by["simplefin:ACT-BRK-1"]
    assert (chk.account_type, chk.subtype, chk.classification) == ("depository", "checking", "asset")
    assert (card.account_type, card.classification) == ("credit_card", "liability") and card.balance == -410.55
    assert (brk.account_type, brk.subtype) == ("investment", "brokerage")
    assert chk.institution_name == "Example Bank" and chk.balance_cents == 250010 and chk.available_balance == 2400.0
    assert chk.balance_date == "2026-03-01" or chk.balance_date == "2026-03-02"  # local date of the unix stamp
    assert chk.as_row()["classification"] == "asset" and chk.as_row()["source"] == "simplefin"
    txs = sf.parse_transactions(FIXTURE["accounts"][0])
    assert [t["id"] for t in txs] == ["simplefin:ACT-CHK-1:t1", "simplefin:ACT-CHK-1:t2", "simplefin:ACT-CHK-1:t3"]
    assert txs[1]["amount"] == 3000.0 and txs[2]["pending"] is True
    assert sf.parse_holdings(FIXTURE["accounts"][2])[0]["shares"] == 20.0


def test_infer_type_table():
    assert sf.infer_type("HELOC Line")[:1] == ("loan",)
    assert sf.infer_type("Roth IRA") == ("investment", "roth_ira", "asset")
    assert sf.infer_type("Student Loan")[2] == "liability"
    assert sf.infer_type("High Yield Savings") == ("depository", "savings", "asset")
    assert sf.infer_type("Mystery") == ("depository", "checking", "asset")


def test_claim_decodes_token(monkeypatch):
    seen = {}

    class R:
        status_code = 200
        text = "https://user:pw@bridge.simplefin.org/simplefin\n"

    def fake_post(url, timeout):
        seen["url"] = url
        return R()

    monkeypatch.setattr(sf.httpx, "post", fake_post)
    token = base64.b64encode(b"https://bridge.simplefin.org/simplefin/claim/XYZ").decode()
    assert sf.SimpleFINClient.claim(token) == "https://user:pw@bridge.simplefin.org/simplefin"
    assert seen["url"].endswith("/claim/XYZ")
    with pytest.raises(ProviderError):
        sf.SimpleFINClient.claim("not base64 at all!!")


def test_client_strips_credentials_into_auth():
    c = sf.SimpleFINClient("https://alice:secret@bridge.simplefin.org/simplefin/")
    base, auth = c._split()
    assert base == "https://bridge.simplefin.org/simplefin" and auth == ("alice", "secret")


# ---------------------------------------------------------------- store + provider
def test_refresh_ingests_and_respects_min_hours(initialized_home: Path):
    p = _provider(initialized_home)
    res = p.refresh(ASOF, force=True)
    assert res.ok and res.accounts == 3 and res.transactions_new == 4 and res.holdings == 2
    start, end, _ = p._calls[0]
    assert end == ASOF and (ASOF - start).days == 365  # first pull asks for the initial history window
    assert p.refresh(ASOF).skipped is True  # pulled moments ago
    res2 = p.refresh(ASOF, force=True)
    assert res2.transactions_new == 0 and res2.transactions_updated == 4
    start2, _, _ = p._calls[-1]
    assert start2 == ASOF - timedelta(days=95)  # overlap window once history exists
    accts = {a.id: a for a in p.accounts()}
    assert accts["simplefin:ACT-CARD-1"].balance == -410.55
    assert p.sync_status().accounts == 3 and p.health().ok is True


def test_pending_lifecycle(initialized_home: Path):
    p = _provider(initialized_home)
    p.refresh(ASOF, force=True)
    txs = p.transactions(ASOF - timedelta(days=30), ASOF)
    assert {t.external_id for t in txs} == {"t1", "t2", "c1"}  # pending excluded by default
    assert all(t.account_type in ("checking", "credit_card") for t in txs)
    # the pending coffee posts under a new id with the same amount -> old pending row superseded, then dropped
    payload = _payload()
    chk = payload["accounts"][0]
    chk["transactions"] = [t for t in chk["transactions"] if t["id"] != "t3"] + [
        {"id": "t3p", "posted": 1772496000, "amount": "-12.00", "description": "COFFEE PLACE", "payee": "Coffee Place", "pending": False}]
    p2 = _provider(initialized_home, payload)
    p2.refresh(ASOF + timedelta(days=1), force=True)
    ids = {t.external_id for t in p2.transactions(ASOF - timedelta(days=30), ASOF + timedelta(days=2))}
    assert "t3p" in ids and "t3" not in ids
    with_pending = p2.store.transactions(ASOF - timedelta(days=30), ASOF + timedelta(days=2), include_pending=True)
    assert "simplefin:ACT-CHK-1:t3" not in {t.id for t in with_pending}


def test_balances_one_row_per_day_and_manual_accounts(initialized_home: Path):
    p = _provider(initialized_home)
    p.refresh(ASOF, force=True)
    p.refresh(ASOF, force=True)
    pts = p.balances(ASOF - timedelta(days=5), ASOF, ["simplefin:ACT-CHK-1"])
    assert len(pts) == 1 and pts[0].balance == 2500.10
    m = p.upsert_manual_account(ManualAccountSpec(key="cabin", name="Lake cabin", entity="personal", account_type="property",
                                                   balance=180000))
    assert m.id == "manual:cabin" and m.is_manual and m.balance == 180000
    assert {a.id for a in p.accounts()} >= {"manual:cabin", "simplefin:ACT-CHK-1"}
    assert [a.id for a in p.accounts(include_manual=False)] == [a.id for a in p.accounts(include_manual=False) if not a.is_manual]
    p.set_manual_balance("manual:cabin", date.today(), 185000)
    assert next(a for a in p.manual_accounts() if a.id == "manual:cabin").balance == 185000
    assert p.mirror_broker_value("simplefin:ACT-BRK-1", ASOF, 10300.0) is True
    assert p.mirror_broker_value("simplefin:nope", ASOF, 1.0) is False
    bk = p.backup(initialized_home / "state" / "backups" / "ledger.sqlite")
    assert bk.exists()


def test_fetch_error_recorded(initialized_home: Path):
    def boom(start, end, bo):
        raise ProviderError("403 rejected")

    p = sf.SimpleFINProvider(store=SQLiteStore(initialized_home / "state" / "ledger.sqlite"), fetcher=boom, access_url="https://u:p@x/y")
    res = p.refresh(ASOF, force=True)
    assert not res.ok and "403" in res.errors[0]
    assert p.health().ok is False
    assert p.sync_status().last_error


# ---------------------------------------------------------------- stage + holdings
def test_stage_with_simplefin_provider(initialized_home: Path, monkeypatch):
    (initialized_home / "config" / "entities.yml").write_text(yaml.safe_dump({"version": 2, "entities": {
        "personal": {"label": "Personal", "kind": "household", "account_ids": [], "name_hints": "(EXAMPLE BANK|CARD CO|BROKERAGE)"}}}))
    (initialized_home / "config" / "profile.yml").write_text(yaml.safe_dump({"version": 2, "spending": {"monthly_core_expenses": 1000}}))
    settings.reset()
    p = _provider(initialized_home)
    monkeypatch.setattr("focos.ledger.providers.current", lambda name=None: p)
    out = stage.run(None, ASOF.isoformat(), "daily")
    assert out["ok"] is True and out["provider"] == "simplefin" and out["n_accounts"] == 3
    c = out["consolidated"]
    assert c["available"] and abs(c["net_worth"] - (2500.10 + 10250.00 - 410.55)) < 1e-6
    assert c["by_entity"]["personal"]["cash"] == 2500.10
    assert c["personal_runway_months"] == pytest.approx(2.5001)
    assert c["cash_flow"]["30d"]["per_entity"]["personal"]["income"] == 3000.0
    assert c["unmapped_accounts"] == []
    assert (paths.SNAPSHOTS_LEDGER / f"{ASOF.isoformat()}.json").exists()


def test_stage_provider_none(initialized_home: Path):
    (initialized_home / "config" / "focos.yml").write_text("ledger: {provider: none}\n")
    settings.reset()
    out = stage.run(None, "2026-03-02", "daily")
    assert out["ok"] is None and "not configured" in out["reason"]


def test_simplefin_holdings_source(initialized_home: Path, monkeypatch):
    (initialized_home / "config" / "accounts.yml").write_text(yaml.safe_dump({"version": 2, "brokerage": [
        {"key": "brk", "label": "My Brokerage", "role": "taxable", "source": "simplefin_holdings",
         "match": {"ledger_account_id": "simplefin:ACT-BRK-1"}}]}))
    settings.reset()
    p = _provider(initialized_home)
    p.refresh(ASOF, force=True)
    monkeypatch.setattr("focos.ledger.providers.current", lambda name=None: p)
    src = SimpleFINHoldingsSource()
    assert src.available() == (True, None)
    snap = src.capture(ASOF.isoformat(), "daily", "t")
    assert [a["key"] for a in snap["accounts"]] == ["brk"]
    acct = snap["accounts"][0]
    assert acct["nickname"] == "My Brokerage" and acct["portfolio"]["cash"] == 250.0 and acct["portfolio"]["total_value"] == 10250.0
    pos = {p_["symbol"]: p_ for p_ in acct["positions"]}
    assert pos["VTI"]["quantity"] == 20 and pos["VTI"]["price"] == 250.0 and pos["VTI"]["avg_cost"] == 200.0
    assert snap["total_value"] == 10250.0
