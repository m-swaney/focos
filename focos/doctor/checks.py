"""`focos doctor` checks. Each Check says what is wrong and exactly what to do; a few have an automatic fix."""
from __future__ import annotations

import os
import shutil
import sys
from datetime import datetime, timedelta

from pydantic import BaseModel

from .. import holdings, paths, settings
from ..config import CONFIG_VERSION
from ..config.migrate import home_version
from ..config.validate import has_errors, validate_all


class Check(BaseModel):
    id: str
    ok: bool | None            # None = not applicable / unknown
    severity: str = "warn"     # info | warn | error
    title: str
    detail: str = ""
    fix: str = ""
    fix_action: str | None = None


def _age_hours(iso: str | None) -> float | None:
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.astimezone()
    return (datetime.now().astimezone() - dt).total_seconds() / 3600


def run_all() -> list[Check]:
    out: list[Check] = []
    cfg = settings.focos()
    # home + version
    writable = os.access(paths.HOME, os.W_OK)
    out.append(Check(id="home", ok=writable, severity="error", title=f"Data dir {paths.HOME}",
                     detail="writable" if writable else "not writable", fix="Check folder permissions or run focos init --home <dir>."))
    v = home_version(paths.HOME)
    out.append(Check(id="config_version", ok=v >= CONFIG_VERSION, severity="warn", title=f"Config layout v{v}",
                     detail="current" if v >= CONFIG_VERSION else f"app expects v{CONFIG_VERSION}", fix="Run `focos migrate`.",
                     fix_action=None if v >= CONFIG_VERSION else "migrate"))
    issues = validate_all()
    out.append(Check(id="config_valid", ok=not has_errors(issues), severity="error", title="Config files validate",
                     detail="; ".join(f"{i.file} {i.path}: {i.message}" for i in issues if i.severity == "error")[:400] or "ok",
                     fix="Open Setup and fix the listed fields, or edit the file under config/."))
    # secrets present
    env_ok = paths.ENV_FILE.exists()
    out.append(Check(id="env_file", ok=env_ok, severity="error", title=".env present", detail=str(paths.ENV_FILE),
                     fix="Run `focos init` to create it."))
    tracked = False
    try:
        from ..orchestrator import git_ops
        repo = git_ops.open_repo(paths.HOME)
        if repo is not None:
            tracked = b".env" in repo.open_index()
    except Exception:  # noqa: BLE001
        pass
    out.append(Check(id="env_not_tracked", ok=not tracked, severity="error", title=".env is not committed",
                     detail="tracked by git!" if tracked else "ok", fix="Run `git rm --cached .env` in the data dir and add .env to .gitignore."))
    # AI
    ai = cfg.get("ai") or {}
    from ..llm import key_status
    ok, detail = key_status(str(ai.get("provider") or "anthropic"))
    if ai.get("mode") == "agent":
        from ..agent_runtime import claude_cli
        from ..run import tokens
        found = claude_cli.find_claude((cfg.get("agent") or {}).get("claude_cli") or "auto")
        out.append(Check(id="claude_cli", ok=bool(found), severity="error", title="Claude Code CLI", detail=found or "not found",
                         fix="Install Claude Code and run `claude` once to log in, or switch ai.mode to api in Setup."))
        for a in tokens.alerts():
            out.append(Check(id=f"token_{a['code']}", ok=False, severity=a["severity"] if a["severity"] != "critical" else "error",
                             title="Claude / broker login", detail=a["text"], fix="Open a `claude` session (and `/mcp`) to renew."))
    else:
        out.append(Check(id="ai_key", ok=ok, severity="error", title=f"AI provider {ai.get('provider')}", detail=detail,
                         fix="Paste the API key in Setup > AI.", fix_action="retest_ai"))
    # ledger
    from ..ledger import providers
    p = providers.current()
    if p is None:
        out.append(Check(id="ledger", ok=None, severity="info", title="Ledger", detail="no provider configured",
                         fix="Connect SimpleFIN in Setup > Ledger to see cash, cards, and loans."))
    else:
        h = p.health()
        out.append(Check(id="ledger", ok=h.ok, severity="error" if h.ok is False else "warn", title=f"Ledger ({p.name})",
                         detail=h.reason or "ok", fix="Open Setup > Ledger and reconnect.", fix_action="refresh_ledger"))
        st = p.sync_status()
        age = _age_hours(st.last_success)
        limit = float((cfg.get("ledger") or {}).get("refresh_min_hours") or 20) * 2
        if h.ok:
            out.append(Check(id="ledger_fresh", ok=(age is not None and age <= limit), severity="warn", title="Ledger data fresh",
                             detail=f"last pull {age:.0f}h ago" if age is not None else "never pulled", fix="Run `focos ledger refresh --force`.",
                             fix_action="refresh_ledger"))
    # holdings
    src = holdings.current()
    ok_h, why = src.available()
    out.append(Check(id="holdings", ok=(ok_h if src.name != "none" else None), severity="warn", title=f"Holdings source ({src.name})",
                     detail=why or "ok", fix="Pick a holdings source in Setup > Holdings."))
    cur, _ = holdings.latest_two()
    if cur and src.name != "none":
        age = _age_hours(cur.get("captured_at"))
        out.append(Check(id="holdings_fresh", ok=(age is not None and age < 72), severity="warn", title="Holdings snapshot fresh",
                         detail=f"captured {age:.0f}h ago ({cur.get('date')})" if age is not None else "unknown", fix="Run `focos holdings capture`."))
    # runs
    from ..run import status as run_status
    st_all = run_status.get()
    daily = st_all.get("daily") or {}
    age = _age_hours(daily.get("finished"))
    out.append(Check(id="last_daily_run", ok=(daily.get("ok") is True and age is not None and age < 48) if daily else None,
                     severity="warn", title="Last daily run",
                     detail=(f"{'ok' if daily.get('ok') else 'failed: ' + str(daily.get('error') or '')[:120]} {age:.0f}h ago" if daily and age is not None else "no runs yet"),
                     fix="Run `focos run --mode daily` and read state/logs/<date>-daily-run.log.", fix_action="run_daily"))
    # scheduler + service
    from .. import scheduler
    sch = scheduler.current()
    jobs = {s.name: s for s in sch.status()}
    daily_job = jobs.get(scheduler.JOB_NAMES["daily"])
    out.append(Check(id="schedule", ok=bool(daily_job and daily_job.installed), severity="warn", title=f"Scheduled runs ({sch.platform})",
                     detail=(f"next {daily_job.next_run}" if daily_job and daily_job.installed else "not installed"),
                     fix="Run `focos schedule install` (Setup > Schedule).", fix_action="reinstall_schedule"))
    svc = jobs.get(scheduler.JOB_NAMES["service"])
    out.append(Check(id="service", ok=bool(svc and svc.installed), severity="info", title="Dashboard service at login",
                     detail="installed" if svc and svc.installed else "not installed", fix="Run `focos service install`."))
    # node / dashboard build
    from ..service.supervisor import dashboard_command, node_exe
    out.append(Check(id="node", ok=bool(node_exe()), severity="warn", title="Node runtime", detail=node_exe() or "not found",
                     fix="Re-run the installer (it downloads a private Node runtime)."))
    out.append(Check(id="dashboard_build", ok=bool(dashboard_command()), severity="warn", title="Dashboard build",
                     detail="found" if dashboard_command() else "missing", fix="Re-run the installer or `npm run build` in dashboard/."))
    # git in the data dir
    try:
        from ..orchestrator import git_ops
        gs = git_ops.status_summary(paths.HOME)
        out.append(Check(id="git", ok=gs.get("repo", False), severity="info", title="Data dir history (git)",
                         detail=f"HEAD {gs.get('head')}" if gs.get("repo") else "not a git repo", fix="Run `focos init` to initialize it."))
    except Exception as e:  # noqa: BLE001
        out.append(Check(id="git", ok=None, severity="info", title="Data dir history (git)", detail=str(e)[:100]))
    # disk
    try:
        free_gb = shutil.disk_usage(paths.HOME).free / 1e9
        out.append(Check(id="disk", ok=free_gb > 1, severity="warn", title="Disk space", detail=f"{free_gb:.1f} GB free", fix="Free up space."))
    except OSError:
        pass
    out.append(Check(id="python", ok=True, severity="info", title="Python", detail=sys.version.split()[0]))
    return out


def fix(check_id: str) -> dict:
    """Automatable fixes the Health page can trigger."""
    if check_id in ("reinstall_schedule", "schedule"):
        from .. import scheduler
        return {"ok": True, "result": [s.model_dump() for s in scheduler.current().install(scheduler.run_jobs())]}
    if check_id in ("refresh_ledger", "ledger", "ledger_fresh"):
        from datetime import date
        from ..ledger import providers
        p = providers.current()
        return {"ok": p is not None, "result": p.refresh(date.today(), force=True).model_dump() if p else None}
    if check_id in ("retest_ai", "ai_key"):
        from ..llm import LLMError, provider_for
        try:
            c = provider_for().test()
            return {"ok": True, "result": {"model": c.model, "cost_usd": c.cost_usd}}
        except LLMError as e:
            return {"ok": False, "error": str(e)}
    if check_id in ("migrate", "config_version"):
        from ..config import migrate
        return {"ok": True, "result": migrate.run(paths.HOME)}
    if check_id in ("regenerate_agent_settings",):
        from ..agent_runtime import settings_render
        return {"ok": True, "result": {k: str(v) for k, v in settings_render.render().items()}}
    return {"ok": False, "error": f"no automatic fix for {check_id}"}
