"""Locate and invoke `claude -p`. Argument builders are pure so tests can pin the exact CLI contract."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from ..run import claude_io
from ..sandbox.brokers.base import BrokerAdapter

FILE_TOOLS = ["Read", "Glob", "Grep"]
DENY_BUILTINS = ["Bash", "PowerShell", "NotebookEdit", "WebFetch", "WebSearch", "Agent", "Task"]
WRITE_SCOPES = ["reports/**", "state/decisions.jsonl", "state/sandbox/proposals/**"]
PROTECTED_SCOPES = ["config/**", "agent/**", "focos/**", "dashboard/**", "scripts/**"]


class ClaudeNotFound(RuntimeError):
    pass


def find_claude(explicit: str | None = "auto") -> str | None:
    if explicit and explicit != "auto":
        return explicit if Path(explicit).exists() else None
    for name in ("claude", "claude.cmd", "claude.exe"):
        hit = shutil.which(name)
        if hit:
            return hit
    appdata = os.environ.get("APPDATA")
    if appdata and (Path(appdata) / "npm" / "claude.cmd").exists():
        return str(Path(appdata) / "npm" / "claude.cmd")
    return None


def _common(model: str, budget_usd: float, mcp_config: Path) -> list[str]:
    return ["-p", "--mcp-config", str(mcp_config), "--strict-mcp-config", "--permission-mode", "dontAsk",
            "--model", model, "--max-budget-usd", str(budget_usd), "--output-format", "json", "--no-session-persistence"]


def stage_a_args(adapter: BrokerAdapter, *, model: str, budget_usd: float, mcp_config: Path) -> list[str]:
    """Snapshot: only the broker's read tools; every write, shell, and trade tool denied."""
    allow = adapter.readonly_tools_stage_a()
    deny = DENY_BUILTINS + ["Edit", "Write"] + adapter.trade_tools() + adapter.denied_tools()
    return _common(model, budget_usd, mcp_config) + ["--allowedTools", ",".join(allow), "--disallowedTools", ",".join(deny)]


def stage_c_args(adapter: BrokerAdapter, *, model: str, budget_usd: float, mcp_config: Path, settings_file: Path,
                 system_prompt: Path, trade_enabled: bool) -> list[str]:
    """Brief: file tools scoped to reports/decisions/proposals, broker read tools, trade tools only when the
    sandbox says so (the PreToolUse gate in settings_file still checks every order)."""
    allow = list(FILE_TOOLS)
    for scope in WRITE_SCOPES:
        allow += [f"Edit({scope})", f"Write({scope})"]
    allow += adapter.readonly_tools_stage_c()
    deny = list(DENY_BUILTINS)
    for scope in PROTECTED_SCOPES:
        deny += [f"Edit({scope})", f"Write({scope})"]
    deny += adapter.denied_tools()
    if trade_enabled:
        allow += adapter.trade_tools()
    else:
        deny += adapter.trade_tools()
    args = _common(model, budget_usd, mcp_config)
    args += ["--append-system-prompt-file", str(system_prompt), "--allowedTools", ",".join(allow),
             "--disallowedTools", ",".join(deny)]
    if settings_file.exists():
        args += ["--settings", str(settings_file)]
    return args


def run(prompt: str, args: list[str], *, log_path: Path, cwd: Path, claude: str | None = "auto",
        timeout_s: int = 2700) -> dict:
    """Run claude with the prompt on stdin; stdout goes to log_path (UTF-8), stderr to log_path + '.err'.
    Returns the parsed result object (claude_io.read_result)."""
    exe = find_claude(claude)
    if not exe:
        raise ClaudeNotFound("Claude Code CLI not found")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    with log_path.open("wb") as out, Path(str(log_path) + ".err").open("wb") as err:
        proc = subprocess.run([exe, *args], input=prompt.encode("utf-8"), stdout=out, stderr=err, cwd=str(cwd),
                              env=env, timeout=timeout_s, shell=False)
    result = claude_io.read_result(log_path)
    result.setdefault("_exit_code", proc.returncode)
    return result
