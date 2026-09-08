"""SQLite ledger schema v2: migration of an existing v1 file, merchant keys, rule application, user overrides."""
import sqlite3
from pathlib import Path

from focos.ledger.providers import sqlite_store as ss
from focos.ledger.providers.base import LedgerAccount
from focos.ledger.providers.sqlite_store import SQLiteStore

V1_SCHEMA = """
CREATE TABLE accounts (
  id TEXT PRIMARY KEY, provider TEXT NOT NULL, org_name TEXT, org_domain TEXT, name TEXT NOT NULL,
  currency TEXT DEFAULT 'USD', account_type TEXT NOT NULL, subtype TEXT, classification TEXT NOT NULL,
  is_manual INTEGER DEFAULT 0, aliases TEXT DEFAULT '[]', first_seen TEXT, last_seen TEXT, raw TEXT);
CREATE TABLE transactions (
  id TEXT PRIMARY KEY, account_id TEXT NOT NULL, posted_date TEXT NOT NULL, amount REAL NOT NULL,
  description TEXT, payee TEXT, memo TEXT, pending INTEGER DEFAULT 0, superseded_by TEXT,
  first_seen TEXT, last_seen TEXT, raw TEXT);
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
INSERT INTO meta VALUES ('schema_version', '1');
INSERT INTO accounts(id, provider, name, account_type, classification) VALUES ('simplefin:A', 'simplefin', 'Checking', 'depository', 'asset');
INSERT INTO transactions(id, account_id, posted_date, amount, description, payee, pending) VALUES
  ('t1', 'simplefin:A', '2026-09-01', -12.5, 'STARBUCKS STORE 10023', NULL, 0),
  ('t2', 'simplefin:A', '2026-09-02', -80.0, 'ALDI 77166 VERO BEACH', NULL, 0),
  ('t3', 'simplefin:A', '2026-09-03', -30.0, 'STARBUCKS STORE 10488', 'Starbucks', 0),
  ('t4', 'simplefin:A', '2026-09-03', 2000.0, 'PAYROLL', NULL, 0);
"""


def _v1_file(home: Path) -> Path:
    p = home / "state" / "ledger.sqlite"
    p.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(p))
    c.executescript(V1_SCHEMA)
    c.close()
    return p


def test_v1_file_migrates_with_backup_and_backfill(initialized_home: Path):
    p = _v1_file(initialized_home)
    store = SQLiteStore(p)
    cols = {r["name"] for r in store.conn.execute("PRAGMA table_info(transactions)").fetchall()}
    assert {"merchant_key", "category", "category_source"} <= cols
    assert store.get_meta("schema_version") == "2" and ss.SCHEMA_VERSION == 2
    keys = {r["id"]: r["merchant_key"] for r in store.conn.execute("SELECT id, merchant_key FROM transactions").fetchall()}
    assert keys == {"t1": "STARBUCKS", "t2": "ALDI", "t3": "STARBUCKS", "t4": "PAYROLL"}
    backups = list((initialized_home / "state" / "backups").glob("ledger-pre-v2-*.sqlite"))
    assert len(backups) == 1
    assert store.counts()["merchant_rules"] == 0
    store.close()
    again = SQLiteStore(p)  # idempotent
    assert len(list((initialized_home / "state" / "backups").glob("ledger-pre-v2-*.sqlite"))) == 1
    again.close()


def test_rules_apply_and_user_overrides_seed(initialized_home: Path):
    p = _v1_file(initialized_home)
    store = SQLiteStore(p)
    unc = store.uncategorized_merchants("2026-08-01", "2026-09-30")
    assert [m["merchant_key"] for m in unc] == ["STARBUCKS", "ALDI"] and unc[0]["n"] == 2 and unc[0]["total"] == 42.5
    store.set_merchant_rule("STARBUCKS", "dining", "seed", 0.9, "Starbucks")
    assert store.apply_category_rules("2026-08-01") == 2
    rows = {r["id"]: (r["category"], r["category_source"]) for r in store.conn.execute("SELECT id, category, category_source FROM transactions")}
    assert rows["t1"] == ("dining", "seed") and rows["t3"] == ("dining", "seed") and rows["t2"] == (None, None)
    assert store.apply_category_rules("2026-08-01") == 0  # nothing left to change
    store.set_merchant_rule("STARBUCKS", "entertainment", "user", 1.0)
    assert store.apply_category_rules("2026-08-01") == 2
    assert store.merchant_rule("STARBUCKS")["source"] == "user" and store.merchant_rule("STARBUCKS")["display_name"] == "Starbucks"
    assert [m["merchant_key"] for m in store.uncategorized_merchants("2026-08-01", "2026-09-30")] == ["ALDI"]
    counts = store.category_counts("2026-08-01")
    assert counts["entertainment"] == {"n": 2, "spend": 42.5} and counts["uncategorized"] == {"n": 1, "spend": 80.0}
    txs = store.transactions(__import__("datetime").date(2026, 8, 1), __import__("datetime").date(2026, 9, 30))
    by_id = {t.id: t for t in txs}
    assert by_id["t1"].category == "entertainment" and by_id["t1"].model_dump()["merchant_key"] == "STARBUCKS"
    store.close()


def test_low_confidence_rule_is_reasked_after_stale_days(initialized_home: Path):
    p = _v1_file(initialized_home)
    store = SQLiteStore(p)
    store.set_merchant_rule("ALDI", "uncategorized", "model", 0.3)
    assert [m["merchant_key"] for m in store.uncategorized_merchants("2026-08-01", "2026-09-30")] == ["STARBUCKS"]
    store.conn.execute("UPDATE merchant_rules SET updated_at='2026-01-01T00:00:00' WHERE merchant_key='ALDI'")
    assert {m["merchant_key"] for m in store.uncategorized_merchants("2026-08-01", "2026-09-30")} == {"STARBUCKS", "ALDI"}
    store.close()


def test_fresh_store_sets_merchant_key_on_insert(initialized_home: Path):
    store = SQLiteStore(initialized_home / "state" / "ledger.sqlite")
    store.upsert_account(LedgerAccount(id="simplefin:B", provider="simplefin", name="Card", account_type="credit_card", classification="liability"))
    store.upsert_transactions("simplefin:B", [{"id": "x1", "posted_date": "2026-09-05", "amount": -9.99, "description": "Netflix.com", "payee": None}])
    assert store.conn.execute("SELECT merchant_key FROM transactions WHERE id='x1'").fetchone()[0] == "NETFLIX"
    assert not list((initialized_home / "state" / "backups").glob("ledger-pre-v2-*"))  # nothing to migrate
    store.close()
