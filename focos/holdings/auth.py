"""`focos auth robinhood`: register the broker's MCP server with Claude Code where an interactive shell can see it
(user scope, so it works from any folder) and run Claude Code's own OAuth login for it in this terminal.
The token lands in ~/.claude/.credentials.json, which every headless `claude -p` run shares."""
from __future__ import annotations

import json
import subprocess
from typing import Callable

from .. import paths, settings
from ..agent_runtime import claude_cli
from ..run import tokens
from ..sandbox import brokers


def robinhood(no_browser: bool = False, echo: Callable[[str], None] = print) -> int:
    cfg = settings.focos()
    exe = claude_cli.find_claude((cfg.get("agent") or {}).get("claude_cli") or "auto")
    if not exe:
        echo("Claude Code CLI not found. Install it, run `claude` once to log in, then retry.")
        return 2
    adapter = brokers.current()
    name, url = adapter.mcp_server_name, adapter.mcp_server_url

    def claude(*args: str, capture: bool = False) -> subprocess.CompletedProcess:
        echo("> claude " + " ".join(args))
        return subprocess.run([exe, *args], cwd=str(paths.HOME), shell=False,
                              capture_output=capture, text=capture, encoding="utf-8" if capture else None, errors="replace" if capture else None)

    login_args = ["mcp", "login", name] + (["--no-browser"] if no_browser else [])
    if claude("mcp", "get", name, capture=True).returncode != 0:
        add = claude("mcp", "add", "--transport", "http", "-s", "user", name, url, capture=True)
        if add.returncode != 0:
            echo((add.stderr or add.stdout or "").strip()[:500] or "could not register the server")
            return 2
    login = claude(*login_args)
    if login.returncode != 0:
        echo("Login did not complete at user scope; retrying with a registration local to the data dir.")
        claude("mcp", "add", "--transport", "http", "-s", "local", name, url, capture=True)
        login = claude(*login_args)
    st = tokens.robinhood_status()
    echo(json.dumps({"connected": st["present"] and not st["expired"], **st}))
    if st["present"] and not st["expired"]:
        echo("Robinhood is connected. The daily keep-alive job refreshes it from here on.")
        return 0
    echo("Robinhood still is not connected. Re-run `focos auth robinhood`; if Claude Code printed an error above, that is the cause.")
    return 1
