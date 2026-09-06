"""Scheduled tasks on Windows run focos with pythonw.exe (no console), so sys.stdout / sys.stderr are None and
the first write to them ends the process. Attach both to a log file in the data dir before anything runs."""
from __future__ import annotations

import io
import sys
from pathlib import Path

MAX_BYTES = 5 * 1024 * 1024


def _home_from_argv(argv: list[str]) -> str | None:
    for i, a in enumerate(argv):
        if a == "--home" and i + 1 < len(argv):
            return argv[i + 1]
        if a.startswith("--home="):
            return a.split("=", 1)[1]
    return None


def _command_from_argv(argv: list[str]) -> str:
    skip = False
    for a in argv[1:]:
        if skip:
            skip = False
            continue
        if a == "--home":
            skip = True
            continue
        if not a.startswith("-"):
            return a
    return "focos"


def log_path(argv: list[str] | None = None) -> Path:
    from . import paths

    argv = sys.argv if argv is None else argv
    home = _home_from_argv(argv)
    if home:
        paths.rebind(home)
    return paths.LOGS / f"{_command_from_argv(argv)}-windowless.log"


def attach(argv: list[str] | None = None) -> Path | None:
    """If either standard stream is missing, send both to <home>/state/logs/<command>-windowless.log."""
    if sys.stdout is not None and sys.stderr is not None:
        return None
    path = log_path(argv)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        if path.exists() and path.stat().st_size > MAX_BYTES:
            path.write_text("", encoding="utf-8")
    except OSError:
        pass
    f = open(path, "a", buffering=1, encoding="utf-8", errors="replace")  # noqa: SIM115
    if sys.stdout is None:
        sys.stdout = f
    if sys.stderr is None:
        sys.stderr = f
    return path


def is_text_stream(obj) -> bool:
    return isinstance(obj, io.TextIOBase)
