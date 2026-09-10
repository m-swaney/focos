"""focos command line. Run with `.venv\\Scripts\\python -m focos <command>`."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import date as _date
from pathlib import Path

import typer

from . import paths, settings

app = typer.Typer(no_args_is_help=True, add_completion=False)


@app.callback()
def _root(home: str = typer.Option(None, "--home", help="household data dir (overrides FOCOS_HOME)")) -> None:
    if home:
        os.environ["FOCOS_HOME"] = str(paths.rebind(home))
        settings.load_env()
        settings.reset()


from .config.cli import config_app, init as _init, migrate as _migrate  # noqa: E402

app.command("init")(_init)
app.command("migrate")(_migrate)
app.add_typer(config_app, name="config")
from .ledger.cli import ledger_app  # noqa: E402

app.add_typer(ledger_app, name="ledger")
status_app = typer.Typer(no_args_is_help=True)
sandbox_app = typer.Typer(no_args_is_help=True)
app.add_typer(status_app, name="status")
app.add_typer(sandbox_app, name="sandbox")


def _echo(obj) -> None:
    typer.echo(json.dumps(obj, indent=2, default=str))


@app.command()
def analyze(from_csv: Path = typer.Option(paths.ROOT / "data" / "positions.csv", help="legacy positions CSV"),
            years: int = 3, out: Path = typer.Option(paths.REPORTS / "summary.md")) -> None:
    """Legacy one-shot analysis from a CSV (same output as the original analyze.py)."""
    import pandas as pd

    from .analytics import report_md
    from .analytics import run as analytics_run

    pos = pd.read_csv(from_csv)
    pos["symbol"] = pos["symbol"].str.upper()
    cfg = dict(settings.analytics())
    cfg["years"] = years
    res = analytics_run.compute(pos, cfg, mode="weekly", tearsheet_dir=paths.REPORTS, heavy=True)
    out.write_text(report_md.render(res), encoding="utf-8")
    typer.echo(report_md.render(res))
    typer.echo(f"Wrote {out}")


@app.command("ingest-claude")
def ingest_claude(stage: str = typer.Option(..., help="A or C"), file: Path = typer.Option(...),
                  mode: str = "daily", date: str = typer.Option(None)) -> None:
    """Parse a `claude -p --output-format json` output file for Stage A (snapshot) or Stage C (brief)."""
    from .run import claude_io, status
    from .sources import robinhood_snapshot as rh

    date = date or _date.today().isoformat()
    paths.ensure_dirs()
    try:
        result = claude_io.read_result(file)
    except Exception as e:
        status.stage(mode, stage, False, f"unreadable claude output: {e}")
        raise typer.Exit(2)
    meta = claude_io.summarize(result)
    if meta["is_error"]:
        err = str(result.get("result") or result.get("error") or meta.get("subtype") or "claude reported is_error")
        status.stage(mode, stage, False, err[:500], extra=meta)
        typer.echo(f"Stage {stage} error: {err[:500]}", err=True)
        raise typer.Exit(2)
    text = result.get("result") or ""
    try:
        payload = claude_io.extract_json(text)
    except Exception as e:
        status.stage(mode, stage, False, f"no JSON in result: {e}", extra=meta)
        (paths.LOGS / f"{date}-{mode}-{stage}-result.txt").write_text(text, encoding="utf-8")
        raise typer.Exit(2)

    if stage.upper() == "A":
        errors = rh.validate(payload)
        if errors:
            status.stage(mode, "A", False, "schema: " + "; ".join(errors[:5]), extra=meta)
            typer.echo("\n".join(errors), err=True)
            raise typer.Exit(2)
        raw_path = paths.RAW / f"{date}-{mode}.json"
        settings.write_json(raw_path, payload)
        snap = rh.normalize(payload, date, mode)
        snap["source"] = "robinhood_mcp"
        from . import holdings
        snap_path = holdings.write_snapshot(snap)
        status.stage(mode, "A", True, extra={**meta, "accounts": len(snap["accounts"]), "total_value": snap["total_value"]})
        _echo({"snapshot": str(snap_path), "accounts": len(snap["accounts"]), "total_value": snap["total_value"]})
    else:
        settings.write_json(paths.LATEST / "brief_result.json", {**payload, "_meta": meta, "date": date, "mode": mode})
        status.stage(mode, "C", True, extra=meta)
        _echo({"summary_line": payload.get("summary_line"), "report_path": payload.get("report_path"),
               "alerts": len(payload.get("alerts", []))})


@app.command()
def pipeline(mode: str = "daily", date: str = typer.Option(None), heavy: bool = typer.Option(None),
             bump: bool = typer.Option(True, help="count this run toward the sandbox warmup")) -> None:
    """Stage B: analytics, diff, alerts, sandbox summary -> state/derived/latest."""
    from . import pipeline as pl
    from .run import status

    try:
        out = pl.run(mode, date, heavy, bump=bump)
    except Exception as e:
        status.stage(mode, "B", False, str(e)[:500])
        raise
    status.stage(mode, "B", True, extra=out)
    _echo(out)


from .brief.prompts import render_placeholders  # noqa: E402,F401  (re-exported for callers and tests)


@app.command("prompt")
def render_prompt(mode: str = typer.Option("daily", help="snapshot | daily | weekly | monthly (which template)"),
                  run_mode: str = typer.Option(None, help="daily | weekly | monthly (the run; defaults to --mode)"),
                  date: str = typer.Option(None), run_id: str = "manual") -> None:
    """Print the Stage A or Stage C prompt with placeholders filled (used by run_agent.ps1 and the run command)."""
    from .brief import prompts

    date = date or _date.today().isoformat()
    sys.stdout.write(prompts.render(mode, date, run_id, run_mode=run_mode))


@app.command("run")
def run_cycle(mode: str = typer.Option("daily", help="daily | weekly | monthly"), date: str = typer.Option(None),
              skip_a: bool = typer.Option(False, "--skip-a", help="reuse the latest holdings snapshot"),
              skip_b: bool = typer.Option(False, "--skip-b"), skip_c: bool = typer.Option(False, "--skip-c"),
              no_git: bool = typer.Option(False, "--no-git"), heavy: bool = typer.Option(None),
              dry_run: bool = typer.Option(False, "--dry-run", help="print what would run and exit")) -> None:
    """One full cycle: holdings snapshot, pipeline, brief, backup, commit (replaces scripts/run_agent.ps1)."""
    from .orchestrator import run as orch

    if mode not in ("daily", "weekly", "monthly"):
        raise typer.BadParameter("mode must be daily, weekly, or monthly")
    opts = orch.RunOptions(mode=mode, date=date, skip_a=skip_a, skip_b=skip_b, skip_c=skip_c, no_git=no_git,
                           heavy=heavy, dry_run=dry_run)
    if dry_run:
        _echo(orch.describe(opts))
        return
    res = orch.run(opts)
    _echo({"run_id": res.run_id, "ok": res.ok, "stages": res.stages, "commit": res.commit, "log": res.log_file})
    if not res.ok:
        raise typer.Exit(1)


@app.command()
def intraday(midday: bool = typer.Option(False, "--midday", help="also do the once-a-day bank pull and rebuild")) -> None:
    """Re-price the latest holdings snapshot from delayed quotes so an open dashboard shows current numbers.

    The dashboard service does this on a timer; this runs it once by hand. It never rewrites the snapshot or the
    dated history, and never bumps the sandbox warmup."""
    from . import intraday as intraday_mod

    if midday:
        _echo(intraday_mod.run_midday())
    out = intraday_mod.refresh()
    _echo({k: out.get(k) for k in ("available", "reason", "asof", "stale", "total_value", "change_since_snapshot",
                                   "day_change", "priced", "skipped")})
    if not out.get("available"):
        raise typer.Exit(1)


ai_app = typer.Typer(no_args_is_help=True, help="AI provider (api mode): test the key, list defaults, estimate context size.")
app.add_typer(ai_app, name="ai")


@ai_app.command("test")
def ai_test(provider: str = typer.Option(None, help="override focos.yml ai.provider"), model: str = typer.Option(None)) -> None:
    """Make one tiny call with the configured provider and report latency."""
    import time

    from .llm import LLMError, key_status, provider_for

    ai = dict(settings.focos().get("ai") or {})
    if provider:
        ai["provider"] = provider
    if model:
        ai["model"] = model
    ok, detail = key_status(ai.get("provider") or "anthropic")
    if not ok:
        _echo({"ok": False, "provider": ai.get("provider"), "error": detail})
        raise typer.Exit(2)
    p = provider_for(ai)
    t0 = time.time()
    try:
        c = p.test()
    except LLMError as e:
        _echo({"ok": False, "provider": p.name, "model": p.model, "error": str(e)})
        raise typer.Exit(2)
    _echo({"ok": True, "provider": p.name, "model": c.model or p.model, "latency_ms": int((time.time() - t0) * 1000),
           "reply": c.text.strip()[:40], "usage": c.usage.model_dump()})


@ai_app.command("models")
def ai_models() -> None:
    """Default model per provider."""
    from .llm import DEFAULT_MODELS

    _echo({"defaults": DEFAULT_MODELS})


@ai_app.command("estimate")
def ai_estimate(mode: str = "daily", date: str = typer.Option(None)) -> None:
    """Estimate the context size of an api-mode brief from the current derived data (no API call)."""
    from .brief import context
    from .llm import provider_for

    date = date or _date.today().isoformat()
    ai = settings.focos().get("ai") or {}
    bundle = context.fit(context.build(mode, date), int(ai.get("max_input_tokens") or 60000))
    p = provider_for(ai, heavy=(mode != "daily"))
    est_in, est_out = bundle.tokens() + 2500, 3000
    _echo({"provider": p.name, "model": p.model, "sections": [s.name for s in bundle.sections], "dropped": bundle.dropped,
           "input_tokens_est": est_in, "output_tokens_est": est_out})


schedule_app = typer.Typer(no_args_is_help=True, help="Scheduled runs (Task Scheduler on Windows, launchd on macOS).")
app.add_typer(schedule_app, name="schedule")
service_app = typer.Typer(no_args_is_help=True, help="The always-on dashboard/API process.")
app.add_typer(service_app, name="service")


@schedule_app.command("install")
def schedule_install() -> None:
    """Register the daily, weekly, and monthly runs from config/focos.yml schedule (re-run to update)."""
    from . import scheduler

    _echo([s.model_dump() for s in scheduler.current().install(scheduler.run_jobs())])


@schedule_app.command("uninstall")
def schedule_uninstall() -> None:
    from . import scheduler

    _echo({"removed": scheduler.current().uninstall([scheduler.JOB_NAMES[k] for k in ("daily", "weekly", "monthly")])})


@schedule_app.command("status")
def schedule_status() -> None:
    from . import scheduler

    _echo([s.model_dump() for s in scheduler.current().status()])


@schedule_app.command("show")
def schedule_show() -> None:
    """Print the job definitions (and the rendered task XML / plist) without installing anything."""
    import sys as _sys

    from . import scheduler

    jobs = scheduler.run_jobs() + [scheduler.service_job()]
    out = []
    for j in jobs:
        d = j.model_dump()
        if _sys.platform == "win32":
            from .scheduler.windows import task_xml
            d["rendered"] = task_xml(j)
        elif _sys.platform == "darwin":
            from .scheduler.launchd import plist_text
            d["rendered"] = plist_text(j, str(paths.HOME))
        out.append(d)
    _echo(out)


@service_app.command("install")
def service_install(start: bool = typer.Option(True, help="start it now")) -> None:
    """Register the at-login dashboard/API service and (by default) start it."""
    from . import scheduler

    sch = scheduler.current()
    res = sch.install([scheduler.service_job()])
    if start and res and res[0].installed:
        sch.start(scheduler.JOB_NAMES["service"])
    _echo([s.model_dump() for s in res])


@service_app.command("uninstall")
def service_uninstall() -> None:
    from . import scheduler
    from .service.supervisor import reap_orphans

    sch = scheduler.current()
    sch.stop(scheduler.JOB_NAMES["service"])
    reap_orphans()
    _echo({"removed": sch.uninstall([scheduler.JOB_NAMES["service"]])})


@service_app.command("start")
def service_start() -> None:
    from . import scheduler

    _echo({"started": scheduler.current().start(scheduler.JOB_NAMES["service"])})


@service_app.command("stop")
def service_stop() -> None:
    """Ending the scheduled task kills the supervisor but not the dashboard it spawned, so reap that too;
    otherwise the port stays held and the next `serve` cannot bind."""
    from . import scheduler
    from .service.supervisor import reap_orphans

    stopped = scheduler.current().stop(scheduler.JOB_NAMES["service"])
    _echo({"stopped": stopped, "reaped": reap_orphans()})


@service_app.command("status")
def service_status() -> None:
    from . import scheduler
    from .service.supervisor import dashboard_command, node_exe

    st = scheduler.current().status([scheduler.JOB_NAMES["service"]])[0].model_dump()
    cmd = dashboard_command()
    st["dashboard_command"] = cmd[0] if cmd else None
    st["node"] = node_exe()
    _echo(st)


@app.command("serve")
def serve(with_dashboard: bool = typer.Option(True, "--with-dashboard/--no-dashboard"),
          with_api: bool = typer.Option(True, "--with-api/--no-api"),
          once: bool = typer.Option(False, "--once", help="start, wait a second, stop (smoke test)")) -> None:
    """Run the dashboard (and local API) in the foreground with restarts; the service job runs this."""
    import logging

    from .service.supervisor import serve as _serve

    logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(message)s", datefmt="%H:%M:%S")
    raise typer.Exit(_serve(with_dashboard=with_dashboard, with_api=with_api, once=once))


@app.command("update")
def update_cmd(check: bool = typer.Option(False, "--check", help="only report whether a newer release exists"),
               force: bool = typer.Option(False, "--force", help="reinstall even if not newer"),
               repo: str = typer.Option(None, help="GitHub repo (owner/name)")) -> None:
    """Fetch and install the newest release next to this one, migrate the data dir, and re-point the service."""
    from . import updater

    r = repo or updater.DEFAULT_REPO
    if check:
        _echo(updater.check(r))
        return
    try:
        _echo(updater.update(r, log=lambda m: typer.echo(f"[update] {m}"), force=force))
    except Exception as e:  # noqa: BLE001
        typer.echo(f"update failed: {e}", err=True)
        raise typer.Exit(1)


@app.command("version")
def version_cmd() -> None:
    from . import updater

    _echo({"version": updater.installed_version(), "app": str(paths.APP), "home": str(paths.HOME), "dev_checkout": updater.is_dev_checkout()})


holdings_app = typer.Typer(no_args_is_help=True, help="Brokerage holdings snapshots.")
app.add_typer(holdings_app, name="holdings")


@holdings_app.command("capture")
def holdings_capture(date: str = typer.Option(None), mode: str = "manual",
                     source: str = typer.Option(None, help="override focos.yml holdings.source")) -> None:
    """Capture a holdings snapshot now with the configured (or given) source."""
    from . import holdings

    date = date or _date.today().isoformat()
    src = holdings.current(source)
    ok, why = src.available()
    if not ok:
        typer.echo(f"{src.name}: {why}", err=True)
        raise typer.Exit(2)
    snap = src.capture(date, mode, "manual")
    _echo({"source": src.name, "date": date, "accounts": [a["key"] for a in (snap or {}).get("accounts", [])],
           "total_value": (snap or {}).get("total_value"), "notes": (snap or {}).get("notes")})


@holdings_app.command("show")
def holdings_show() -> None:
    """Summarize the latest snapshot (no full account numbers are ever stored here)."""
    from . import holdings

    cur, prev = holdings.latest_two()
    if not cur:
        _echo({"available": False})
        return
    _echo({"date": cur.get("date"), "source": cur.get("source"), "total_value": cur.get("total_value"),
           "previous_date": (prev or {}).get("date"),
           "accounts": [{"key": a["key"], "role": a.get("brokerage_account_type"), "last4": a.get("last4"),
                         "positions": len(a.get("positions", [])),
                         "total_value": (a.get("portfolio") or {}).get("total_value")} for a in cur.get("accounts", [])]})


@holdings_app.command("keepalive")
def holdings_keepalive(date: str = typer.Option(None)) -> None:
    """Refresh the Robinhood login with one cheap read call (installed as a daily job so the token never lapses)."""
    from .holdings import keepalive

    rec = keepalive.run(date)
    _echo({k: rec.get(k) for k in ("date", "ok", "auth_error", "refreshed", "duration_ms", "error")}
          | {"expires_at": (rec.get("token_after") or {}).get("expires_at")})
    if not rec["ok"]:
        raise typer.Exit(1)


auth_app = typer.Typer(no_args_is_help=True, help="Broker and agent logins.")
app.add_typer(auth_app, name="auth")


@auth_app.command("robinhood")
def auth_robinhood(no_browser: bool = typer.Option(False, "--no-browser", help="print the authorization URL instead of opening a browser")) -> None:
    """Connect Robinhood: register its MCP server with Claude Code and run the login flow in this terminal."""
    from .holdings import auth

    raise typer.Exit(auth.robinhood(no_browser=no_browser, echo=typer.echo))


note_app = typer.Typer(invoke_without_command=True, help="Leave a note for your chief of staff; the next run reads it.")
app.add_typer(note_app, name="note")


def _parse_about(about: str | None) -> dict | None:
    if not about:
        return None
    kind, _, ident = about.partition(":")
    kind = {"tax": "tax_agenda"}.get(kind, kind)
    return {"type": kind, **({"id": ident} if ident else {})}


@note_app.callback()
def note_main(ctx: typer.Context, text: list[str] = typer.Argument(None),
              about: str = typer.Option(None, help="what it concerns: goal:<id>, tax:<id>, decision:<id>, question")) -> None:
    """`focos note "the withholding is fixed"`: saved now, read by the next brief run."""
    if ctx.invoked_subcommand:
        return
    if not text:
        typer.echo(ctx.get_help())
        raise typer.Exit(0)
    from . import inbox

    _echo(inbox.add(" ".join(text), about=_parse_about(about), source="cli"))


@note_app.command("add")
def note_add(text: list[str] = typer.Argument(...), about: str = typer.Option(None)) -> None:
    """Same as `focos note "<text>"`."""
    from . import inbox

    _echo(inbox.add(" ".join(text), about=_parse_about(about), source="cli"))


@note_app.command("list")
def note_list(n: int = 20) -> None:
    """Recent notes and their status (pending, consumed, applied, answered, dismissed)."""
    from . import inbox

    _echo({"pending": len(inbox.pending()), "unaddressed": [r["id"] for r in inbox.unaddressed()], "notes": inbox.recent(n)})


@note_app.command("dismiss")
def note_dismiss(note_id: str) -> None:
    from . import inbox

    note = inbox.dismiss(note_id)
    if note is None:
        typer.echo(f"no note {note_id}", err=True)
        raise typer.Exit(1)
    _echo(note)


done_app = typer.Typer(no_args_is_help=True, help="Mark a goal, tax-agenda item, or decision as done.")
app.add_typer(done_app, name="done")


def _apply_user(updates: list[dict]) -> None:
    from .updates import apply as apply_mod

    changes = apply_mod.apply(updates, actor="user", run="cli", date=_date.today().isoformat())
    _echo([{"ok": c["ok"], "summary": apply_mod.describe(c)} for c in changes])
    if not all(c["ok"] for c in changes):
        raise typer.Exit(1)


@done_app.command("goal")
def done_goal(goal_id: str, on: str = typer.Option(None, help="completion date YYYY-MM-DD"), pause: bool = typer.Option(False, "--pause")) -> None:
    st = {"status": "paused"} if pause else {"status": "done", **({"completed_on": on} if on else {})}
    _apply_user([{"target": "goal", "id": goal_id, "set": st, "reason": "focos done goal"}])


@done_app.command("tax")
def done_tax(item_id: str, drop: bool = typer.Option(False, "--drop", help="drop instead of done"), note: str = typer.Option(None)) -> None:
    st = {"status": "dropped" if drop else "done", **({"notes": note} if note else {})}
    _apply_user([{"target": "tax_agenda", "id": item_id, "set": st, "reason": "focos done tax"}])


@done_app.command("decision")
def done_decision(decision_id: str, status: str = typer.Option("acted", help="acted | retired | standing"), note: str = typer.Option("")) -> None:
    _apply_user([{"target": "decision", "id": decision_id, "set": {"status": status, "note": note}, "reason": "focos done decision"}])


reopen_app = typer.Typer(no_args_is_help=True, help="Reopen a goal or tax-agenda item.")
app.add_typer(reopen_app, name="reopen")


@reopen_app.command("goal")
def reopen_goal(goal_id: str) -> None:
    _apply_user([{"target": "goal", "id": goal_id, "set": {"status": "active"}, "reason": "focos reopen goal"}])


@reopen_app.command("tax")
def reopen_tax(item_id: str) -> None:
    _apply_user([{"target": "tax_agenda", "id": item_id, "set": {"status": "open"}, "reason": "focos reopen tax"}])


@app.command()
def changes(n: int = 20, days: int = typer.Option(None)) -> None:
    """What changed in goals, the tax agenda, profile notes, spending, and decisions, and who changed it."""
    from .updates import apply as apply_mod

    _echo([{k: c.get(k) for k in ("ts", "actor", "run", "ok", "summary", "reason")} for c in reversed(apply_mod.recent_changes(n, days))])


agent_app = typer.Typer(no_args_is_help=True, help="Claude Code agent-mode plumbing.")
app.add_typer(agent_app, name="agent")


@agent_app.command("render-settings")
def agent_render_settings() -> None:
    """Write <home>/agent/settings.headless.json and mcp.json for the configured broker adapter."""
    from .agent_runtime import settings_render

    _echo({k: str(v) for k, v in settings_render.render().items()})


@agent_app.command("args")
def agent_args(stage: str = typer.Argument(..., help="A or C"), mode: str = "daily") -> None:
    """Show the exact claude CLI arguments a run would use (for debugging permissions)."""
    from .agent_runtime import claude_cli, settings_render
    from .brief.agent_writer import trade_tools_enabled
    from .sandbox import brokers

    adapter = brokers.current()
    files = settings_render.render(adapter)
    agent = settings.focos().get("agent") or {}
    if stage.upper() == "A":
        args = claude_cli.stage_a_args(adapter, model=agent.get("model_snapshot") or "sonnet",
                                       budget_usd=float((agent.get("budget_usd") or {}).get("snapshot") or 3), mcp_config=files["mcp"])
    else:
        args = claude_cli.stage_c_args(adapter, model=agent.get("model_daily") or "sonnet", budget_usd=5.0, mcp_config=files["mcp"],
                                       settings_file=files["settings"], system_prompt=files["system_prompt"],
                                       trade_enabled=trade_tools_enabled())
    _echo({"claude": claude_cli.find_claude(agent.get("claude_cli") or "auto"), "args": args})


@status_app.command("start")
def status_start(mode: str, run_id: str) -> None:
    from .run import status
    status.start(mode, run_id)


@status_app.command("fail")
def status_fail(mode: str, stage: str, error: str) -> None:
    from .run import status
    status.stage(mode, stage, False, error)


@status_app.command("finish")
def status_finish(mode: str, ok: bool = True, error: str = None, commit: str = None) -> None:
    from .run import status
    br = settings.read_json(paths.LATEST / "brief_result.json", {}) or {}
    status.finish(mode, ok, error, br.get("summary_line"), br.get("report_path"), commit)
    _echo(status.get().get(mode))


@status_app.command("show")
def status_show() -> None:
    from .run import status
    _echo(status.get())


@sandbox_app.command("allowed-tools")
def sandbox_allowed_tools() -> None:
    """Print extra tool names to allow in Stage C (empty unless live, warmed up, and not killed)."""
    from .sandbox import state
    typer.echo(",".join(state.allowed_tools_extra()))


@sandbox_app.command("set-mode")
def sandbox_set_mode(mode: str = typer.Argument(..., help="paper | live")) -> None:
    from .sandbox import state
    if mode not in ("paper", "live"):
        raise typer.BadParameter("mode must be paper or live")
    _echo(state.set_mode(mode))


@sandbox_app.command("kill")
def sandbox_kill(on: bool = True) -> None:
    from .sandbox import state
    if on:
        state.kill_file().parent.mkdir(parents=True, exist_ok=True)
        state.kill_file().write_text("halt all sandbox trading\n", encoding="utf-8")
    elif state.kill_file().exists():
        state.kill_file().unlink()
    _echo({"killed": state.killed()})


@sandbox_app.command("show")
def sandbox_show() -> None:
    from .sandbox import state
    from .sources import robinhood_snapshot as rh
    cur, _ = rh.latest_two()
    _echo(state.summary(cur))


property_app = typer.Typer(no_args_is_help=True)
app.add_typer(property_app, name="property")


@property_app.command("refresh")
def property_refresh(date: str = typer.Option(None), no_push: bool = False,
                     force: bool = typer.Option(False, help="call Zillow even if refreshed in the last 20 days")) -> None:
    """Refresh property values (Zillow or manual) and write them to the ledger. Zillow free tier: 25 calls/month."""
    from .ledger import properties
    _echo(properties.refresh(date, push=not no_push, force=force))


@property_app.command("show")
def property_show() -> None:
    _echo(settings.read_json(paths.LATEST / "properties.json", {"available": False}))


@app.command()
def doctor(export: bool = typer.Option(False, "--export", help="write a redacted diagnostics zip"),
           legacy: bool = typer.Option(False, "--legacy", hidden=True)) -> None:
    """Health checks with fix-it instructions. --export writes a redacted diagnostics zip for support."""
    if not legacy:
        from .doctor import checks

        rows = checks.run_all()
        for c in rows:
            mark = "ok " if c.ok else ("-- " if c.ok is None else "!! ")
            typer.echo(f"{mark}{c.title}: {c.detail}" + (f"\n     fix: {c.fix}" if c.ok is False and c.fix else ""))
        if export:
            from .doctor import diagnostics

            typer.echo(f"diagnostics: {diagnostics.export()}")
        if any(c.ok is False and c.severity == "error" for c in rows):
            raise typer.Exit(1)
        return
    from .run import status
    checks = {}
    checks["python"] = sys.version.split()[0]
    checks["claude"] = shutil.which("claude") or shutil.which("claude.cmd")
    checks["venv_python"] = str(paths.ROOT / ".venv" / "Scripts" / "python.exe")
    from . import holdings
    snaps = holdings.snapshot_files()
    checks["latest_snapshot"] = snaps[-1].name if snaps else None
    checks["home"] = str(paths.HOME)
    from .run import tokens
    checks["tokens"] = tokens.expiries()
    checks["token_alerts"] = tokens.alerts()
    try:
        import httpx
        checks["dashboard_up"] = httpx.get("http://127.0.0.1:3100/", timeout=5).status_code == 200
    except Exception:
        checks["dashboard_up"] = False
    checks["status"] = status.get()
    try:
        checks["git_head"] = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=paths.ROOT,
                                            capture_output=True, text=True).stdout.strip()
    except Exception:
        checks["git_head"] = None
    _echo(checks)


if __name__ == "__main__":
    app()
