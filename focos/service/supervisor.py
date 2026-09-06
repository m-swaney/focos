"""Supervise the Next.js dashboard (and, when installed, the local API) as child processes with restarts."""
from __future__ import annotations

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
    for c in children:
        c.start()
    if once:
        time.sleep(1)
        for c in children:
            c.stop()
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
            stop.wait(2)
    finally:
        for c in children:
            c.stop()
    return 0
