"""One focos cycle in Python (replaces scripts/run_agent.ps1)."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date as _date
from datetime import datetime
from pathlib import Path

from .. import holdings, paths, settings
from ..brief import writer_for
from ..holdings.base import SourceError
from ..run import status
from . import git_ops

log = logging.getLogger("focos.run")


@dataclass
class RunOptions:
    mode: str = "daily"
    date: str | None = None
    skip_a: bool = False
    skip_b: bool = False
    skip_c: bool = False
    no_git: bool = False
    heavy: bool | None = None
    dry_run: bool = False


@dataclass
class RunResult:
    run_id: str
    mode: str
    date: str
    ok: bool = True
    stages: dict = field(default_factory=dict)
    commit: str | None = None
    log_file: str | None = None


def describe(opts: RunOptions) -> dict:
    """What a run would do with the current config (for --dry-run and the doctor)."""
    cfg = settings.focos()
    src = holdings.current()
    ok, why = src.available()
    writer = writer_for(cfg.get("ai"))
    return {"home": str(paths.HOME), "mode": opts.mode, "date": opts.date or _date.today().isoformat(),
            "holdings_source": {"name": src.name, "available": ok, "reason": why},
            "ledger_provider": (cfg.get("ledger") or {}).get("provider"),
            "brief_writer": writer.mode_name, "ai": cfg.get("ai"), "git": cfg.get("git"),
            "skips": {"A": opts.skip_a, "B": opts.skip_b, "C": opts.skip_c}}


def _setup_logging(date: str, mode: str) -> Path:
    paths.LOGS.mkdir(parents=True, exist_ok=True)
    p = paths.LOGS / f"{date}-{mode}-run.log"
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


def _ledger_backup(date: str) -> str | None:
    """Provider-owned backup (SQLite copy, or pg_dump for Sure); keeps the newest 8."""
    from ..ledger import providers

    provider = providers.current()
    if provider is None:
        return None
    paths.BACKUPS.mkdir(parents=True, exist_ok=True)
    ext = "sql" if provider.name == "sure" else "sqlite"
    out = paths.BACKUPS / f"ledger-{provider.name}-{date}.{ext}"
    try:
        res = provider.backup(out)
    except Exception as e:  # noqa: BLE001
        log.warning("ledger backup skipped: %s", e)
        return None
    if not res:
        return None
    for old in sorted(paths.BACKUPS.glob(f"ledger-{provider.name}-*"), key=lambda p: p.stat().st_mtime, reverse=True)[8:]:
        old.unlink(missing_ok=True)
    return str(res)


def run(opts: RunOptions) -> RunResult:
    paths.ensure_dirs()
    date = opts.date or _date.today().isoformat()
    run_id = f"{opts.mode}-{date}-{datetime.now().strftime('%H%M%S')}"
    logfile = _setup_logging(date, opts.mode)
    res = RunResult(run_id=run_id, mode=opts.mode, date=date, log_file=str(logfile))
    cfg = settings.focos()
    status.start(opts.mode, run_id)
    log.info("run %s started (home=%s)", run_id, paths.HOME)

    # ---- Stage A: holdings snapshot
    if opts.skip_a:
        log.info("Stage A skipped")
        res.stages["A"] = "skipped"
    else:
        src = holdings.current()
        ok, why = src.available()
        log.info("Stage A: holdings via %s", src.name)
        if not ok:
            status.stage(opts.mode, "A", False, why or "holdings source unavailable")
            log.error("Stage A failed: %s", why)
            res.ok = False
            res.stages["A"] = f"failed: {why}"
            status.finish(opts.mode, False, f"A : {why}")
            return res
        try:
            snap = src.capture(date, opts.mode, run_id)
            meta = getattr(src, "last_meta", {}) or {}
            n_acc = len((snap or {}).get("accounts", []))
            status.stage(opts.mode, "A", True, cost_usd=meta.get("cost_usd"),
                         extra={**meta, "source": src.name, "accounts": n_acc, "total_value": (snap or {}).get("total_value")})
            res.stages["A"] = f"ok ({src.name}, {n_acc} accounts)"
        except (SourceError, Exception) as e:  # noqa: BLE001
            msg = f"{type(e).__name__}: {str(e)[:300]}"
            status.stage(opts.mode, "A", False, msg)
            log.error("Stage A failed: %s", msg)
            res.ok = False
            res.stages["A"] = f"failed: {msg}"
            status.finish(opts.mode, False, f"A : {msg}")
            return res

    # ---- Stage B: pipeline
    if opts.skip_b:
        log.info("Stage B skipped")
        res.stages["B"] = "skipped"
    else:
        from .. import pipeline

        log.info("Stage B: pipeline")
        try:
            out = pipeline.run(opts.mode, date, opts.heavy)
            status.stage(opts.mode, "B", True, extra=out)
            res.stages["B"] = f"ok ({len(out.get('files', []))} files)"
        except Exception as e:  # noqa: BLE001
            msg = f"{type(e).__name__}: {str(e)[:300]}"
            status.stage(opts.mode, "B", False, msg)
            log.exception("Stage B failed")
            res.ok = False
            res.stages["B"] = f"failed: {msg}"
            status.finish(opts.mode, False, f"B : {msg}")
            return res

    # ---- Stage C: brief
    if opts.skip_c:
        log.info("Stage C skipped")
        res.stages["C"] = "skipped"
    else:
        writer = writer_for(cfg.get("ai"))
        log.info("Stage C: brief via %s mode", writer.mode_name)
        outcome = writer.write(opts.mode, date, run_id)
        status.stage(opts.mode, "C", outcome.ok, outcome.error, cost_usd=outcome.cost_usd, extra=outcome.meta)
        if outcome.ok:
            res.stages["C"] = f"ok ({outcome.report_path})"
        else:
            log.error("Stage C failed: %s", outcome.error)
            res.ok = False
            res.stages["C"] = f"failed: {outcome.error}"

    # ---- backup (weekly/monthly)
    if opts.mode != "daily":
        bk = _ledger_backup(date)
        if bk:
            log.info("ledger backup written to %s", bk)
            res.stages["backup"] = bk

    # ---- commit the data dir
    git_cfg = cfg.get("git") or {}
    if not opts.no_git and git_cfg.get("commit_each_run", True):
        try:
            res.commit = git_ops.commit_run(paths.HOME, f"run: {opts.mode} {date}",
                                            tuple(git_cfg.get("commit_paths") or git_ops.DEFAULT_PATHS),
                                            git_cfg.get("author_name"), git_cfg.get("author_email"),
                                            push=bool(git_cfg.get("push")))
            log.info("commit: %s", res.commit or "nothing to commit")
        except Exception as e:  # noqa: BLE001
            log.warning("git step skipped: %s", e)

    br = settings.read_json(paths.LATEST / "brief_result.json", {}) or {}
    status.finish(opts.mode, res.ok, None if res.ok else "; ".join(v for v in res.stages.values() if v.startswith("failed")),
                  br.get("summary_line") if not opts.skip_c else None, br.get("report_path") if not opts.skip_c else None,
                  res.commit)
    log.info("run %s finished ok=%s", run_id, res.ok)
    return res
