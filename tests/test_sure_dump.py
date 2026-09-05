"""Sure pg_dump parser and import: types, signs, transfer pairs, escapes, date filters."""
from datetime import date
from pathlib import Path

from focos.ledger.legacy import sure_dump as sd
from focos.ledger.providers.sqlite_store import SQLiteStore

FIX = Path(__file__).parent / "fixtures" / "sure_dump.sql"


def test_parse_accounts_types_and_balances():
    b = sd.parse_copy_blocks(FIX)
    assert {k: len(v) for k, v in b.items()} == {"accounts": 5, "entries": 7, "transactions": 6, "transfers": 1, "balances": 7}
    by = {a.id: (a, r) for a, r in sd.accounts(b)}
    chk, _ = by["sure:acc-chk"]
    assert (chk.account_type, chk.subtype, chk.balance, chk.balance_date) == ("depository", "checking", 1500.0, "2026-01-02")
    card, raw = by["sure:acc-card"]
    assert card.classification == "liability" and card.balance == -410.55 and raw["simplefin_account_id"] == "ACT-CARD-1"
    loan, _ = by["sure:acc-loan"]
    assert (loan.account_type, loan.subtype, loan.balance) == ("loan", "student", -12000.0)
    prop, raw = by["sure:acc-prop"]
    assert prop.account_type == "property" and raw["simplefin_account_id"] is None
    assert by["sure:acc-biz"][0].institution_name == "Mercury"


def test_transactions_sign_transfers_and_escapes():
    tx = sd.transactions(sd.parse_copy_blocks(FIX))
    chk = {t["id"]: t for t in tx["sure:acc-chk"]}
    assert set(chk) == {"sure:acc-chk:e-1", "sure:acc-chk:e-2", "sure:acc-chk:e-3", "sure:acc-chk:e-7"}  # excluded + valuation skipped
    assert chk["sure:acc-chk:e-1"]["amount"] == -52.1 and chk["sure:acc-chk:e-2"]["amount"] == 3000.0  # Sure stores outflows positive
    assert chk["sure:acc-chk:e-2"]["memo"] == "Tab\tsafe"
    t3 = chk["sure:acc-chk:e-3"]
    assert t3["raw"]["transfer_id"] == "tr-1" and t3["raw"]["other_account_id"] == "sure:acc-biz" and t3["raw"]["kind"] == "funds_movement"
    biz = tx["sure:acc-biz"][0]
    assert biz["amount"] == 500.0 and biz["raw"]["other_account_id"] == "sure:acc-chk"
    assert "sure:acc-prop" not in tx


def test_import_dump_into_store(tmp_path):
    store = SQLiteStore(tmp_path / "ledger.sqlite")
    dry = sd.import_dump(FIX, store, dry_run=True)
    assert dry["accounts"] == 5 and dry["transactions"] == 5 and store.counts()["accounts"] == 0
    out = sd.import_dump(FIX, store, since=date(2026, 1, 1))
    assert out["transactions"] == 4 and out["balance_points"] == 6 and out["with_simplefin_id"] == 2
    accts = {a.id: a for a in store.accounts()}
    assert accts["sure:acc-card"].balance == -410.55 and accts["sure:acc-loan"].balance == -12000.0  # liabilities negative
    assert accts["sure:acc-chk"].balance == 1500.0
    rows = store.transactions(date(2026, 1, 1), date(2026, 1, 31))
    t3 = next(t for t in rows if t.id == "sure:acc-chk:e-3")
    assert t3.transfer_id == "tr-1" and t3.other_account_id == "sure:acc-biz"
    assert store.get_meta("sure_import") == "sure_dump.sql" and store.first_pull("sure")["n_tx"] == 4
    assert store.providers_present() == ["sure"] and store.account_raw("sure:acc-chk")["simplefin_account_id"] == "ACT-CHK-1"
