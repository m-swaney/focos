from __future__ import annotations

import os
from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel

from ... import paths, settings
from ...config import writer
from ...config.validate import has_errors, validate_all
from ...llm import key_status

router = APIRouter(prefix="/setup")

# The names focos seeds itself: config/templates/focos.example.yml, migrate_v2, and the model default.
# The Welcome step only counts as done once the household has replaced one of them with its own name.
PLACEHOLDER_LABELS = {"Our household", "Household", "My household"}


def step_status() -> dict[str, str]:
    cfg = settings.focos()
    ai_ok, _ = key_status(str((cfg.get("ai") or {}).get("provider") or "anthropic"))
    ledger = (cfg.get("ledger") or {}).get("provider")
    ledger_done = (ledger == "simplefin" and bool(os.environ.get("SIMPLEFIN_ACCESS_URL") or os.environ.get("MERCURY_TOKEN"))) \
        or ledger == "none"
    ents = settings.entities_v2().get("entities") or {}
    accounts_done = any((e.get("account_ids") for e in ents.values())) or bool(settings.brokerage()) or ledger == "none"
    holdings = (cfg.get("holdings") or {}).get("source") or "none"
    prof = settings.profile_v2()
    profile_done = bool((prof.get("owner") or {}).get("name"))
    from ... import scheduler

    sched = scheduler.current().status([scheduler.JOB_NAMES["daily"]])[0].installed
    from ...run import status as run_status

    ran = bool(run_status.get().get("daily"))
    label = str(cfg.get("home_label") or "").strip()
    welcome_done = bool(label) and label not in PLACEHOLDER_LABELS
    return {"welcome": "done" if welcome_done else "todo",
            "ai": "done" if ai_ok else "todo", "ledger": "done" if ledger_done else "todo",
            "accounts": "done" if accounts_done else "todo", "holdings": "done" if holdings != "none" else "skipped",
            "profile": "done" if profile_done else "todo", "schedule": "done" if sched else "todo",
            "first_run": "done" if ran else "todo"}


def setup_complete(cfg: dict, steps: dict[str, str]) -> bool:
    """Finished means every step is settled, however the household got there. Relying on the timestamp alone
    left the "setup is not finished" banner up forever for anyone who configured focos outside the wizard."""
    return bool(cfg.get("setup_completed_at")) or all(v in ("done", "skipped") for v in steps.values())


@router.get("/status")
def status():
    cfg = settings.focos()
    issues = validate_all()
    from ...agent_runtime import claude_cli

    steps = step_status()
    return {"home": str(paths.HOME), "app": str(paths.APP), "home_label": cfg.get("home_label"),
            "setup_completed_at": cfg.get("setup_completed_at"), "steps": steps,
            "setup_complete": setup_complete(cfg, steps),
            "config_ok": not has_errors(issues), "issues": [i.as_dict() for i in issues],
            "agent_available": bool(claude_cli.find_claude((cfg.get("agent") or {}).get("claude_cli") or "auto")),
            "ai": cfg.get("ai"), "ledger": cfg.get("ledger"), "holdings": cfg.get("holdings"), "schedule": cfg.get("schedule")}


class HomeLabel(BaseModel):
    home_label: str


@router.post("/label")
def label(body: HomeLabel):
    issues = writer.write_section("focos.yml", "home_label", body.home_label.strip()[:80] or "My household")
    if issues:
        return {"ok": False, "error": "; ".join(i.message for i in issues), "issues": [i.as_dict() for i in issues]}
    return {"ok": True, "home_label": settings.focos().get("home_label")}


@router.post("/complete")
def complete():
    writer.write_section("focos.yml", "setup_completed_at", datetime.now().astimezone().isoformat(timespec="seconds"))
    return {"ok": True, "setup_completed_at": settings.focos().get("setup_completed_at")}
