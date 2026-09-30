"""Balances you know that the bank feed does not: a loan whose connection broke, read off a statement.

`focos ledger set-balance "<account>" <amount>` records the number on the account the feed already created, so
nothing is double counted and, if the connection ever comes back, the live feed simply takes over again (a
newer feed balance always wins).

A loan also keeps itself current: give it the rate, the payment, and the day it is paid (`--rate 10.3
--payment 1550 --day 21`), and every run after a payment date writes the balance that payment leaves (one
month's interest on the balance, the rest off principal), marked `projected`. A newer statement number resets
it. While an account is tracked this way focos stops asking you to reconnect it.
"""
from __future__ import annotations

import json
import re
from datetime import date, timedelta

META_PREFIX = "amortize:"
OWN_SOURCES = ("manual", "projected")


def _store(provider=None):
    if provider is None:
        from . import providers

        provider = providers.current()
    store = getattr(provider, "store", None)
    if store is None:
        raise RuntimeError("manual balances need the SQLite ledger (ledger.provider simplefin or manual)")
    return store


def find_account(store, query: str) -> dict:
    """An account by exact id, else by a case-insensitive match on its name or institution."""
    rows = [dict(r) for r in store.conn.execute("SELECT id, name, org_name, classification, account_type FROM accounts")]
    exact = [r for r in rows if r["id"] == query]
    if exact:
        return exact[0]
    pat = re.compile(re.escape(query), re.I)
    hits = [r for r in rows if pat.search(r["name"] or "") or pat.search(r["org_name"] or "")]
    live = [r for r in hits if not str(r["id"]).startswith("sure:")]      # imported history rows alias the live one
    hits = live or hits
    if len(hits) != 1:
        names = ", ".join(f"{r['id']} ({r['name']})" for r in hits) or "none"
        raise ValueError(f"'{query}' matches {len(hits)} accounts: {names}. Use the account id.")
    return hits[0]


def set_balance(query: str, amount: float, as_of: str | None = None, rate_pct: float | None = None,
                payment: float | None = None, day: int | None = None, provider=None) -> dict:
    store = _store(provider)
    acct = find_account(store, query)
    as_of = as_of or date.today().isoformat()
    liability = acct["classification"] == "liability"
    value = -abs(float(amount)) if liability else float(amount)
    store.upsert_balance(acct["id"], as_of, value, source="manual")
    plan = None
    if rate_pct is not None or payment is not None or day is not None:
        old = get_plan(store, acct["id"]) or {}
        plan = {"rate_pct": rate_pct if rate_pct is not None else old.get("rate_pct"),
                "payment": payment if payment is not None else old.get("payment"),
                "day": int(day) if day is not None else old.get("day")}
        if not all(plan.get(k) for k in ("rate_pct", "payment", "day")):
            raise ValueError("a self-updating loan needs --rate, --payment, and --day")
        store.set_meta(META_PREFIX + acct["id"], json.dumps(plan))
    return {"account_id": acct["id"], "name": acct["name"], "institution": acct["org_name"], "as_of": as_of,
            "balance": value, "self_updating": plan or get_plan(store, acct["id"])}


def get_plan(store, account_id: str) -> dict | None:
    raw = store.get_meta(META_PREFIX + account_id)
    try:
        return json.loads(raw) if raw else None
    except ValueError:
        return None


def _latest(store, account_id: str, sources: tuple[str, ...] | None = None) -> dict | None:
    q = "SELECT date, balance, source FROM balances_daily WHERE account_id=?"
    args: list = [account_id]
    if sources:
        q += f" AND source IN ({','.join('?' * len(sources))})"
        args += list(sources)
    r = store.conn.execute(q + " ORDER BY date DESC LIMIT 1", args).fetchone()
    return dict(r) if r else None


def _payment_dates(after: date, through: date, day: int) -> list[date]:
    out, d = [], after + timedelta(days=1)
    while d <= through:
        last = (d.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        if d.day == min(day, last.day):
            out.append(d)
        d += timedelta(days=1)
    return out


def project(asof: str, provider=None) -> list[dict]:
    """Roll every self-updating loan forward through the payment dates since its last balance. Returns what was
    written. A feed balance newer than ours means the connection is back, so the feed is left alone."""
    store = _store(provider)
    out = []
    for r in store.conn.execute("SELECT key, value FROM meta WHERE key LIKE ?", (META_PREFIX + "%",)).fetchall():
        account_id = r["key"][len(META_PREFIX):]
        try:
            plan = json.loads(r["value"])
        except ValueError:
            continue
        last = _latest(store, account_id)
        if not last or last["source"] not in OWN_SOURCES:
            continue
        bal = abs(float(last["balance"]))
        monthly = float(plan["rate_pct"]) / 100 / 12
        for d in _payment_dates(date.fromisoformat(last["date"]), date.fromisoformat(asof), int(plan["day"])):
            interest = round(bal * monthly, 2)
            bal = max(0.0, round(bal + interest - float(plan["payment"]), 2))
            store.upsert_balance(account_id, d.isoformat(), -bal, source="projected")
            out.append({"account_id": account_id, "date": d.isoformat(), "balance": -bal, "interest": interest})
    return out


def tracked_institutions(provider=None) -> set[str]:
    """Institutions whose every account has a balance of ours newer than anything the feed sent: the owner is
    keeping them by hand, so a broken connection there is not something to nag about."""
    try:
        store = _store(provider)
    except RuntimeError:
        return set()
    by_org: dict[str, list[bool]] = {}
    for a in store.conn.execute("SELECT id, org_name FROM accounts WHERE org_name IS NOT NULL").fetchall():
        mine = _latest(store, a["id"], OWN_SOURCES)
        feed = _latest(store, a["id"], ("feed",))
        by_org.setdefault(a["org_name"], []).append(bool(mine and (not feed or mine["date"] >= feed["date"])))
    return {org for org, flags in by_org.items() if flags and all(flags)}
