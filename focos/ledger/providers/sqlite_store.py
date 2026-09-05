"""Local SQLite ledger: accounts, daily balances, transactions, holdings, manual accounts, pull log.

Used by the SimpleFIN provider and for manual accounts under every provider. One file, no server, honest
history: every pull upserts, nothing is ever thrown away except stale pending rows.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable

from .base import BalancePoint, Holding, LedgerAccount, ManualAccountSpec, Transaction, now_iso

SCHEMA_VERSION = 1
SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
  id TEXT PRIMARY KEY, provider TEXT NOT NULL, org_name TEXT, org_domain TEXT, name TEXT NOT NULL,
  currency TEXT DEFAULT 'USD', account_type TEXT NOT NULL, subtype TEXT, classification TEXT NOT NULL,
  is_manual INTEGER DEFAULT 0, aliases TEXT DEFAULT '[]', first_seen TEXT, last_seen TEXT, raw TEXT);
CREATE TABLE IF NOT EXISTS balances_daily (
  account_id TEXT NOT NULL, date TEXT NOT NULL, balance REAL NOT NULL, available REAL, balance_ts INTEGER,
  source TEXT DEFAULT 'feed', PRIMARY KEY (account_id, date));
CREATE TABLE IF NOT EXISTS transactions (
  id TEXT PRIMARY KEY, account_id TEXT NOT NULL, posted_date TEXT NOT NULL, amount REAL NOT NULL,
  description TEXT, payee TEXT, memo TEXT, pending INTEGER DEFAULT 0, superseded_by TEXT,
  first_seen TEXT, last_seen TEXT, raw TEXT);
CREATE INDEX IF NOT EXISTS ix_tx_acct_date ON transactions(account_id, posted_date);
CREATE TABLE IF NOT EXISTS holdings (
  account_id TEXT NOT NULL, date TEXT NOT NULL, key TEXT NOT NULL, symbol TEXT, description TEXT, shares REAL,
  cost_basis REAL, market_value REAL, currency TEXT, PRIMARY KEY (account_id, date, key));
CREATE TABLE IF NOT EXISTS manual_accounts (
  id TEXT PRIMARY KEY, key TEXT UNIQUE, name TEXT, entity TEXT, account_type TEXT, subtype TEXT,
  classification TEXT, currency TEXT, notes TEXT, created_at TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS pulls (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, provider TEXT, start_date TEXT, end_date TEXT,
  n_accounts INTEGER, n_tx INTEGER, errors TEXT);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
"""
PENDING_MATCH_DAYS = 5


class SQLiteStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # the local API serves requests from a thread pool; sqlite3 (threadsafety 3) serializes access itself
        self.conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=DELETE")
        self.conn.executescript(SCHEMA)
        self.set_meta("schema_version", str(SCHEMA_VERSION))

    def close(self) -> None:
        self.conn.close()

    # ---- meta
    def get_meta(self, key: str, default: str | None = None) -> str | None:
        row = self.conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

    def set_meta(self, key: str, value: str) -> None:
        with self.conn:
            self.conn.execute("INSERT INTO meta(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))

    # ---- accounts
    def upsert_account(self, a: LedgerAccount, raw: dict | None = None) -> None:
        ts = now_iso()
        with self.conn:
            self.conn.execute(
                """INSERT INTO accounts(id, provider, org_name, org_domain, name, currency, account_type, subtype, classification,
                                        is_manual, aliases, first_seen, last_seen, raw)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET org_name=excluded.org_name, org_domain=excluded.org_domain, name=excluded.name,
                        currency=excluded.currency, last_seen=excluded.last_seen, raw=excluded.raw""",
                (a.id, a.provider, a.institution_name, a.org_domain, a.name, a.currency, a.account_type, a.subtype,
                 a.classification, int(a.is_manual), json.dumps(a.aliases), ts, ts, json.dumps(raw or {}, default=str)))

    def set_aliases(self, account_id: str, aliases: list[str]) -> None:
        with self.conn:
            self.conn.execute("UPDATE accounts SET aliases=? WHERE id=?", (json.dumps(sorted(set(aliases))), account_id))

    def set_account_type(self, account_id: str, account_type: str, subtype: str | None, classification: str) -> None:
        with self.conn:
            self.conn.execute("UPDATE accounts SET account_type=?, subtype=?, classification=? WHERE id=?",
                              (account_type, subtype, classification, account_id))

    def accounts(self, providers: Iterable[str] | None = None) -> list[LedgerAccount]:
        rows = self.conn.execute("SELECT * FROM accounts ORDER BY provider, name").fetchall()
        out = []
        for r in rows:
            if providers is not None and r["provider"] not in providers:
                continue
            bal = self.latest_balance(r["id"])
            out.append(LedgerAccount(
                id=r["id"], provider=r["provider"], name=r["name"], institution_name=r["org_name"], org_domain=r["org_domain"],
                currency=r["currency"] or "USD", account_type=r["account_type"], subtype=r["subtype"],
                classification=r["classification"], balance=bal.balance if bal else 0.0,
                balance_cents=int(round((bal.balance if bal else 0.0) * 100)), available_balance=bal.available if bal else None,
                balance_date=bal.date if bal else None, is_manual=bool(r["is_manual"]), aliases=json.loads(r["aliases"] or "[]")))
        return out

    # ---- balances
    def upsert_balance(self, account_id: str, on: str, balance: float, available: float | None = None,
                       balance_ts: int | None = None, source: str = "feed") -> None:
        with self.conn:
            self.conn.execute(
                """INSERT INTO balances_daily(account_id, date, balance, available, balance_ts, source) VALUES(?,?,?,?,?,?)
                   ON CONFLICT(account_id, date) DO UPDATE SET balance=excluded.balance, available=excluded.available,
                        balance_ts=excluded.balance_ts, source=excluded.source
                   WHERE excluded.balance_ts IS NULL OR balances_daily.balance_ts IS NULL OR excluded.balance_ts >= balances_daily.balance_ts""",
                (account_id, on, float(balance), available, balance_ts, source))

    def latest_balance(self, account_id: str) -> BalancePoint | None:
        r = self.conn.execute("SELECT * FROM balances_daily WHERE account_id=? ORDER BY date DESC LIMIT 1", (account_id,)).fetchone()
        return BalancePoint(account_id=r["account_id"], date=r["date"], balance=r["balance"], available=r["available"]) if r else None

    def balances(self, start: date, end: date, account_ids: list[str] | None = None) -> list[BalancePoint]:
        q = "SELECT * FROM balances_daily WHERE date BETWEEN ? AND ?"
        args: list = [start.isoformat(), end.isoformat()]
        if account_ids:
            q += f" AND account_id IN ({','.join('?' * len(account_ids))})"
            args += account_ids
        rows = self.conn.execute(q + " ORDER BY account_id, date", args).fetchall()
        return [BalancePoint(account_id=r["account_id"], date=r["date"], balance=r["balance"], available=r["available"]) for r in rows]

    # ---- transactions
    def upsert_transactions(self, account_id: str, txs: list[dict], seen_ids_this_pull: set[str] | None = None) -> tuple[int, int]:
        """txs: dicts with id, posted_date, amount, description, payee, memo, pending, raw. Returns (new, updated).
        Pending rows for this account that were not returned in this pull are deleted (the bank dropped them);
        a posted row matching a still-pending row (same amount within a few days) marks it superseded."""
        new = updated = 0
        ts = now_iso()
        returned = {t["id"] for t in txs} if seen_ids_this_pull is None else seen_ids_this_pull
        with self.conn:
            for t in txs:
                exists = self.conn.execute("SELECT id FROM transactions WHERE id=?", (t["id"],)).fetchone()
                self.conn.execute(
                    """INSERT INTO transactions(id, account_id, posted_date, amount, description, payee, memo, pending, superseded_by,
                                                first_seen, last_seen, raw) VALUES(?,?,?,?,?,?,?,?,NULL,?,?,?)
                       ON CONFLICT(id) DO UPDATE SET posted_date=excluded.posted_date, amount=excluded.amount,
                            description=excluded.description, payee=excluded.payee, memo=excluded.memo, pending=excluded.pending,
                            last_seen=excluded.last_seen, raw=excluded.raw""",
                    (t["id"], account_id, t["posted_date"], float(t["amount"]), t.get("description"), t.get("payee"), t.get("memo"),
                     int(bool(t.get("pending"))), ts, ts, json.dumps(t.get("raw") or {}, default=str)))
                if exists:
                    updated += 1
                else:
                    new += 1
            # pending rows the bank no longer reports
            stale = self.conn.execute("SELECT id FROM transactions WHERE account_id=? AND pending=1", (account_id,)).fetchall()
            for r in stale:
                if r["id"] not in returned:
                    self.conn.execute("DELETE FROM transactions WHERE id=?", (r["id"],))
            # posted rows that replace a pending one
            for t in txs:
                if t.get("pending"):
                    continue
                lo = (date.fromisoformat(t["posted_date"]) - timedelta(days=PENDING_MATCH_DAYS)).isoformat()
                hi = (date.fromisoformat(t["posted_date"]) + timedelta(days=PENDING_MATCH_DAYS)).isoformat()
                self.conn.execute(
                    """UPDATE transactions SET superseded_by=? WHERE account_id=? AND pending=1 AND superseded_by IS NULL
                       AND ABS(amount - ?) < 0.005 AND posted_date BETWEEN ? AND ? AND id != ?""",
                    (t["id"], account_id, float(t["amount"]), lo, hi, t["id"]))
        return new, updated

    def transactions(self, start: date, end: date, account_ids: list[str] | None = None, include_pending: bool = False,
                     providers: Iterable[str] | None = None, legacy_providers: Iterable[str] | None = None,
                     legacy_before: dict[str, str | None] | None = None) -> list[Transaction]:
        """legacy_providers: providers whose rows are only history (imported from a retired ledger). Their rows are
        returned only when legacy_before names the account, and then only before that account's cutoff date
        (None = no cutoff). transfer_id / other_account_id come from raw when an import recorded them."""
        q = """SELECT t.*, a.name AS account_name, a.account_type AS account_type, a.subtype AS subtype, a.provider AS provider
               FROM transactions t JOIN accounts a ON a.id = t.account_id WHERE t.posted_date BETWEEN ? AND ?"""
        args: list = [start.isoformat(), end.isoformat()]
        if not include_pending:
            q += " AND t.pending = 0"
        else:
            q += " AND t.superseded_by IS NULL"
        if account_ids:
            q += f" AND t.account_id IN ({','.join('?' * len(account_ids))})"
            args += account_ids
        if providers is not None:
            provs = list(providers)
            q += f" AND a.provider IN ({','.join('?' * len(provs))})"
            args += provs
        rows = self.conn.execute(q + " ORDER BY t.posted_date, t.id", args).fetchall()
        legacy_set = set(legacy_providers or ())
        out = []
        for r in rows:
            if r["provider"] in legacy_set:
                if legacy_before is None or r["account_id"] not in legacy_before:
                    continue
                cutoff = legacy_before[r["account_id"]]
                if cutoff is not None and r["posted_date"] >= cutoff:
                    continue
            try:
                raw = json.loads(r["raw"] or "{}")
            except ValueError:
                raw = {}
            acct_type = r["subtype"] or r["account_type"] or ""
            out.append(Transaction(id=r["id"], date=r["posted_date"], account_id=r["account_id"], account_name=r["account_name"],
                                   account_type=str(acct_type).lower(), amount=r["amount"], name=r["description"], merchant=r["payee"],
                                   category=None, tags=[], transfer_id=raw.get("transfer_id") or None,
                                   other_account_id=raw.get("other_account_id") or None,
                                   external_id=r["id"].split(":")[-1], source=r["provider"], pending=bool(r["pending"])))
        return out

    # ---- legacy history and account identity
    def providers_present(self) -> list[str]:
        return [r["provider"] for r in self.conn.execute("SELECT DISTINCT provider FROM accounts ORDER BY provider").fetchall()]

    def account_raw(self, account_id: str) -> dict:
        r = self.conn.execute("SELECT raw FROM accounts WHERE id=?", (account_id,)).fetchone()
        try:
            return json.loads(r["raw"] or "{}") if r else {}
        except ValueError:
            return {}

    def first_transaction_date(self, account_id: str) -> str | None:
        r = self.conn.execute("SELECT MIN(posted_date) AS d FROM transactions WHERE account_id=? AND pending=0", (account_id,)).fetchone()
        return r["d"] if r and r["d"] else None

    def first_pull(self, provider: str) -> dict | None:
        r = self.conn.execute("SELECT * FROM pulls WHERE provider=? AND errors='[]' ORDER BY id ASC LIMIT 1", (provider,)).fetchone()
        return dict(r) if r else None

    def legacy_cutoffs(self, primary: Iterable[str], legacy: Iterable[str]) -> dict[str, str | None]:
        """{legacy account id: first date NOT to read from it}. An account aliased from a live one stops where the
        live account's own history starts; the rest use meta legacy_cutoff:<id>, then the global legacy_cutoff,
        else None (read everything, right for accounts that closed before the switch)."""
        legacy = tuple(legacy)
        if not legacy:
            return {}
        global_cut = self.get_meta("legacy_cutoff")
        out: dict[str, str | None] = {}
        for r in self.conn.execute(f"SELECT id FROM accounts WHERE provider IN ({','.join('?' * len(legacy))})", legacy).fetchall():
            out[r["id"]] = self.get_meta(f"legacy_cutoff:{r['id']}", global_cut)
        primary = tuple(primary)
        for r in self.conn.execute(f"SELECT id, aliases FROM accounts WHERE provider IN ({','.join('?' * len(primary))})", primary).fetchall():
            first = self.first_transaction_date(r["id"])
            for alias in json.loads(r["aliases"] or "[]"):
                if alias in out and first:
                    out[alias] = first
        return out

    def rename_account(self, old_id: str, new_id: str, provider: str | None = None, is_manual: bool | None = None) -> None:
        """Move an account and all its rows to a new id (rows already under new_id are replaced)."""
        with self.conn:
            self.conn.execute("UPDATE OR REPLACE accounts SET id=? WHERE id=?", (new_id, old_id))
            if provider is not None:
                self.conn.execute("UPDATE accounts SET provider=? WHERE id=?", (provider, new_id))
            if is_manual is not None:
                self.conn.execute("UPDATE accounts SET is_manual=? WHERE id=?", (int(is_manual), new_id))
            for table in ("balances_daily", "transactions", "holdings"):
                self.conn.execute(f"UPDATE OR REPLACE {table} SET account_id=? WHERE account_id=?", (new_id, old_id))
            for r in self.conn.execute("SELECT id, aliases FROM accounts").fetchall():
                aliases = json.loads(r["aliases"] or "[]")
                if old_id in aliases:
                    self.conn.execute("UPDATE accounts SET aliases=? WHERE id=?",
                                      (json.dumps(sorted({new_id if a == old_id else a for a in aliases})), r["id"]))
            self.conn.execute("DELETE FROM meta WHERE key=?", (f"legacy_cutoff:{old_id}",))

    def adopt_account(self, old_id: str, spec: ManualAccountSpec) -> LedgerAccount:
        """Give an imported legacy account a manual identity (manual:<key>) without losing its balances or
        transactions. No balance is written: the history stays exactly as imported."""
        new_id = f"manual:{spec.key}"
        if new_id != old_id:
            self.rename_account(old_id, new_id, provider="manual", is_manual=True)
        ts = now_iso()
        with self.conn:
            self.conn.execute("UPDATE accounts SET name=?, account_type=?, subtype=?, classification=?, currency=?, last_seen=? WHERE id=?",
                              (spec.name, spec.account_type, spec.subtype, spec.classification, spec.currency, ts, new_id))
            self.conn.execute(
                """INSERT INTO manual_accounts(id, key, name, entity, account_type, subtype, classification, currency, notes, created_at, updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET name=excluded.name, entity=excluded.entity, account_type=excluded.account_type,
                        subtype=excluded.subtype, classification=excluded.classification, updated_at=excluded.updated_at""",
                (new_id, spec.key, spec.name, spec.entity, spec.account_type, spec.subtype, spec.classification, spec.currency,
                 spec.notes, ts, ts))
        return next(a for a in self.accounts(providers=("manual",)) if a.id == new_id)

    # ---- holdings
    def upsert_holdings(self, account_id: str, on: str, holdings: list[dict]) -> int:
        n = 0
        with self.conn:
            self.conn.execute("DELETE FROM holdings WHERE account_id=? AND date=?", (account_id, on))
            for h in holdings:
                key = (h.get("symbol") or h.get("description") or h.get("id") or "").strip().upper()
                if not key:
                    continue
                self.conn.execute(
                    "INSERT OR REPLACE INTO holdings(account_id, date, key, symbol, description, shares, cost_basis, market_value, currency) VALUES(?,?,?,?,?,?,?,?,?)",
                    (account_id, on, key, (h.get("symbol") or None), h.get("description"), h.get("shares"), h.get("cost_basis"),
                     h.get("market_value"), h.get("currency") or "USD"))
                n += 1
        return n

    def holdings(self, asof: date | None = None) -> list[Holding]:
        """Latest holdings per account on or before asof."""
        cutoff = (asof or date.today()).isoformat()
        rows = self.conn.execute(
            """SELECT h.* FROM holdings h JOIN (SELECT account_id, MAX(date) AS d FROM holdings WHERE date <= ? GROUP BY account_id) m
               ON m.account_id = h.account_id AND m.d = h.date ORDER BY h.account_id, h.market_value DESC""", (cutoff,)).fetchall()
        return [Holding(account_id=r["account_id"], date=r["date"], symbol=r["symbol"], description=r["description"],
                        shares=r["shares"] or 0.0, cost_basis=r["cost_basis"], market_value=r["market_value"],
                        currency=r["currency"] or "USD") for r in rows]

    # ---- manual accounts
    def upsert_manual_account(self, spec: ManualAccountSpec) -> LedgerAccount:
        aid = f"manual:{spec.key}"
        ts = now_iso()
        with self.conn:
            self.conn.execute(
                """INSERT INTO manual_accounts(id, key, name, entity, account_type, subtype, classification, currency, notes, created_at, updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET name=excluded.name, entity=excluded.entity, account_type=excluded.account_type,
                        subtype=excluded.subtype, classification=excluded.classification, currency=excluded.currency,
                        notes=excluded.notes, updated_at=excluded.updated_at""",
                (aid, spec.key, spec.name, spec.entity, spec.account_type, spec.subtype, spec.classification, spec.currency,
                 spec.notes, ts, ts))
        acct = LedgerAccount(id=aid, provider="manual", name=spec.name, account_type=spec.account_type, subtype=spec.subtype,
                             classification=spec.classification, currency=spec.currency, is_manual=True)
        self.upsert_account(acct)
        self.upsert_balance(aid, date.today().isoformat(), spec.balance, source="manual")
        return next(a for a in self.accounts(providers=("manual",)) if a.id == aid)

    def manual_entities(self) -> dict[str, str]:
        return {r["id"]: r["entity"] for r in self.conn.execute("SELECT id, entity FROM manual_accounts").fetchall()}

    # ---- pulls
    def record_pull(self, provider: str, start: str, end: str, n_accounts: int, n_tx: int, errors: list[str]) -> None:
        with self.conn:
            self.conn.execute("INSERT INTO pulls(ts, provider, start_date, end_date, n_accounts, n_tx, errors) VALUES(?,?,?,?,?,?,?)",
                              (now_iso(), provider, start, end, n_accounts, n_tx, json.dumps(errors)))

    def last_pull(self, provider: str, ok_only: bool = True) -> dict | None:
        q = "SELECT * FROM pulls WHERE provider=?" + (" AND errors='[]'" if ok_only else "") + " ORDER BY id DESC LIMIT 1"
        r = self.conn.execute(q, (provider,)).fetchone()
        return dict(r) if r else None

    def last_pull_age_hours(self, provider: str) -> float | None:
        p = self.last_pull(provider)
        if not p:
            return None
        try:
            ts = datetime.fromisoformat(p["ts"])
        except ValueError:
            return None
        return (datetime.now().astimezone() - ts).total_seconds() / 3600.0

    # ---- maintenance
    def backup(self, dest: Path) -> Path:
        dest.parent.mkdir(parents=True, exist_ok=True)
        target = sqlite3.connect(str(dest))
        try:
            self.conn.backup(target)
        finally:
            target.close()
        return dest

    def vacuum(self) -> None:
        self.conn.execute("VACUUM")

    def counts(self) -> dict:
        return {t: self.conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                for t in ("accounts", "balances_daily", "transactions", "holdings", "manual_accounts", "pulls")}
