"""Keep an open dashboard alive between daily runs.

Stage A captures the broker's quotes once, and the pipeline hands those frozen quotes to the analytics, so
re-running it changes nothing. This module re-prices the same snapshot from free delayed quotes every few
minutes, and pulls the bank feed once at midday.

Three rules it never breaks: the authoritative snapshot and the dated derived folders are left exactly as the
daily run wrote them, the sandbox warmup counter is never bumped, and everything it produces lands in
`state/cache/intraday.json`, which git ignores, so the data dir stays clean between runs.
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime, time as _time
from pathlib import Path

from . import holdings, paths, settings

log = logging.getLogger("focos.intraday")

CACHE_NAME = "intraday.json"
DELAYED_MINUTES = 15
MOVERS = 8
DEFAULTS = {"enabled": True, "every_minutes": 15, "market_open": "09:30", "market_close": "16:00",
            "weekdays_only": True, "midday_ledger": "12:00"}


def cache_path() -> Path:
    return paths.CACHE / CACHE_NAME


def read() -> dict | None:
    """The last intraday result, or None. Never raises: a missing or corrupt file just means "no data yet"."""
    got = settings.read_json(cache_path(), None)
    return got if isinstance(got, dict) else None


def config(cfg: dict | None = None) -> dict:
    got = cfg if cfg is not None else (settings.focos().get("intraday") or {})
    return {**DEFAULTS, **{k: v for k, v in got.items() if v is not None or k == "midday_ledger"}}


def enabled(cfg: dict | None = None) -> bool:
    return bool(config(cfg).get("enabled", True))


def now_local() -> datetime:
    return datetime.now(settings.tz())


def _hhmm(value, fallback: str) -> _time:
    try:
        h, m = str(value or fallback).split(":")
        return _time(int(h), int(m))
    except (TypeError, ValueError):
        h, m = fallback.split(":")
        return _time(int(h), int(m))


def market_open_now(now: datetime, cfg: dict | None = None) -> bool:
    """Inside the configured window, in the household's own timezone. Holidays are not modelled: the quotes
    simply do not move, which costs one cheap request and shows the truth."""
    c = config(cfg)
    if c.get("weekdays_only", True) and now.weekday() >= 5:
        return False
    return _hhmm(c.get("market_open"), "09:30") <= now.time() <= _hhmm(c.get("market_close"), "16:00")


def price_due(now: datetime, cfg: dict | None = None, last_at: datetime | None = None) -> bool:
    """First tick after startup always runs, so an evening or weekend page is populated rather than empty."""
    c = config(cfg)
    if not enabled(c):
        return False
    if last_at is None:
        return True
    if not market_open_now(now, c):
        return False
    return (now - last_at).total_seconds() >= float(c.get("every_minutes") or 15) * 60


def midday_due(now: datetime, cfg: dict | None = None, done_for: str | None = None) -> bool:
    c = config(cfg)
    at = c.get("midday_ledger")
    if not enabled(c) or not at:
        return False
    if c.get("weekdays_only", True) and now.weekday() >= 5:
        return False
    if done_for == now.date().isoformat():
        return False
    return now.time() >= _hhmm(at, "12:00")


# ---------------------------------------------------------------- the price refresh

def _positions(snapshot: dict) -> list[tuple[dict, dict]]:
    return [(a, p) for a in snapshot.get("accounts") or [] for p in a.get("positions") or []
            if (p.get("quantity") or 0) > 0 and p.get("symbol")]


def _equity(account: dict) -> float:
    return sum(float(p.get("value") or 0) for p in account.get("positions") or [])


def refresh(now: datetime | None = None, quotes: dict | None = None) -> dict:
    """Re-price the latest snapshot from delayed quotes and publish state/cache/intraday.json."""
    from .analytics import prices

    now = now or now_local()
    snapshot, _ = holdings.latest_two()
    if not snapshot or not snapshot.get("accounts"):
        return _write({"available": False, "asof": now.isoformat(timespec="seconds"),
                       "reason": "no holdings snapshot yet"})
    rows = _positions(snapshot)
    if not rows:
        return _write({"available": False, "asof": now.isoformat(timespec="seconds"),
                       "reason": "the latest snapshot holds no positions"})

    symbols = sorted({str(p["symbol"]).upper() for _, p in rows})
    if quotes is None:
        quotes, stale = prices.fetch_quotes(symbols)
    else:
        stale = False
    big_move = float((settings.analytics() or {}).get("big_move_pct") or 5.0) / 100.0

    priced: list[dict] = []
    skipped: list[str] = []
    by_account: dict[str, dict] = {}
    day_change = 0.0
    day_base = 0.0
    for account, position in rows:
        key = account.get("key") or "unknown"
        symbol = str(position["symbol"]).upper()
        qty = float(position.get("quantity") or 0)
        snap_value = float(position.get("value") or 0)
        q = quotes.get(symbol) or {}
        price = q.get("last")
        acct = by_account.setdefault(key, {"key": key, "equity_value": 0.0, "snapshot_equity": _equity(account),
                                           "broker_total": float((account.get("portfolio") or {}).get("total_value") or 0.0)})
        if not price:
            skipped.append(symbol)
            acct["equity_value"] += snap_value
            continue
        price = float(price)
        value = qty * price
        prev = q.get("prev_close")
        change_pct = (price / float(prev) - 1) if prev else None
        acct["equity_value"] += value
        if prev:
            day_change += (price - float(prev)) * qty
            day_base += float(prev) * qty
        priced.append({"symbol": symbol, "account": key, "quantity": qty, "price": price, "value": value,
                       "day_change_pct": change_pct, "value_change": value - snap_value})

    accounts = []
    for a in by_account.values():
        delta = a["equity_value"] - a["snapshot_equity"]
        accounts.append({"key": a["key"], "equity_value": round(a["equity_value"], 2),
                         "total_value": round(a["broker_total"] + delta, 2), "change_since_snapshot": round(delta, 2)})
    change = sum(a["change_since_snapshot"] for a in accounts)
    movers = sorted([p for p in priced if p["day_change_pct"] is not None],
                    key=lambda p: -abs(p["day_change_pct"]))[:MOVERS]
    for m in movers:
        m["big"] = abs(m["day_change_pct"]) >= big_move

    return _write({
        "available": True,
        "asof": now.isoformat(timespec="seconds"),
        "source": "yahoo",
        "stale": bool(stale),
        "delayed_minutes": DELAYED_MINUTES,
        "snapshot_date": snapshot.get("date"),
        "snapshot_captured_at": snapshot.get("captured_at"),
        "snapshot_total_value": snapshot.get("total_value"),
        "total_value": round(float(snapshot.get("total_value") or 0) + change, 2),
        "change_since_snapshot": round(change, 2),
        "day_change": round(day_change, 2),
        "day_change_pct": (day_change / day_base) if day_base else None,
        "big_move_pct": big_move,
        "accounts": accounts,
        "movers": movers,
        "positions": sorted(priced, key=lambda p: -p["value"]),
        "symbols": len(symbols),
        "priced": len(priced),
        "skipped": sorted(set(skipped)),
    })


# ---------------------------------------------------------------- the midday bank pull

def run_midday(now: datetime | None = None) -> dict:
    """One forced ledger pull a day, then rebuild the derived JSON from the existing snapshot.

    Forced because `refresh_min_hours` is 20 and the previous run was about 19 hours earlier, so an unforced
    midday pull would always be gated out. `mode="daily"` matters twice over: it keeps the heavy analytics off
    and keeps the monthly Zillow refresh off.
    """
    from . import pipeline
    from .ledger import providers

    now = now or now_local()
    date = now.date().isoformat()
    out: dict = {"date": date, "ok": False, "pull": None, "error": None,
                 "ts": now.isoformat(timespec="seconds")}
    provider = providers.current()
    if provider is None:
        out["error"] = "no ledger provider configured"
        _write({}, midday=out)  # recorded for the day either way, so a restart does not retry every tick
        return out
    try:
        res = provider.refresh(now.date(), force=True)
        out["pull"] = {k: getattr(res, k, None) for k in ("ok", "skipped", "accounts", "transactions_new", "transactions_updated")}
        pipeline.run("daily", heavy=False, bump=False)
        out["ok"] = True
    except Exception as e:  # noqa: BLE001  (a bank hiccup must not stop the service)
        out["error"] = f"{type(e).__name__}: {str(e)[:200]}"
        log.warning("midday ledger pull failed: %s", out["error"])
    _write({}, midday=out)
    return out


def _write(payload: dict, midday: dict | None = None) -> dict:
    """Publish, keeping whichever half of the file this call did not produce."""
    prev = read() or {}
    merged = {**prev, **payload}
    merged["midday"] = midday if midday is not None else prev.get("midday")
    try:
        settings.write_json(cache_path(), merged)
    except OSError as e:
        log.warning("could not write %s: %s", cache_path(), e)
    return merged


# ---------------------------------------------------------------- the supervisor's timer

class Ticker:
    """Drives the two jobs from the service's existing two-second loop. Each runs on a daemon thread, so a slow
    fetch never stalls child-process monitoring, and no failure ever reaches the loop."""

    def __init__(self, cfg: dict | None = None):
        self.cfg = config(cfg)
        self.last_price_at: datetime | None = None
        self._busy = False

    def enabled(self) -> bool:
        return enabled(self.cfg)

    def due(self, now: datetime) -> str | None:
        if self._busy:
            return None
        if midday_due(now, self.cfg, ((read() or {}).get("midday") or {}).get("date")):
            return "midday"
        if price_due(now, self.cfg, self.last_price_at):
            return "prices"
        return None

    def tick(self, now: datetime | None = None) -> str | None:
        now = now or now_local()
        job = self.due(now)
        if job is None:
            return None
        self.last_price_at = now
        self._busy = True
        threading.Thread(target=self._run, args=(job,), name=f"focos-intraday-{job}", daemon=True).start()
        return job

    def _run(self, job: str) -> None:
        try:
            if job == "midday":
                log.info("intraday: midday ledger pull")
                run_midday()
                refresh()
            else:
                out = refresh()
                if out.get("available"):
                    log.info("intraday: %s priced, total %.2f (%s)", out.get("priced"), out.get("total_value") or 0,
                             "stale quotes" if out.get("stale") else "fresh")
        except Exception as e:  # noqa: BLE001
            log.warning("intraday %s failed: %s: %s", job, type(e).__name__, str(e)[:200])
        finally:
            self._busy = False
