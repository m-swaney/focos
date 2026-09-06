"""Supervise the Next.js dashboard (and, when installed, the local API) as child processes with restarts."""
from __future__ import annotations

import csv
import io
import json
import logging
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

from .. import paths, settings

log = logging.getLogger("focos.service")


def _children_file() -> Path:
    return paths.LOGS / "service-children.json"


def _record(children: list["Child"]) -> None:
    """Remember the child pids. Task Scheduler ends this process without running our cleanup, so the record is
    the only way a later start can tell that the dashboard still holding the port is our own orphan."""
    try:
        paths.LOGS.mkdir(parents=True, exist_ok=True)
        alive = [{"pid": c.proc.pid, "exe": c.argv[0]} for c in children if c.proc and c.alive()]
        _children_file().write_text(json.dumps(alive), encoding="utf-8")
    except OSError as e:
        log.warning("could not record child pids: %s", e)


def _image_name(pid: int) -> str | None:
    """Image name of the running process, or None when nothing is running under that pid."""
    try:
        if sys.platform == "win32":
            r = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH", "/FO", "CSV"],
                               capture_output=True, text=True, timeout=15)
            row = next(csv.reader(io.StringIO(r.stdout)), None)
            return row[0] if row and len(row) > 1 else None
        r = subprocess.run(["ps", "-p", str(pid), "-o", "comm="], capture_output=True, text=True, timeout=15)
        return Path(r.stdout.strip()).name or None
    except (OSError, subprocess.SubprocessError):
        return None


def reap_orphans() -> list[int]:
    """Kill dashboard children left behind by a previous supervisor that was killed rather than shut down.
    A pid is only killed when it is still running the same executable we launched, so a recycled pid
    belonging to something else is left alone. Returns the pids actually killed."""
    try:
        recorded = json.loads(_children_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    killed = []
    for entry in recorded if isinstance(recorded, list) else []:
        pid, exe = entry.get("pid"), entry.get("exe") or ""
        if not isinstance(pid, int) or pid == os.getpid():
            continue
        if _image_name(pid) != Path(exe).name:
            continue
        try:
            os.kill(pid, signal.SIGTERM)
            killed.append(pid)
            log.warning("killed orphaned %s (pid %s) left by an earlier run", Path(exe).name, pid)
        except OSError as e:
            log.warning("could not kill orphaned pid %s: %s", pid, e)
    _children_file().unlink(missing_ok=True)
    return killed


def node_exe() -> str | None:
    bundled = paths.user_home() / ".focos" / "node" / ("node.exe" if sys.platform == "win32" else "bin/node")
    if bundled.exists():
        return str(bundled)
    return shutil.which("node")


def _ensure_static(dash: Path, standalone_dir: Path) -> None:
    """Next's standalone output expects .next/static and public next to server.js; copy them in when missing
    or older than the build (the release bundle ships them at their original locations)."""
    for rel in (Path(".next") / "static", Path("public")):
        src, dst = dash / rel, standalone_dir / rel
        if not src.exists():
            continue
        if not dst.exists() or src.stat().st_mtime > dst.stat().st_mtime:
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst)


def dashboard_command() -> tuple[list[str], Path] | None:
    """Prebuilt standalone server (release installs) or `npm run start` (dev checkouts)."""
    dash = paths.APP / "dashboard"
    standalone = dash / ".next" / "standalone" / "server.js"
    node = node_exe()
    if standalone.exists() and node:
        try:
            _ensure_static(dash, standalone.parent)
        except OSError as e:
            log.warning("could not stage dashboard static assets: %s", e)
        return [node, str(standalone)], standalone.parent
    if (dash / "package.json").exists() and (dash / ".next").exists():
        npm = shutil.which("npm.cmd") or shutil.which("npm")
        if npm:
            return [npm, "run", "start"], dash
    return None


def _env(port: int, host: str = "127.0.0.1") -> dict[str, str]:
    """The dashboard binds to `host` (dashboard.host in focos.yml); the local API always stays on loopback and
    is reached through the dashboard's server-side proxy, so opening the dashboard to a tailnet or LAN never
    exposes the API or its token."""
    env = dict(os.environ)
    env.update({"FOCOS_HOME": str(paths.HOME), "PORT": str(port), "HOSTNAME": host or "127.0.0.1", "NODE_ENV": "production"})
    token = os.environ.get("FOCOS_DASH_TOKEN")
    if token:
        env["FOCOS_DASH_TOKEN"] = token
    return env


class Child:
    def __init__(self, name: str, argv: list[str], cwd: Path, env: dict[str, str]):
        self.name, self.argv, self.cwd, self.env = name, argv, cwd, env
        self.proc: subprocess.Popen | None = None
        self.failures = 0

    def start(self) -> None:
        log.info("%s: starting %s", self.name, " ".join(self.argv[:2]))
        self.proc = subprocess.Popen(self.argv, cwd=str(self.cwd), env=self.env,
                                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))

    def alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def stop(self) -> None:
        if self.alive():
            self.proc.terminate()
            try:
                self.proc.wait(10)
            except subprocess.TimeoutExpired:
                self.proc.kill()


def serve(with_dashboard: bool = True, with_api: bool = True, once: bool = False) -> int:
    cfg = settings.focos().get("dashboard") or {}
    children: list[Child] = []
    if with_dashboard:
        cmd = dashboard_command()
        if cmd:
            children.append(Child("dashboard", cmd[0], cmd[1], _env(int(cfg.get("port") or 3100), str(cfg.get("host") or "127.0.0.1"))))
            log.info("dashboard: listening on %s:%s", cfg.get("host") or "127.0.0.1", cfg.get("port") or 3100)
        else:
            log.warning("dashboard: no build found under %s (run the installer or `npm run build`)", paths.APP / "dashboard")
    api_thread = None
    if with_api:
        try:
            from ..api.app import run_in_thread  # available once the local API phase is installed

            api_thread = run_in_thread(int(cfg.get("api_port") or 3101))
        except ImportError as e:
            log.info("api: not available (%s)", e)
    stop = threading.Event()

    def _sig(*_):
        stop.set()

    for s in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(s, _sig)
        except (ValueError, OSError):
            pass
    reap_orphans()  # a previous supervisor may have been killed without releasing the dashboard's port
    for c in children:
        c.start()
    _record(children)
    if once:
        time.sleep(1)
        for c in children:
            c.stop()
        _children_file().unlink(missing_ok=True)
        return 0
    try:
        while not stop.is_set():
            for c in children:
                if not c.alive():
                    c.failures += 1
                    backoff = min(60, 2 ** min(c.failures, 6))
                    log.warning("%s exited (code %s); restarting in %ss", c.name, c.proc.returncode if c.proc else None, backoff)
                    stop.wait(backoff)
                    if not stop.is_set():
                        c.start()
                        _record(children)
            stop.wait(2)
    finally:
        for c in children:
            c.stop()
        _children_file().unlink(missing_ok=True)
    return 0
