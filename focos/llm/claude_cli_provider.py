"""An LLMProvider backed by `claude -p` with no tools: for small deterministic harness calls (merchant labeling)
when the household runs in agent mode and has no API key or local model. One process per call; the system
prompt goes in a file, the conversation on stdin."""
from __future__ import annotations

import json
import tempfile
from datetime import date as _date
from pathlib import Path

from .. import paths
from .base import Completion, LLMError, Message, ToolSpec, structured_via_text

NO_TOOLS = ["Read", "Glob", "Grep", "Edit", "Write", "Bash", "PowerShell", "WebFetch", "WebSearch", "Agent", "Task", "NotebookEdit"]


class ClaudeCLIProvider:
    name = "claude_cli"

    def __init__(self, model: str = "haiku", budget_usd: float = 0.2, claude: str | None = "auto", label: str = "harness"):
        self.model = model
        self.budget_usd = budget_usd
        self._claude = claude
        self.label = label

    def _args(self, system_file: Path, mcp_file: Path) -> list[str]:
        return ["-p", "--model", self.model, "--max-budget-usd", str(self.budget_usd), "--output-format", "json",
                "--no-session-persistence", "--permission-mode", "dontAsk", "--mcp-config", str(mcp_file), "--strict-mcp-config",
                "--disallowedTools", ",".join(NO_TOOLS), "--append-system-prompt-file", str(system_file)]

    def complete(self, system: str, messages: list[Message], *, max_tokens: int, tools: list[ToolSpec] | None = None,
                 tool_choice: str | None = None, cache_system: bool = True) -> Completion:
        from ..agent_runtime import claude_cli

        if tools:
            raise LLMError("the claude_cli provider does not support tool calls")
        exe = claude_cli.find_claude(self._claude)
        if not exe:
            raise LLMError("Claude Code CLI not found")
        paths.LOGS.mkdir(parents=True, exist_ok=True)
        prompt = "\n\n".join(m.content if m.role == "user" else f"(your previous reply)\n{m.content}" for m in messages)
        with tempfile.TemporaryDirectory(prefix="focos-cli-") as tmp:
            system_file = Path(tmp) / "system.md"
            system_file.write_text(system, encoding="utf-8")
            mcp_file = Path(tmp) / "mcp.json"
            mcp_file.write_text(json.dumps({"mcpServers": {}}), encoding="utf-8")
            log = paths.LOGS / f"{_date.today().isoformat()}-{self.label}-cli.json"
            try:
                result = claude_cli.run(prompt, self._args(system_file, mcp_file), log_path=log, cwd=paths.HOME, claude=self._claude,
                                        timeout_s=300)
            except Exception as e:  # noqa: BLE001
                raise LLMError(f"claude -p failed: {str(e)[:300]}") from e
        if result.get("is_error"):
            raise LLMError(str(result.get("result") or result.get("error") or result.get("subtype") or "claude error")[:300])
        return Completion(text=str(result.get("result") or ""), model=self.model, stop_reason=result.get("subtype"))

    def structured(self, system: str, messages: list[Message], schema: dict, *, max_tokens: int) -> tuple[dict, Completion]:
        return structured_via_text(self, system, messages, schema, max_tokens=max_tokens)

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float | None:
        return None

    def test(self) -> Completion:
        return self.complete("Reply with exactly: OK", [Message(role="user", content="ping")], max_tokens=8)
