"""An intraday trading pass: read the agentic account fresh, then let the agent act inside the sandbox rules.

This is not a cut-down daily run. The daily run at 16:35 exists to write a brief, and it lands after the
close, where `market_orders_only_during_rth` rejects every market order the agent could build from its own
proposal schema. A trading pass exists to execute, so it runs inside regular hours and does only what
executing needs:

    T-A   one broker read scoped to the agentic account  ->  state/sandbox/live.json
    T-B   the exit plan, in code: breached stops and missing resting stops  ->  state/sandbox/exits.json
    T-C   the agent sends the required exits, then proposes, reviews, and places  ->  proposals, orders, decisions
    T-V   verify against the order journal: a required exit that did not reach the broker fails the pass

What it deliberately leaves alone: the holdings snapshot and the dated derived folders (so the daily diff and
the dashboard's day-over-day numbers are whatever the daily run last wrote), the ledger, the inbox, and the
sandbox warmup counter. Skipping Stage B is the point -- the analytics are a closing-price story and nothing
here needs them.

Outside regular hours the pass exits before spending a token: every order it could produce would be blocked.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date as _date
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .. import paths, settings
from ..agent_runtime import claude_cli, settings_render
from ..brief import prompts
from ..run import claude_io, status
from .. import notify
from ..sandbox import brokers, exits, live, market_calendar, performance
from ..sandbox import state as sandbox_state
from . import git_ops

log = logging.getLogger("focos.trade")

MODE = "trade"


@dataclass
class TradeResult:
    run_id: str
    date: str
    ok: bool = True
    skipped: str | None = None
    stages: dict = field(default_factory=dict)
    proposals: list = field(default_factory=list)
    trades_placed: list = field(default_factory=list)
    commit: str | None = None
    log_file: str | None = None


def _setup_logging(date: str) -> Path:
    paths.LOGS.mkdir(parents=True, exist_ok=True)
    p = paths.LOGS / f"{date}-{MODE}-run.log"
    handler = logging.FileHandler(p, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    root = logging.getLogger("focos")
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    if not any(isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler) for h in root.handlers):
        sh = logging.StreamHandler()
        sh.setFormatter(logging.Formatter("[%(asctime)s] %(message)s", "%H:%M:%S"))
        root.addHandler(sh)
    return p


def market_now() -> datetime:
    """Now in the broker's market timezone -- the clock the sandbox rules are written against, which is not
    necessarily the household's."""
    return datetime.now(ZoneInfo(brokers.current().market_tz))


def why_not(now: datetime | None = None) -> str | None:
    """The reason this pass should not run at all, or None to proceed.

    Checked before any token is spent, and each reason is one the gate would raise anyway at order time.
    """
    now = now or market_now()
    if not (settings.focos().get("agent") or {}).get("sandbox_enabled"):
        return "agent.sandbox_enabled is false"
    if sandbox_state.killed():
        return "KILL switch is set (state/sandbox/KILL)"
    closed = market_calendar.why_closed(now, settings.sandbox_rules().get("no_trading_days") or [])
    if closed:
        return f"{closed} ({now:%H:%M} {now.tzname() or 'local'}); orders would be rejected"
    return None


def capture_live(date: str, run_id: str) -> dict:
    """T-A: one scoped broker read of the agentic account, published to state/sandbox/live.json."""
    from ..holdings.base import SourceError
    from ..holdings.robinhood_mcp import RobinhoodMCPSource

    cfg = settings.focos()
    agent = cfg.get("agent") or {}
    adapter = brokers.current()
    source = RobinhoodMCPSource()
    ok, why = source.available()
    if not ok:
        raise SourceError(why or "broker unavailable")
    files = settings_render.render(adapter)
    args = claude_cli.stage_a_args(adapter, model=agent.get("model_snapshot") or "sonnet",
                                   budget_usd=float((agent.get("budget_usd") or {}).get("trade_snapshot") or 1.0),
                                   mcp_config=files["mcp"])
    prompt = prompts.render_trade_snapshot(date, run_id)
    logp = paths.LOGS / f"{date}-{MODE}-A-{run_id[-6:]}.json"
    if agent.get("debug_claude"):
        args += claude_cli.debug_args(paths.LOGS / f"{date}-{MODE}-A-{run_id[-6:]}.debug.log")
    result = claude_cli.run(prompt, args, log_path=logp, cwd=paths.HOME, claude=agent.get("claude_cli") or "auto")
    meta = claude_io.summarize(result)
    if meta["is_error"]:
        raise SourceError(str(result.get("result") or result.get("error") or meta.get("subtype"))[:400])
    payload = claude_io.extract_json(result.get("result") or "")
    if not isinstance(payload, dict) or not payload.get("account_number"):
        raise SourceError("live read returned no account_number")
    # full account number stays in state/raw (gitignored); the published view is masked
    settings.write_json(paths.RAW / f"{date}-{MODE}-{run_id[-6:]}.json", payload)
    view = live.write(live.normalize(payload))
    try:
        performance.record_fills(payload.get("filled_orders") or [])
    except Exception as e:  # noqa: BLE001 -- the scorecard can wait; the pass cannot
        log.warning("fills not recorded: %s", e)
    view["_meta"] = meta
    return view


def run_pass(date: str | None = None, now: datetime | None = None, force: bool = False,
             exits_only: bool = False) -> TradeResult:
    paths.ensure_dirs()
    date = date or _date.today().isoformat()
    now = now or market_now()
    run_id = f"{MODE}-{date}-{now.strftime('%H%M%S')}"
    logfile = _setup_logging(date)
    res = TradeResult(run_id=run_id, date=date, log_file=str(logfile))

    skip = None if force else why_not(now)
    if skip:
        log.info("trading pass %s skipped: %s", run_id, skip)
        res.skipped = skip
        res.stages["T"] = f"skipped: {skip}"
        return res

    cfg = settings.focos()
    agent = cfg.get("agent") or {}
    status.start(MODE, run_id)
    log.info("trading pass %s started (home=%s)", run_id, paths.HOME)

    # ---- T-A: fresh view of the agentic account
    try:
        view = capture_live(date, run_id)
        p = view.get("portfolio") or {}
        log.info("T-A: account %s, cash %.2f, %d position(s)", view.get("last4"), p.get("cash") or 0,
                 len(view.get("positions") or []))
        status.stage(MODE, "A", True, extra={"cash": p.get("cash"), "positions": len(view.get("positions") or [])})
        res.stages["A"] = f"ok (cash {p.get('cash')}, {len(view.get('positions') or [])} positions)"
    except Exception as e:  # noqa: BLE001
        msg = f"{type(e).__name__}: {str(e)[:300]}"
        log.error("T-A failed: %s", msg)
        status.stage(MODE, "A", False, msg)
        status.finish(MODE, False, f"A : {msg}")
        res.ok = False
        res.stages["A"] = f"failed: {msg}"
        notify.send("focos: trading pass could not read the account", msg[:300], "warn", key=f"trade_a_failed:{date}")
        return res

    # ---- T-B: the exit plan. Code decides which stops are breached; the model only sends the orders.
    trade_enabled = sandbox_state.trading_enabled()
    try:
        plan = exits.build(view, today=date, write_proposals=trade_enabled)
    except Exception as e:  # noqa: BLE001
        log.error("T-B failed: %s", e)
        plan = {"required_exits": [], "missing_stops": [], "positions": [], "error": str(e)[:300]}
    if plan.get("required_exits"):
        log.warning("T-B: required exits %s", ", ".join(e["symbol"] for e in plan["required_exits"]))
    if plan.get("missing_stops"):
        log.info("T-B: protective stops to place %s", ", ".join(s["symbol"] for s in plan["missing_stops"]))
    res.stages["B"] = (f"{len(plan.get('required_exits') or [])} required exit(s), "
                       f"{len(plan.get('missing_stops') or [])} stop(s) to place")

    # ---- T-C: the agent trades
    adapter = brokers.current()
    files = settings_render.render(adapter)
    rendered_system = paths.HOME_AGENT / "system.rendered.md"
    rendered_system.write_text(prompts.system_prompt() + "\n\n" + prompts.addendum("agent"), encoding="utf-8")
    budget_key = "trade_exits" if exits_only else MODE
    budget_default = 0.75 if exits_only else 6.0
    args = claude_cli.stage_trade_args(adapter, model=agent.get("model_trade") or "opus",
                                       budget_usd=float((agent.get("budget_usd") or {}).get(budget_key) or budget_default),
                                       mcp_config=files["mcp"], settings_file=files["settings"],
                                       system_prompt=rendered_system, trade_enabled=trade_enabled,
                                       exits_only=exits_only)
    logp = paths.LOGS / f"{date}-{MODE}-C-{run_id[-6:]}.json"
    if agent.get("debug_claude"):
        args += claude_cli.debug_args(paths.LOGS / f"{date}-{MODE}-C-{run_id[-6:]}.debug.log")
    log.info("T-C: %s pass (trade tools %s)", "exits-only" if exits_only else "trading",
             "on" if trade_enabled else "off")
    # The gate runs as its own process and cannot see this call's arguments, so the kind of pass goes on disk
    # where the hook can read it. Cleared however this ends: a stale marker would mute the next pass's buys.
    sandbox_state.start_pass("exits" if exits_only else "trade", run_id)
    started_at = datetime.now(settings.tz()).replace(microsecond=0)   # the journal stamps whole seconds
    prompt = prompts.render_trade(date, run_id, exits_only=exits_only,
                                  exits_block=exits.prompt_block(plan) if trade_enabled else None)
    try:
        result = claude_cli.run(prompt, args, log_path=logp, cwd=paths.HOME, claude=agent.get("claude_cli") or "auto")
    except Exception as e:  # noqa: BLE001
        msg = f"{type(e).__name__}: {str(e)[:300]}"
        log.error("T-C failed: %s", msg)
        status.stage(MODE, "C", False, msg)
        _verify(res, plan, started_at, trade_enabled)
        status.finish(MODE, False, f"C : {msg}")
        res.ok = False
        res.stages["C"] = f"failed: {msg}"
        return res
    finally:
        sandbox_state.end_pass()

    meta = {**claude_io.summarize(result), "trade_tools": trade_enabled, "exits_only": exits_only}
    if meta["is_error"]:
        msg = str(result.get("result") or result.get("error") or meta.get("subtype"))[:400]
        log.error("T-C failed: %s", msg)
        status.stage(MODE, "C", False, msg, extra=meta)
        _verify(res, plan, started_at, trade_enabled)
        status.finish(MODE, False, f"C : {msg}")
        res.ok = False
        res.stages["C"] = f"failed: {msg}"
        return res
    try:
        payload = claude_io.extract_json(result.get("result") or "")
    except Exception as e:  # noqa: BLE001  -- a pass that traded but garbled its summary still traded
        log.warning("T-C returned no JSON summary: %s", e)
        payload = {}
    res.proposals = list(payload.get("proposals") or [])
    res.trades_placed = list(payload.get("trades_placed") or [])
    res.stages["C"] = f"ok ({len(res.trades_placed)} placed, {len(res.proposals)} proposed)"
    status.stage(MODE, "C", True, extra={**meta, "proposals": len(res.proposals), "trades": len(res.trades_placed)})
    log.info("T-C: %d order(s) placed, %d proposal(s)", len(res.trades_placed), len(res.proposals))

    # ---- T-V: what actually reached the broker
    missed = _verify(res, plan, started_at, trade_enabled)

    # ---- commit
    git_cfg = cfg.get("git") or {}
    if git_cfg.get("commit_each_run", True):
        try:
            res.commit = git_ops.commit_run(paths.HOME, f"trade: {date} {now:%H:%M}",
                                            tuple(git_cfg.get("commit_paths") or git_ops.DEFAULT_PATHS),
                                            git_cfg.get("author_name"), git_cfg.get("author_email"),
                                            push=bool(git_cfg.get("push")))
            log.info("commit: %s", res.commit or "nothing to commit")
        except Exception as e:  # noqa: BLE001
            log.warning("git step skipped: %s", e)

    summary = (f"{len(res.trades_placed)} order(s) placed" if res.trades_placed else
               f"{len(res.proposals)} proposal(s), no orders" if res.proposals else "no action")
    error = None
    if missed:
        # "no action" while a stop sits breached is the failure 0.3.6 reported as success for days.
        res.ok = False
        error = f"required exit not placed: {', '.join(missed)}"
        summary = f"{error}; {summary}"
    status.finish(MODE, res.ok, error, summary, None, res.commit)
    try:
        from .. import needs_you

        needs_you.refresh(date)
    except Exception:  # noqa: BLE001
        pass
    log.info("trading pass %s finished ok=%s (%s)", run_id, res.ok, summary)
    return res


def _placed_since(started_at: datetime) -> list[dict]:
    """Orders the broker accepted during this pass, from the journal (not the model's summary)."""
    out = []
    for o in exits.accepted_orders():
        try:
            if datetime.fromisoformat(str(o.get("_ts"))) >= started_at:
                out.append(o)
        except ValueError:
            continue
    return out


def _verify(res: TradeResult, plan: dict, started_at: datetime, trade_enabled: bool) -> list[str]:
    """Check the plan against the journal, record it in status, and push what the household should know: every
    order placed, and loudly, any required exit that did not go through. Returns the symbols of missed exits."""
    if not trade_enabled:
        return []
    check = exits.verify(plan)
    placed = _placed_since(started_at)
    res.stages["V"] = (f"exits done {check['exits_done'] or '-'}, missed {check['exits_missed'] or '-'}, "
                       f"stops missed {check['stops_missed'] or '-'}")
    status.stage(MODE, "V", not check["exits_missed"], None if not check["exits_missed"] else
                 f"required exit not placed: {', '.join(check['exits_missed'])}", extra={**check, "placed": len(placed)})
    if check["exits_missed"]:
        detail = "; ".join(f"{e['symbol']} ({e['reason']})" for e in plan.get("required_exits", [])
                           if e["symbol"] in check["exits_missed"])
        notify.send("focos: stop exit did not go through",
                    f"{detail}. The next pass will try again; sell by hand in the Robinhood app if you want it out now.",
                    "critical", key=f"exit_missed:{res.run_id}")
    if check["stops_missed"]:
        notify.send("focos: protective stop not placed", f"No resting stop for {', '.join(check['stops_missed'])}. "
                    "The next pass will try again.", "warn", key=f"stops_missed:{res.date}:{','.join(check['stops_missed'])}")
    if placed and (settings.focos().get("notify") or {}).get("trades", True):
        lines = [f"{o.get('side')} {o.get('quantity') or ('$' + str(o.get('dollar_amount')))} {o.get('symbol')} "
                 f"({o.get('type')}{' @ ' + str(o.get('limit_price')) if o.get('limit_price') else ''}"
                 f"{' stop ' + str(o.get('stop_price')) if o.get('stop_price') else ''})" for o in placed]
        notify.send(f"focos sandbox: {len(placed)} order(s)", "\n".join(lines), "info", key=f"orders:{res.run_id}")
    return check["exits_missed"]
