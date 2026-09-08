"""The spending refinement rule: eligibility, fill when empty, hysteresis on two runs, the owner freeze."""
import json
from pathlib import Path

import yaml

from focos import paths, settings, spending
from focos.updates import apply as apply_mod


def _profile(home: Path, core=None, disc=None) -> None:
    sp = {"monthly_core_expenses": core, "monthly_discretionary": disc}
    (home / "config" / "profile.yml").write_text(yaml.safe_dump({"version": 2, "owner": {"name": "Ann"}, "spending": sp}))
    settings.reset()


def _cons(core90, disc90=900.0, coverage=0.92, history=80):
    return {"available": True, "spending": {"observed_monthly_core_90d": core90, "observed_monthly_discretionary_90d": disc90,
                                            "coverage_pct_90d": coverage, "history_days": history}}


def _sp(home: Path) -> dict:
    return yaml.safe_load((home / "config" / "profile.yml").read_text())["spending"]


def test_not_eligible_reasons(initialized_home: Path):
    _profile(initialized_home, 4000)
    assert spending.refine({"available": False}, "2026-09-08")["reason"] == "no ledger spending data"
    r = spending.refine(_cons(4300, coverage=0.5), "2026-09-08")
    assert not r["eligible"] and "50%" in r["reason"]
    r = spending.refine(_cons(4300, history=20), "2026-09-08")
    assert "20 days" in r["reason"]
    assert _sp(initialized_home)["monthly_core_expenses"] == 4000
    assert settings.read_json(paths.STATE / "spending_track.json")["last"]["reason"]


def test_fills_missing_figures_immediately(initialized_home: Path):
    _profile(initialized_home, None, None)
    r = spending.refine(_cons(4370.4, 912.0), "2026-09-08")
    assert r["eligible"] and len(r["applied"]) == 2
    sp = _sp(initialized_home)
    assert sp["monthly_core_expenses"] == 4400 and sp["monthly_discretionary"] == 910
    assert sp["monthly_core_source"] == "observed" and str(sp["observed_asof"]) == "2026-09-08"
    ch = [json.loads(l) for l in paths.CHANGES.read_text().splitlines()]
    assert all(c["actor"] == "system" and c["target"] == "spending" for c in ch) and "no configured figure" in ch[0]["reason"]


def test_hysteresis_needs_two_agreeing_breaches(initialized_home: Path):
    _profile(initialized_home, 4000, 800)
    r1 = spending.refine(_cons(4800, 820), "2026-09-08")  # +20%: breach, first sighting
    assert r1["applied"] == [] and r1["candidates"]["monthly_core_expenses"]["status"].startswith("breach")
    assert r1["candidates"]["monthly_discretionary"]["status"] == "within band"
    r2 = spending.refine(_cons(4150, 820), "2026-09-09")  # back within band: no change, history resets
    assert r2["applied"] == [] and r2["candidates"]["monthly_core_expenses"]["status"] == "within band"
    r3 = spending.refine(_cons(4800, 820), "2026-09-10")
    r4 = spending.refine(_cons(4750, 820), "2026-09-11")  # second consecutive breach, agrees within 10%
    assert r3["applied"] == [] and len(r4["applied"]) == 1 and "two consecutive runs" in json.loads(paths.CHANGES.read_text().splitlines()[-1])["reason"]
    assert _sp(initialized_home)["monthly_core_expenses"] == 4800 and _sp(initialized_home)["monthly_discretionary"] == 800
    # the baseline restarts from the new value: the next run alone cannot move it again
    r5 = spending.refine(_cons(5800, 820), "2026-09-12")
    assert r5["applied"] == []


def test_owner_change_freezes_refinement(initialized_home: Path):
    _profile(initialized_home, 4000)
    apply_mod.apply([{"target": "spending", "set": {"monthly_core_expenses": 4200}}], actor="user", run="cli", date="2026-08-20")
    assert _sp(initialized_home)["monthly_core_source"] == "user"
    r = spending.refine(_cons(5200), "2026-09-08")
    assert not r["eligible"] and "frozen" in r["reason"] and "2026-08-20" in r["reason"]
    r = spending.refine(_cons(5200), "2026-11-01")  # more than 60 days later: eligible again
    assert r["eligible"]
