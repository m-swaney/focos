"""Generate <home>/agent/settings.headless.json (deny list + PreToolUse/PostToolUse hooks that call this very
interpreter) and <home>/agent/mcp.json from the broker adapter. Re-run on init, update, and before every
agent-mode run so absolute paths never go stale."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from .. import paths
from ..sandbox import brokers
from ..sandbox.brokers.base import BrokerAdapter


def python_command() -> str:
    return Path(sys.executable).resolve().as_posix()


def settings_document(adapter: BrokerAdapter, python: str | None = None) -> dict:
    py = python or python_command()
    home = paths.HOME.as_posix()
    hook = lambda module, timeout: {"type": "command", "command": f'"{py}" -m {module} --home "{home}"', "timeout": timeout}  # noqa: E731
    return {
        "permissions": {"deny": adapter.denied_tools() + ["Bash", "PowerShell", "WebFetch", "WebSearch"]},
        "hooks": {
            "PreToolUse": [{"matcher": adapter.hook_matcher(), "hooks": [hook("focos.sandbox.gate", 60)]}],
            "PostToolUse": [{"matcher": next(k for k, v in adapter.guarded_tools().items() if v == "place"),
                             "hooks": [hook("focos.sandbox.journal", 30)]}],
        },
    }


def render(adapter: BrokerAdapter | None = None, python: str | None = None) -> dict[str, Path]:
    adapter = adapter or brokers.current()
    paths.HOME_AGENT.mkdir(parents=True, exist_ok=True)
    settings_file = paths.HOME_AGENT / "settings.headless.json"
    mcp_file = paths.HOME_AGENT / "mcp.json"
    settings_file.write_text(json.dumps(settings_document(adapter, python), indent=2) + "\n", encoding="utf-8")
    mcp_file.write_text(json.dumps(adapter.mcp_config(), indent=2) + "\n", encoding="utf-8")
    return {"settings": settings_file, "mcp": mcp_file, "system_prompt": paths.AGENT / "prompts" / "system.md"}
