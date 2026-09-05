"""Stage A output handling: validate, mask account numbers, normalize into the committed snapshot."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from jsonschema import Draft202012Validator

from .. import paths, settings

def schema_path() -> Path:
    return paths.AGENT / "schemas" / "snapshot.schema.json"




def validate(raw: dict) -> list[str]:
    schema = json.loads(schema_path().read_text(encoding="utf-8"))
    v = Draft202012Validator(schema)
    return [f"{'/'.join(str(p) for p in e.path)}: {e.message}" for e in sorted(v.iter_errors(raw), key=str)]


def account_key(acct: dict, accounts_cfg: dict | None = None) -> str:
    """Canonical key from accounts.yml: match.last4 first, then the sandbox-role account for an
    agentic-enabled account, else acct<last4>."""
    from ..config.compat import accounts_v2

    brokerage = accounts_v2(accounts_cfg if accounts_cfg is not None else settings.accounts()).get("brokerage", [])
    last4 = str(acct.get("account_number", ""))[-4:]
    for a in brokerage:
        if str((a.get("match") or {}).get("last4", "")) == last4:
            return a["key"]
    if acct.get("agentic_allowed"):
        for a in brokerage:
            if a.get("role") == "sandbox":
                return a["key"]
    return f"acct{last4}"


def normalize(raw: dict, date: str, mode: str, accounts_cfg: dict | None = None) -> dict:
    """Return the committed snapshot: canonical account keys, masked numbers, values from quotes."""
    quotes = {q["symbol"]: q for q in raw.get("quotes", [])}
    number_to_key: dict[str, str] = {}
    accounts = []
    for a in raw.get("accounts", []):
        key = account_key(a, accounts_cfg)
        number_to_key[str(a["account_number"])] = key
        positions = []
        for p in a.get("equity_positions", []):
            q = quotes.get(p["symbol"], {})
            price = q.get("last_trade_price")
            prev = q.get("previous_close")
            qty = float(p["quantity"])
            positions.append({
                "symbol": p["symbol"],
                "quantity": qty,
                "avg_cost": p.get("average_buy_price"),
                "price": price,
                "value": (qty * price) if price is not None else None,
                "day_change_pct": ((price / prev - 1) if (price and prev) else None),
                "sellable": p.get("shares_available_for_sells"),
            })
        positions.sort(key=lambda r: -(r["value"] or 0))
        accounts.append({
            "key": key,
            "last4": str(a["account_number"])[-4:],
            "nickname": a.get("nickname"),
            "brokerage_account_type": a.get("brokerage_account_type"),
            "type": a.get("type"),
            "agentic_allowed": bool(a.get("agentic_allowed")),
            "option_level": a.get("option_level"),
            "portfolio": a.get("portfolio", {}),
            "positions": positions,
            "option_positions": a.get("option_positions", []),
            "crypto_positions": a.get("crypto_positions", []),
            "recent_orders": a.get("recent_orders", []),
        })
    lots = []
    for lot in raw.get("tax_lots", []):
        lots.append({**{k: v for k, v in lot.items() if k != "account_number"},
                     "account": number_to_key.get(str(lot.get("account_number")), "unknown")})
    return {
        "date": date,
        "mode": mode,
        "captured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "accounts": accounts,
        "quotes": [{"symbol": s, "last": q.get("last_trade_price"), "prev_close": q.get("previous_close"),
                    "quote_time": q.get("quote_time")} for s, q in quotes.items()],
        "earnings": raw.get("earnings", []),
        "news": raw.get("news", []),
        "tax_lots": lots,
        "notes": raw.get("notes", ""),
        "total_value": float(sum((a.get("portfolio", {}).get("total_value") or 0) for a in raw.get("accounts", []))),
    }


def positions_frame(snapshot: dict) -> pd.DataFrame:
    rows = [{"account": a["key"], "symbol": p["symbol"], "quantity": p["quantity"], "avg_cost": p["avg_cost"]}
            for a in snapshot["accounts"] for p in a["positions"] if p["quantity"] > 0]
    return pd.DataFrame(rows, columns=["account", "symbol", "quantity", "avg_cost"])


def live_prices(snapshot: dict) -> dict[str, float]:
    return {q["symbol"]: float(q["last"]) for q in snapshot.get("quotes", []) if q.get("last")}


def lots_for_tax(snapshot: dict, accounts: list[str] | None = None) -> list[dict]:
    """Tax lots for the taxable accounts (default: every accounts.yml entry with role taxable)."""
    keys = set(accounts if accounts is not None else settings.accounts_by_role("taxable"))
    return [l for l in snapshot.get("tax_lots", []) if l.get("account") in keys]


def catalysts(snapshot: dict) -> dict:
    return {"date": snapshot["date"], "earnings": snapshot.get("earnings", []), "news": snapshot.get("news", [])}


def agentic_account(snapshot: dict) -> dict | None:
    for a in snapshot["accounts"]:
        if a["agentic_allowed"]:
            return a
    return None


def load(path: Path) -> dict:
    return settings.read_json(path)


def latest_two() -> tuple[dict | None, dict | None]:
    from .. import holdings

    return holdings.latest_two()
