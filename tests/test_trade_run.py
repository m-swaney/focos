"""The intraday trading pass: when it refuses to run, and what tools it is given."""
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import yaml

from focos import paths, settings
from focos.agent_runtime import claude_cli
from focos.orchestrator import trade
from focos.sandbox.brokers.robinhood import PLACE, PREFIX, REVIEW, RobinhoodAdapter

ET = ZoneInfo("America/New_York")


def _enable_sandbox(home: Path):
    (home / "config" / "focos.yml").write_text(yaml.safe_dump({"agent": {"sandbox_enabled": True}}))
    settings.reset()


def test_refuses_outside_regular_hours(initialized_home: Path):
    """The whole bug this fixes: an order placed after the close is rejected by the rules, so a pass there
    would burn tokens for a guaranteed refusal."""
    _enable_sandbox(initialized_home)
    assert trade.why_not(datetime(2026, 9, 18, 16, 35, tzinfo=ET)) is not None   # after the close
    assert trade.why_not(datetime(2026, 9, 18, 9, 0, tzinfo=ET)) is not None     # before the open
    assert trade.why_not(datetime(2026, 9, 19, 11, 0, tzinfo=ET)) is not None    # Saturday
    assert trade.why_not(datetime(2026, 11, 26, 11, 0, tzinfo=ET)) is not None   # Thanksgiving
    assert trade.why_not(datetime(2026, 11, 27, 15, 0, tzinfo=ET)) is not None   # half day, after the 13:00 close
    assert trade.why_not(datetime(2026, 9, 18, 10, 30, tzinfo=ET)) is None       # Friday, mid-session
    assert trade.why_not(datetime(2026, 9, 18, 15, 0, tzinfo=ET)) is None


def test_refuses_when_the_kill_switch_is_set(initialized_home: Path):
    _enable_sandbox(initialized_home)
    mid_session = datetime(2026, 9, 18, 11, 0, tzinfo=ET)
    assert trade.why_not(mid_session) is None
    paths.SANDBOX.mkdir(parents=True, exist_ok=True)
    (paths.SANDBOX / "KILL").write_text("halt", encoding="utf-8")
    assert "KILL" in trade.why_not(mid_session)


def test_refuses_when_the_sandbox_is_off(initialized_home: Path):
    (initialized_home / "config" / "focos.yml").write_text(yaml.safe_dump({"agent": {"sandbox_enabled": False}}))
    settings.reset()
    assert "sandbox_enabled" in trade.why_not(datetime(2026, 9, 18, 11, 0, tzinfo=ET))


def test_run_pass_skips_without_spending_anything(initialized_home: Path, monkeypatch):
    _enable_sandbox(initialized_home)
    monkeypatch.setattr(trade, "market_now", lambda: datetime(2026, 9, 18, 20, 0, tzinfo=ET))

    def boom(*a, **k):
        raise AssertionError("a skipped pass must not call the broker")

    monkeypatch.setattr(trade, "capture_live", boom)
    res = trade.run_pass()
    assert res.skipped and res.ok and not res.trades_placed


def test_trade_args_scope_writes_to_proposals_and_decisions_only(tmp_path):
    a = RobinhoodAdapter()
    gate_file = tmp_path / "settings.headless.json"
    gate_file.write_text("{}", encoding="utf-8")
    args = claude_cli.stage_trade_args(a, model="sonnet", budget_usd=2.0, mcp_config=Path("mcp.json"),
                                       settings_file=gate_file, system_prompt=Path("sys.md"),
                                       trade_enabled=True)
    allow = args[args.index("--allowedTools") + 1].split(",")
    deny = args[args.index("--disallowedTools") + 1].split(",")
    assert "Write(state/sandbox/proposals/**)" in allow and "Write(state/decisions.jsonl)" in allow
    # a trading pass writes no brief and touches no config
    assert "Write(reports/**)" in deny and "Write(config/**)" in deny and "Write(state/updates/**)" in deny
    assert "Bash" in deny and "WebFetch" in deny
    assert PLACE in allow and REVIEW in allow
    assert PREFIX + "place_option_order" in deny and PREFIX + "place_crypto_order" in deny


def test_trade_args_withhold_trade_tools_when_the_sandbox_says_so():
    a = RobinhoodAdapter()
    args = claude_cli.stage_trade_args(a, model="sonnet", budget_usd=2.0, mcp_config=Path("mcp.json"),
                                       settings_file=Path("nope.json"), system_prompt=Path("sys.md"),
                                       trade_enabled=False)
    allow = args[args.index("--allowedTools") + 1].split(",")
    deny = args[args.index("--disallowedTools") + 1].split(",")
    assert PLACE not in allow and REVIEW not in allow
    assert PLACE in deny and REVIEW in deny


def test_trade_prompts_render(initialized_home: Path):
    from focos.brief import prompts

    snap = prompts.render_trade_snapshot("2026-09-18", "trade-1")
    assert "Agentic account" in snap and "account_number" in snap and "Return ONLY the JSON object" in snap

    body = prompts.render_trade("2026-09-18", "trade-1", now=datetime(2026, 9, 18, 15, 0))
    assert "15:00" in body and "{{TIME}}" not in body and "{{OWNER}}" not in body
    assert "live.json" in body and "trades_placed" in body
    assert "Exits before entries" in body


def test_trade_pass_gets_the_research_tools_the_brief_does_not(tmp_path):
    """A pass that cannot screen cannot find anything, which is how the sandbox sat in cash: give it the
    scanners and indicators, but nothing that writes to the broker account."""
    a = RobinhoodAdapter()
    gate_file = tmp_path / "settings.headless.json"
    gate_file.write_text("{}", encoding="utf-8")
    args = claude_cli.stage_trade_args(a, model="opus", budget_usd=6.0, mcp_config=Path("mcp.json"),
                                       settings_file=gate_file, system_prompt=Path("sys.md"), trade_enabled=True)
    allow = args[args.index("--allowedTools") + 1].split(",")
    for tool in ("run_scan", "get_scans", "get_equity_technical_indicators", "get_equity_analyst_ratings",
                 "get_earnings_results", "get_realized_pnl"):
        assert PREFIX + tool in allow, tool
    # scan creation writes to the broker account and the gate does not cover it
    for tool in ("create_scan", "update_scan_filters", "add_to_watchlist"):
        assert PREFIX + tool not in allow, tool
    # the brief's Stage C stays as narrow as it was
    assert PREFIX + "run_scan" not in a.readonly_tools_stage_c()


def test_exits_only_pass_keeps_selling_but_loses_the_research_tools(tmp_path):
    a = RobinhoodAdapter()
    gate_file = tmp_path / "settings.headless.json"
    gate_file.write_text("{}", encoding="utf-8")
    args = claude_cli.stage_trade_args(a, model="opus", budget_usd=0.75, mcp_config=Path("mcp.json"),
                                       settings_file=gate_file, system_prompt=Path("sys.md"), trade_enabled=True,
                                       exits_only=True)
    allow = args[args.index("--allowedTools") + 1].split(",")
    # honouring a stop means selling, so the order tools stay; the gate is what refuses the buys
    assert PLACE in allow and REVIEW in allow
    assert PREFIX + "run_scan" not in allow and PREFIX + "get_equity_technical_indicators" not in allow
    assert PREFIX + "get_equity_quotes" in allow


def test_exits_pass_renders_its_own_prompt(initialized_home: Path):
    from focos.brief import prompts

    body = prompts.render_trade("2026-09-18", "trade-1", now=datetime(2026, 9, 18, 12, 45), exits_only=True)
    assert "exits-only" in body and "{{TIME}}" not in body
    assert "12:45" in body
    # it must not go looking for anything
    assert "run_scan" not in body and "shortlist" not in body


def test_pass_marker_tells_the_gate_which_pass_is_running(initialized_home: Path):
    from focos.sandbox import gate
    from focos.sandbox import state as sb_state

    now = datetime(2026, 9, 18, 12, 45, tzinfo=ET)
    assert gate._pass_kind(now) == "trade"          # no marker: an ordinary pass
    sb_state.start_pass("exits", "trade-2026-09-18-124500")
    assert gate._pass_kind(datetime.now(ET)) == "exits"
    sb_state.end_pass()
    assert gate._pass_kind(datetime.now(ET)) == "trade"
    # a marker left behind by a crashed pass must not mute tomorrow's buys
    sb_state.start_pass("exits", "stale")
    stale = settings.read_json(sb_state.pass_file(), {})
    stale["started_at"] = "2026-09-18T12:45:00+00:00"
    settings.write_json(sb_state.pass_file(), stale)
    assert gate._pass_kind(datetime.now(ET)) == "trade"


def test_trade_tools_are_refused_without_the_gate(tmp_path):
    """Granting place_equity_order without the PreToolUse hook would put real orders on an unchecked path."""
    a = RobinhoodAdapter()
    with pytest.raises(claude_cli.MissingGate):
        claude_cli.stage_trade_args(a, model="sonnet", budget_usd=2.0, mcp_config=Path("mcp.json"),
                                    settings_file=tmp_path / "absent.json", system_prompt=Path("sys.md"),
                                    trade_enabled=True)
    # with trade tools off there is nothing to guard, so a missing settings file is merely unfortunate
    args = claude_cli.stage_trade_args(a, model="sonnet", budget_usd=2.0, mcp_config=Path("mcp.json"),
                                       settings_file=tmp_path / "absent.json", system_prompt=Path("sys.md"),
                                       trade_enabled=False)
    assert PLACE in args[args.index("--disallowedTools") + 1].split(",")
