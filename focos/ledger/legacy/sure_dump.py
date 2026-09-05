"""Read a plain-format ``pg_dump`` of a Sure (Maybe) database and load its accounts, transactions, and daily
balances into the local SQLite ledger. Works long after the Sure containers are gone.

Only the ``COPY public.<table> (...) FROM stdin;`` blocks are parsed (tab separated, ``\\N`` for NULL, the
usual backslash escapes). Sure stores outflows as positive entry amounts; focos stores inflows positive, so
amounts are negated. Transfer pairs Sure matched are kept in ``raw`` so netting still sees them.
"""
from __future__ import annotations

import io
import re
from datetime import date
from pathlib import Path

from ..providers.base import LedgerAccount
from ..providers.sqlite_store import SQLiteStore

PROVIDER = "sure"
TABLES = ("accounts", "entries", "transactions", "transfers", "balances")
TYPE_MAP: dict[str, tuple[str, str]] = {          # accountable_type -> (account_type, classification)
    "Depository": ("depository", "asset"),
    "CreditCard": ("credit_card", "liability"),
    "Loan": ("loan", "liability"),
    "Investment": ("investment", "asset"),
    "Crypto": ("investment", "asset"),
    "Property": ("property", "asset"),
    "Vehicle": ("vehicle", "asset"),
    "OtherAsset": ("other", "asset"),
    "OtherLiability": ("other", "liability"),
}
_COPY_RE = re.compile(r"^COPY public\.(\w+) \((.*)\) FROM stdin;$")
_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "b": "\b", "f": "\f", "v": "\v", "\\": "\\"}


def _unescape(field: str) -> str | None:
    if field == "\\N":
        return None
    if "\\" not in field:
        return field
    out, i = [], 0
    while i < len(field):
        ch = field[i]
        if ch == "\\" and i + 1 < len(field):
            out.append(_ESCAPES.get(field[i + 1], field[i + 1]))
            i += 2
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def parse_copy_blocks(path: Path, tables: tuple[str, ...] = TABLES) -> dict[str, list[dict]]:
    """{table: [row dict keyed by column]} for the requested tables; other blocks are skipped."""
    out: dict[str, list[dict]] = {t: [] for t in tables}
    text = Path(path).read_text(encoding="utf-8-sig", errors="replace")
    cols: list[str] | None = None
    table: str | None = None
    for line in io.StringIO(text):
        line = line.rstrip("\r\n")
        if cols is None:
            m = _COPY_RE.match(line)
            if m and m.group(1) in out:
                table = m.group(1)
                cols = [c.strip() for c in m.group(2).split(",")]
            continue
        if line == "\\.":
            cols = table = None
            continue
        fields = line.split("\t")
        if len(fields) != len(cols):
            continue
        out[table].append({c: _unescape(v) for c, v in zip(cols, fields)})
    return out


def account_id(sure_id: str) -> str:
    return f"{PROVIDER}:{sure_id}"


def _f(v: str | None) -> float:
    try:
        return float(v) if v not in (None, "") else 0.0
    except ValueError:
        return 0.0


def accounts(blocks: dict[str, list[dict]]) -> list[tuple[LedgerAccount, dict]]:
    """(LedgerAccount, raw) per Sure account. raw keeps the fields later steps use (simplefin_account_id,
    accountable_type, status, disabled_at) and never the balance history."""
    latest: dict[str, tuple[str, float, float | None]] = {}
    for b in blocks.get("balances", []):
        aid, d = b.get("account_id"), b.get("date")
        if not aid or not d:
            continue
        cur = latest.get(aid)
        if cur is None or d > cur[0]:
            latest[aid] = (d, _f(b.get("balance")), _f(b.get("cash_balance")) if b.get("cash_balance") not in (None, "") else None)
    out = []
    for a in blocks.get("accounts", []):
        kind = a.get("accountable_type") or "OtherAsset"
        account_type, classification = TYPE_MAP.get(kind, ("other", "asset"))
        subtype = (a.get("subtype") or None)
        bal_date, bal, cash = latest.get(a["id"], (None, _f(a.get("balance")), None))
        signed = -abs(bal) if classification == "liability" else bal
        acct = LedgerAccount(
            id=account_id(a["id"]), provider=PROVIDER, name=a.get("name") or a["id"], institution_name=a.get("institution_name"),
            org_domain=a.get("institution_domain"), currency=a.get("currency") or "USD", account_type=account_type,
            subtype=subtype, classification=classification, balance=signed, balance_cents=int(round(signed * 100)),
            available_balance=cash, balance_date=bal_date)
        raw = {"sure_id": a["id"], "accountable_type": kind, "subtype": subtype, "status": a.get("status"),
               "disabled_at": a.get("disabled_at"), "simplefin_account_id": a.get("simplefin_account_id"),
               "plaid_account_id": a.get("plaid_account_id"), "exclude_from_reports": a.get("exclude_from_reports")}
        out.append((acct, raw))
    return out


def transactions(blocks: dict[str, list[dict]]) -> dict[str, list[dict]]:
    """{ledger account id: [transaction dicts for SQLiteStore.upsert_transactions]} from Transaction entries."""
    tx_meta = {t["id"]: t for t in blocks.get("transactions", [])}
    transfer_of: dict[str, str] = {}          # transaction id -> transfer id
    partner_of: dict[str, str] = {}           # transaction id -> the other transaction id
    for tr in blocks.get("transfers", []):
        a, b = tr.get("inflow_transaction_id"), tr.get("outflow_transaction_id")
        for x, y in ((a, b), (b, a)):
            if x:
                transfer_of[x] = tr["id"]
                if y:
                    partner_of[x] = y
    entry_by_tx: dict[str, dict] = {}
    entries = [e for e in blocks.get("entries", []) if e.get("entryable_type") == "Transaction"]
    for e in entries:
        entry_by_tx[e["entryable_id"]] = e
    out: dict[str, list[dict]] = {}
    for e in entries:
        if (e.get("excluded") or "f") == "t" or not e.get("date") or not e.get("account_id"):
            continue
        tid = e["entryable_id"]
        meta = tx_meta.get(tid, {})
        aid = account_id(e["account_id"])
        partner = entry_by_tx.get(partner_of.get(tid, ""))
        raw = {"sure_entry_id": e["id"], "sure_transaction_id": tid, "kind": meta.get("kind"),
               "transfer_id": transfer_of.get(tid) or meta.get("transfer_id"),
               "other_account_id": account_id(partner["account_id"]) if partner else None,
               "external_id": e.get("external_id"), "source": e.get("source")}
        out.setdefault(aid, []).append({
            "id": f"{aid}:{e['id']}", "posted_date": e["date"][:10], "amount": -_f(e.get("amount")),
            "description": e.get("name"), "payee": None, "memo": e.get("notes"), "pending": False, "raw": raw})
    return out


def balances(blocks: dict[str, list[dict]]) -> list[tuple[str, str, float, float | None]]:
    out = []
    for b in blocks.get("balances", []):
        if b.get("account_id") and b.get("date"):
            out.append((account_id(b["account_id"]), b["date"][:10], _f(b.get("balance")),
                        _f(b.get("cash_balance")) if b.get("cash_balance") not in (None, "") else None))
    return out


def import_dump(path: Path, store: SQLiteStore, since: date | None = None, until: date | None = None,
                dry_run: bool = False) -> dict:
    """Load the dump into the store. Liability balances are stored negative (focos convention)."""
    blocks = parse_copy_blocks(path)
    accts = accounts(blocks)
    liability = {a.id for a, _ in accts if a.classification == "liability"}
    txs = transactions(blocks)
    bals = balances(blocks)
    lo, hi = (since.isoformat() if since else "0000-00-00"), (until.isoformat() if until else "9999-12-31")
    n_tx = n_bal = 0
    for acct, raw in accts:
        if not dry_run:
            store.upsert_account(acct, raw=raw)
    for aid, rows in txs.items():
        rows = [r for r in rows if lo <= r["posted_date"] <= hi]
        n_tx += len(rows)
        if rows and not dry_run:
            store.upsert_transactions(aid, rows, seen_ids_this_pull=set())
    for aid, d, bal, cash in bals:
        if not (lo <= d <= hi):
            continue
        n_bal += 1
        if not dry_run:
            store.upsert_balance(aid, d, -abs(bal) if aid in liability else bal, cash, source="sure")
    if not dry_run:
        store.record_pull(PROVIDER, lo if since else (min((d for _, d, _, _ in bals), default=hi)), hi if until else date.today().isoformat(),
                          len(accts), n_tx, [])
        store.set_meta("sure_import", f"{Path(path).name}")
    return {"dump": str(path), "accounts": len(accts), "transactions": n_tx, "balance_points": n_bal,
            "with_simplefin_id": sum(1 for _, r in accts if r.get("simplefin_account_id")), "dry_run": dry_run,
            "db": str(store.path)}
