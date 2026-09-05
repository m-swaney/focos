from pathlib import Path

from focos.agent_runtime import claude_cli
from focos.sandbox.brokers.robinhood import PLACE, PREFIX, REVIEW, RobinhoodAdapter

A = RobinhoodAdapter()


def _flag(args: list[str], name: str) -> str:
    return args[args.index(name) + 1]


def test_stage_a_only_read_tools():
    args = claude_cli.stage_a_args(A, model="sonnet", budget_usd=3.0, mcp_config=Path("mcp.json"))
    assert args[:2] == ["-p", "--mcp-config"] and "--strict-mcp-config" in args
    assert _flag(args, "--permission-mode") == "dontAsk"
    assert _flag(args, "--max-budget-usd") == "3.0" and _flag(args, "--output-format") == "json"
    allow = _flag(args, "--allowedTools").split(",")
    deny = _flag(args, "--disallowedTools").split(",")
    assert allow == [PREFIX + "get_*", PREFIX + "search"]
    for t in ("Bash", "PowerShell", "Edit", "Write", "WebFetch", PLACE, REVIEW, PREFIX + "place_option_order"):
        assert t in deny


def test_stage_c_scopes_and_trade_toggle(tmp_path: Path):
    settings_file = tmp_path / "settings.headless.json"
    settings_file.write_text("{}")
    common = dict(model="opus", budget_usd=10.0, mcp_config=tmp_path / "mcp.json", settings_file=settings_file,
                  system_prompt=tmp_path / "system.md")
    off = claude_cli.stage_c_args(A, trade_enabled=False, **common)
    on = claude_cli.stage_c_args(A, trade_enabled=True, **common)
    allow_off, deny_off = _flag(off, "--allowedTools").split(","), _flag(off, "--disallowedTools").split(",")
    allow_on, deny_on = _flag(on, "--allowedTools").split(","), _flag(on, "--disallowedTools").split(",")
    assert {"Read", "Glob", "Grep", "Write(reports/**)", "Edit(state/decisions.jsonl)", "Write(state/sandbox/proposals/**)",
            PREFIX + "get_equity_quotes"} <= set(allow_off)
    assert {"Write(config/**)", "Edit(focos/**)", "Bash", PREFIX + "cancel_equity_order"} <= set(deny_off)
    assert PLACE in deny_off and REVIEW in deny_off and PLACE not in allow_off
    assert PLACE in allow_on and REVIEW in allow_on and PLACE not in deny_on
    assert _flag(on, "--settings") == str(settings_file)
    assert _flag(on, "--append-system-prompt-file") == str(tmp_path / "system.md")


def test_stage_c_omits_settings_when_missing(tmp_path: Path):
    args = claude_cli.stage_c_args(A, model="sonnet", budget_usd=5.0, mcp_config=tmp_path / "m.json",
                                   settings_file=tmp_path / "missing.json", system_prompt=tmp_path / "s.md", trade_enabled=False)
    assert "--settings" not in args


def test_find_claude_explicit_path(tmp_path: Path):
    fake = tmp_path / "claude.cmd"
    fake.write_text("")
    assert claude_cli.find_claude(str(fake)) == str(fake)
    assert claude_cli.find_claude(str(tmp_path / "nope")) is None
