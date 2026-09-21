"""The PreToolUse gate and PostToolUse journal get every broker-specific string from the adapter."""
import io
import json
from pathlib import Path

from focos import paths, settings
from focos.sandbox import gate, journal
from focos.sandbox import state as sb_state
from focos.sandbox.brokers.robinhood import PLACE, REVIEW


def _run(module, payload: dict, monkeypatch) -> int:
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    monkeypatch.setattr("sys.argv", ["hook", "--home", str(paths.HOME)])
    return module.main()


def test_gate_ignores_unrelated_tools(initialized_home: Path, monkeypatch):
    assert _run(gate, {"tool_name": "Read", "tool_input": {}}, monkeypatch) == 0
    assert not (initialized_home / "state" / "sandbox" / "gate_log.jsonl").exists()


def test_gate_blocks_in_paper_mode_and_redacts(initialized_home: Path, monkeypatch):
    order = {"account_number": "90001234", "symbol": "VTI", "side": "buy", "type": "market", "dollar_amount": "50",
             "time_in_force": "gfd", "market_hours": "regular_hours", "ref_id": "x"}
    rc = _run(gate, {"tool_name": PLACE, "tool_input": order, "session_id": "s"}, monkeypatch)
    assert rc == 2
    entries = [json.loads(l) for l in (initialized_home / "state" / "sandbox" / "gate_log.jsonl").read_text().splitlines()]
    assert entries[-1]["tool"] == "place" and entries[-1]["ok"] is False
    assert "account_number" not in entries[-1]["order"] and entries[-1]["order"]["account_last4"] == "1234"
    assert any("paper" in r or "mode" in r for r in entries[-1]["reasons"])
    assert _run(gate, {"tool_name": REVIEW, "tool_input": order}, monkeypatch) == 2


def test_journal_counts_only_successful_places(initialized_home: Path, monkeypatch):
    order = {"account_number": "90001234", "symbol": "VTI", "side": "buy"}
    assert _run(journal, {"tool_name": REVIEW, "tool_input": order, "tool_response": "ok"}, monkeypatch) == 0
    assert not (initialized_home / "state" / "sandbox" / "orders.jsonl").exists()
    _run(journal, {"tool_name": PLACE, "tool_input": order, "tool_response": {"error": "rejected"}}, monkeypatch)
    _run(journal, {"tool_name": PLACE, "tool_input": order, "tool_response": {"id": "o1", "state": "queued"}}, monkeypatch)
    rows = [json.loads(l) for l in (initialized_home / "state" / "sandbox" / "orders.jsonl").read_text().splitlines()]
    assert [r["ok"] for r in rows] == [False, True]
    assert all("account_number" not in r["order"] and r["order"]["account_last4"] == "1234" for r in rows)
    settings.reset()
    assert sb_state.load_mode()["live_orders"] == 1


def test_allowed_tools_extra_from_adapter(initialized_home: Path):
    assert sb_state.allowed_tools_extra() == []
    sb_state.set_mode("live")
    sb_state.save_mode({**sb_state.load_mode(), "run_count": 99})
    assert sb_state.allowed_tools_extra() == [REVIEW, PLACE]


def test_agentic_number_resolves_from_a_trading_pass_raw_read(initialized_home: Path):
    """A pass's own raw read is the newest file in state/raw while it runs, and it is scoped to one account
    rather than carrying the full list. Missing that shape refused every order during a pass."""
    from focos.sandbox.brokers.robinhood import RobinhoodAdapter

    a = RobinhoodAdapter()
    daily = {"accounts": [{"account_number": "90003333", "agentic_allowed": True},
                          {"account_number": "90001111", "agentic_allowed": False}]}
    assert a.sandbox_account_number(daily) == "90003333"
    # the trade snapshot's shape: one account, stated at the top level
    assert a.sandbox_account_number({"account_number": "90003333", "portfolio": {}, "positions": []}) == "90003333"
    assert a.sandbox_account_number({}) is None
    assert a.sandbox_account_number(None) is None
