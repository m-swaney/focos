"""Holdings reported by the SimpleFIN feed for brokerage accounts (when the institution provides them)."""
from __future__ import annotations

import re
from datetime import date

from .. import settings
from ..ledger import providers
from . import write_snapshot
from .base import SourceError, account_entry, empty_snapshot, finish_snapshot, position_entry


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return s[:40] or "acct"


class SimpleFINHoldingsSource:
    name = "simplefin_holdings"

    def available(self) -> tuple[bool, str | None]:
        if providers.configured_name() != "simplefin":
            return False, "holdings.source simplefin_holdings needs ledger.provider simplefin"
        p = providers.current()
        h = p.health()
        if not h.ok:
            return False, h.reason or "SimpleFIN not ready"
        if not p.holdings():
            return False, "the SimpleFIN feed has not reported holdings for any account yet (pull once, or use csv)"
        return True, None

    def capture(self, asof: str, mode: str, run_id: str) -> dict | None:
        p = providers.current()
        if p is None or p.name != "simplefin":
            raise SourceError("ledger provider is not simplefin")
        snap = empty_snapshot(asof, mode, self.name)
        by_ledger_id = {}
        for a in settings.brokerage():
            lid = (a.get("match") or {}).get("ledger_account_id") or a.get("ledger_account_id")
            if lid:
                by_ledger_id[lid] = a
        ledger_accounts = {a.id: a for a in p.accounts(include_manual=False)}
        grouped: dict[str, list] = {}
        for h in p.holdings(date.fromisoformat(asof)):
            grouped.setdefault(h.account_id, []).append(h)
        quotes: dict[str, dict] = {}
        for lid, rows in grouped.items():
            spec = by_ledger_id.get(lid) or {}
            ledger_acct = ledger_accounts.get(lid)
            key = spec.get("key") or _slug(ledger_acct.name if ledger_acct else lid)
            positions = []
            for h in rows:
                if not h.symbol or not h.shares:
                    continue
                price = (h.market_value / h.shares) if (h.market_value is not None and h.shares) else None
                avg = (h.cost_basis / h.shares) if (h.cost_basis is not None and h.shares) else None
                positions.append(position_entry(h.symbol, h.shares, avg, price))
                quotes.setdefault(h.symbol.upper(), {"symbol": h.symbol.upper(), "last": price, "prev_close": None, "quote_time": None})
            mv = sum((p_.get("value") or 0.0) for p_ in positions)
            cash = max(0.0, (ledger_acct.balance if ledger_acct else mv) - mv)
            role = spec.get("role") or ("roth_ira" if (ledger_acct and ledger_acct.subtype == "roth_ira") else "taxable")
            snap["accounts"].append(account_entry(key, label=spec.get("label") or (ledger_acct.name if ledger_acct else key),
                                                  role=role, positions=positions, cash=cash))
        snap["quotes"] = list(quotes.values())
        finish_snapshot(snap)
        write_snapshot(snap)
        return snap
