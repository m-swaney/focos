"""Refine the profile's monthly spending figures from observed, categorized ledger data.

Rule (deliberately slow): eligible only when categorization covers at least MIN_COVERAGE of 90-day expense and
there are MIN_HISTORY_DAYS of history. Frozen for FREEZE_DAYS after the owner (or a note) set a figure. A missing
figure is filled immediately; an existing one changes only when the observed value breaches BAND on two consecutive
eligible runs whose candidates agree within AGREE. Changes go through updates.apply as actor=system, so they land
in the changes log, the dashboard, and the next brief's "What I updated".
"""
from __future__ import annotations

from datetime import date as _date
from datetime import timedelta

from . import paths, settings
from .updates import apply as apply_mod

MIN_COVERAGE = 0.85
MIN_HISTORY_DAYS = 60
FREEZE_DAYS = 60
BAND = 0.15
AGREE = 0.10
FIELDS = (("monthly_core_expenses", "observed_monthly_core_90d"), ("monthly_discretionary", "observed_monthly_discretionary_90d"))
TRACK_NAME = "spending_track.json"


def _track_path():
    return paths.STATE / TRACK_NAME


def _round(v: float) -> float:
    return float(round(v, -2)) if v >= 1000 else float(round(v, -1))


def _owner_set_recently(days: int, today: _date) -> str | None:
    cutoff = (today - timedelta(days=days)).isoformat()
    for r in reversed(apply_mod.all_changes()):
        if r.get("target") == "spending" and r.get("ok") and r.get("actor") in ("user", "model") and str(r.get("date") or "") >= cutoff:
            return str(r.get("date"))
    return None


def refine(consolidated: dict | None, asof: str) -> dict:
    today = _date.fromisoformat(asof)
    sp = ((consolidated or {}).get("spending") or {}) if (consolidated or {}).get("available") else {}
    track = settings.read_json(_track_path(), {}) or {}
    result: dict = {"date": asof, "eligible": False, "reason": None, "applied": [], "candidates": {}}
    coverage, history = sp.get("coverage_pct_90d"), sp.get("history_days")
    if not sp:
        result["reason"] = "no ledger spending data"
    elif coverage is None or coverage < MIN_COVERAGE:
        result["reason"] = f"only {round((coverage or 0) * 100)}% of 90-day spending is categorized (need {round(MIN_COVERAGE * 100)}%)"
    elif (history or 0) < MIN_HISTORY_DAYS:
        result["reason"] = f"{history or 0} days of history (need {MIN_HISTORY_DAYS})"
    elif not sp.get("observed_monthly_core_90d"):
        result["reason"] = "no observed core spending"
    else:
        result["eligible"] = True
    if result["eligible"]:
        when = _owner_set_recently(FREEZE_DAYS, today)
        if when:
            result["eligible"] = False
            result["reason"] = f"frozen: the owner set a spending figure on {when}"
    if not result["eligible"]:
        track["last"] = result
        settings.write_json(_track_path(), track)
        return result

    prof_sp = settings.profile_v2().get("spending") or {}
    cands = track.setdefault("candidates", {})
    updates: list[dict] = []
    for field, obs_key in FIELDS:
        obs = sp.get(obs_key)
        if obs is None or obs <= 0:
            continue
        cand = _round(float(obs))
        hist = [c for c in (cands.get(field) or []) if c.get("date") != asof]
        hist.append({"date": asof, "value": cand})
        cands[field] = hist[-3:]
        cfg = prof_sp.get(field)
        if cfg in (None, 0):
            updates.append({"field": field, "value": cand, "reason": f"no configured figure; observed 90-day {field.replace('_', ' ')} "
                                                                     f"with {round(coverage * 100)}% categorized"})
            continue
        cfg = float(cfg)
        breach = abs(obs - cfg) / cfg > BAND
        prev = hist[-2] if len(hist) >= 2 else None
        if not breach:
            result["candidates"][field] = {"observed": round(obs, 2), "configured": cfg, "status": "within band"}
        elif prev and abs(prev["value"] - cfg) / cfg > BAND and abs(prev["value"] - cand) <= AGREE * max(cand, 1.0):
            updates.append({"field": field, "value": cand, "reason": f"observed 90-day {field.replace('_', ' ')} {round(obs)} vs configured "
                                                                     f"{round(cfg)} on two consecutive runs ({prev['date']}, {asof}); "
                                                                     f"{round(coverage * 100)}% categorized"})
        else:
            result["candidates"][field] = {"observed": round(obs, 2), "configured": cfg, "status": "breach; waiting for a second run to agree"}
    if updates:
        recs = apply_mod.apply([{"target": "spending", "set": {u["field"]: u["value"]}, "reason": u["reason"]} for u in updates],
                               actor="system", run=f"pipeline-{asof}", date=asof)
        result["applied"] = [apply_mod.describe(r) for r in recs]
        for u in updates:  # a fresh baseline: the hysteresis history restarts from the value just written
            cands[u["field"]] = [{"date": asof, "value": u["value"]}]
        settings.reset()
    track["last"] = result
    settings.write_json(_track_path(), track)
    return result
