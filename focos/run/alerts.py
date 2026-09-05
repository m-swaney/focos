"""Deterministic alerts. Stage C reads these; it may add its own but never removes them."""
from __future__ import annotations

from datetime import date, datetime, timedelta


def _a(sev: str, code: str, text: str, **data) -> dict:
    return {"severity": sev, "code": code, "text": text, **({"data": data} if data else {})}


def build(snapshot: dict, portfolio: dict, profile: dict, catalysts: dict, history: list[dict],
          tax_lots: dict | None = None, sure_ok: bool | None = None, consolidated: dict | None = None) -> list[dict]:
    alerts: list[dict] = []
    risk = profile.get("risk") or {}
    max_single = float(risk.get("max_single_stock_weight_pct") or 20) / 100
    max_sector = float(risk.get("max_sector_weight_pct") or 45) / 100

    # concentration in the taxable account(s)
    from .. import settings as _settings
    taxable_keys = set(_settings.accounts_by_role("taxable"))
    sandbox_keys = set(_settings.accounts_by_role("sandbox"))
    taxable = [p for p in portfolio.get("positions", []) if p["account"] in taxable_keys]
    for p in taxable:
        if p.get("weight_account") and p["weight_account"] > max_single:
            alerts.append(_a("warn", "concentration",
                             f"{p['symbol']} is {p['weight_account']*100:.0f}% of the taxable account (limit {max_single*100:.0f}%)",
                             symbol=p["symbol"], weight=p["weight_account"]))
    top_lt = next(iter(portfolio.get("look_through", {}).items()), None)
    if top_lt and top_lt[1]["weight"] > max_single:
        alerts.append(_a("info", "look_through",
                         f"Look-through exposure to {top_lt[0]} is {top_lt[1]['weight']*100:.0f}% of everything including ETFs"))
    for sec, v in list(portfolio.get("sectors", {}).items())[:1]:
        if v["weight"] > max_sector:
            alerts.append(_a("warn", "sector", f"{sec} is {v['weight']*100:.0f}% of the combined portfolio (limit {max_sector*100:.0f}%)"))

    # drawdown from the best snapshot value we have seen
    values = [h.get("total_value") for h in history if h.get("total_value")]
    if values and snapshot.get("total_value"):
        peak = max(values + [snapshot["total_value"]])
        dd = snapshot["total_value"] / peak - 1
        if dd <= -0.10:
            alerts.append(_a("critical" if dd <= -0.20 else "warn", "drawdown",
                             f"Combined value is {dd*100:.1f}% below its peak of ${peak:,.0f}", drawdown=dd, peak=peak))

    # earnings within 7 days for held names
    today = date.fromisoformat(snapshot["date"])
    held = {p["symbol"] for p in portfolio.get("positions", [])}
    for e in catalysts.get("earnings", []):
        try:
            d = datetime.fromisoformat(str(e["date"])[:10]).date()
        except Exception:
            continue
        if e.get("symbol") in held and today <= d <= today + timedelta(days=7):
            alerts.append(_a("info", "earnings", f"{e['symbol']} reports earnings on {d.isoformat()}", symbol=e["symbol"], date=d.isoformat()))

    # sandbox funding
    for a in snapshot.get("accounts", []):
        is_sandbox = a.get("key") in sandbox_keys or (not sandbox_keys and a.get("agentic_allowed"))
        if is_sandbox and (a.get("portfolio") or {}).get("total_value", 0) == 0:
            alerts.append(_a("info", "sandbox_unfunded", "Sandbox account has no funds; sandbox stays in paper mode"))

    # tax lots crossing to long-term soon
    if tax_lots and tax_lots.get("crossing_to_lt"):
        n = len(tax_lots["crossing_to_lt"])
        gain = sum(x["gain"] for x in tax_lots["crossing_to_lt"])
        alerts.append(_a("info", "lt_crossing", f"{n} lot(s) with ${gain:,.0f} unrealized gain become long-term within 30 days"))

    # data quality
    if portfolio.get("meta", {}).get("prices_stale"):
        alerts.append(_a("warn", "prices_stale", "Yahoo Finance failed; risk stats use cached prices"))
    if snapshot.get("notes"):
        alerts.append(_a("warn", "snapshot_notes", f"Snapshot notes: {snapshot['notes'][:200]}"))
    if sure_ok is False:
        alerts.append(_a("warn", "sure_unavailable", "Sure ledger unavailable this run; entity and cash sections are stale"))
    if consolidated and consolidated.get("available"):
        if consolidated.get("unmapped_accounts"):
            names = ", ".join(str(a.get("name")) for a in consolidated["unmapped_accounts"][:5])
            alerts.append(_a("warn", "unmapped_accounts", f"Sure accounts not mapped to an entity: {names}"))
        um = ((consolidated.get("cash_flow") or {}).get("30d") or {}).get("unmatched") or []
        if um:
            alerts.append(_a("warn", "unmatched_transfers", f"{len(um)} transfer-looking transaction(s) in the last 30 days have no matching leg; review in the weekly brief"))
        cash_policy = profile.get("cash_policy") or {}
        runway = consolidated.get("personal_runway_months")
        if runway is not None and cash_policy.get("emergency_fund_months") and runway < float(cash_policy["emergency_fund_months"]):
            alerts.append(_a("warn", "emergency_fund", f"Personal cash covers {runway:.1f} months of core expenses (target {cash_policy['emergency_fund_months']})"))

    # profile completeness
    person = profile.get("owner") or profile.get("person") or {}
    missing = [k for k in ("birth_year", "federal_bracket_pct") if not person.get(k)]
    if missing:
        alerts.append(_a("info", "profile_incomplete", f"profile.yml missing: {', '.join(missing)}"))
    return alerts
