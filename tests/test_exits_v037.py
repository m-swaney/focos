"""0.3.7: exits always go through, stops are enforced in code and rest at the broker, and failures are loud.

The regression cases have the shape of the orders the 0.3.6 gate refused while a position sat below its stop:
an exit carrying a proposal without entry fields, and an exit re-sending its entry's ref_id.
"""
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from focos import notify, paths, settings
from focos.sandbox import exits, journal, performance, rules

ET = ZoneInfo("America/New_York")
ACCT = "90003333"
RULES = {"warmup_runs": 10, "require_approval_first_n": 0, "budget_usd": 1000, "max_position_weight": 0.40,
         "max_order_usd": 500, "weekly_budget_usd": 2500, "cash_floor_pct": 0.0, "max_orders_per_run": 3,
         "max_orders_per_week": 10, "min_price": 5.0, "blocklist_patterns": [], "market_orders_only_during_rth": True,
         "max_drawdown_pct": 0.5}
BUY_PROP = {"ref_id": "buy-1", "date": "2026-09-22", "symbol": "BIOX", "side": "buy", "thesis": "t", "exit_plan": "e",
            "stop_loss": 38.0, "target": 50.0, "horizon_days": 15, "paper": False}


def ctx(**over):
    base = {"tool": "place", "now": datetime(2026, 9, 29, 12, 45, tzinfo=ET), "killed": False, "mode": "live",
            "run_count": 28, "live_orders": 3, "agentic_account_number": ACCT, "equity": 1000.00, "cash": 120.00,
            "positions": {"BIOX": {"value": 350.00, "quantity": 11.0, "sellable": 11.0},
                          "CHIP": {"value": 345.00, "quantity": 3.0, "sellable": 3.0}},
            "prices": {"BIOX": 31.50, "CHIP": 115.00},
            "orders_this_run": 0, "orders_this_week": 10, "buy_notional_this_week": 0.0, "proposal": None,
            "approved": False, "used_ref_ids": {"buy-1": "buy BIOX on 2026-09-22"}}
    base.update(over)
    return base


def sell(**over):
    o = {"account_number": ACCT, "symbol": "BIOX", "side": "sell", "type": "limit", "quantity": "11",
         "limit_price": "31.40", "time_in_force": "gfd", "market_hours": "regular_hours", "ref_id": "exit-1"}
    o.update(over)
    return o


# ---------------------------------------------------------------- the gate
def test_exit_with_its_own_sell_proposal_passes():
    """0.3.6 refused this for "missing stop_loss / horizon_days" -- entry fields demanded of an exit."""
    prop = {"ref_id": "exit-1", "symbol": "BIOX", "side": "sell", "thesis": "stop exit", "exit_plan": "full exit",
            "stop_loss": None, "horizon_days": 0}
    v = rules.validate(sell(), ctx(proposal=prop), RULES)
    assert v.ok, v.reasons
    assert v.exit


def test_exit_reusing_the_entry_ref_id_is_refused_with_a_fixable_reason():
    """0.3.6: the pass sent the entry's ref_id. The broker de-duplicates on it, so even an allowed order
    would have come back as the old buy. The gate now says exactly that, and marks it correctable."""
    v = rules.validate(sell(ref_id="buy-1"), ctx(proposal=BUY_PROP), RULES)
    assert not v.ok
    assert any("already used" in r and "fresh UUID" in r for r in v.reasons)
    assert v.exit and v.correctable


def test_exit_needs_no_proposal_and_ignores_entry_limits():
    """A sell of a held position clears frequency caps, the price floor and the drawdown halt."""
    v = rules.validate(sell(type="market", limit_price=None),
                       ctx(orders_this_week=99, orders_this_run=99, equity=100.0, cash=0.0,
                           prices={"BIOX": 3.10}), RULES)
    assert v.ok, v.reasons


def test_kill_switch_and_wrong_account_still_stop_an_exit():
    assert not rules.validate(sell(), ctx(killed=True), RULES).ok
    v = rules.validate(sell(account_number="1234"), ctx(), RULES)
    assert any("Agentic" in r for r in v.reasons) and v.correctable


def test_resting_stop_orders_are_sells_only_and_may_be_gtc():
    stop = sell(ref_id="stop-1", type="stop_market", limit_price=None, stop_price="112.50", time_in_force="gtc",
                symbol="CHIP", quantity="3")
    v = rules.validate(stop, ctx(), RULES)
    assert v.ok, v.reasons
    assert not rules.validate({**stop, "stop_price": None}, ctx(), RULES).ok
    buy_stop = {**stop, "side": "buy"}
    assert any("protective sells only" in r for r in rules.validate(buy_stop, ctx(), RULES).reasons)
    gtc_buy = {"account_number": ACCT, "symbol": "CHIP", "side": "buy", "type": "limit", "quantity": "1",
               "limit_price": "116", "time_in_force": "gtc", "ref_id": "b2"}
    assert any("gtc is for resting sell" in r for r in rules.validate(gtc_buy, ctx(orders_this_week=0), RULES).reasons)


def test_buys_still_face_every_limit():
    prop = {"ref_id": "b1", "symbol": "NEWCO", "side": "buy", "thesis": "t", "exit_plan": "e", "stop_loss": 220,
            "horizon_days": 10}
    buy = {"account_number": ACCT, "symbol": "NEWCO", "side": "buy", "type": "limit", "quantity": "1",
           "limit_price": "238", "ref_id": "b1"}
    v = rules.validate(buy, ctx(proposal=prop), RULES)
    assert any("per week" in r for r in v.reasons)          # the weekly buy count is used up
    assert any("available cash" in r for r in v.reasons)    # not enough cash
    assert not v.correctable
    bad_stop = {**prop, "stop_loss": 240}
    v2 = rules.validate(buy, ctx(proposal=bad_stop, orders_this_week=0, cash=500.0), RULES)
    assert any("not below the entry" in r for r in v2.reasons)


def test_cancel_is_guarded():
    c = {"account_number": ACCT, "order_id": "abc"}
    assert rules.validate(c, ctx(tool="cancel"), RULES).ok
    assert not rules.validate({**c, "account_number": "1"}, ctx(tool="cancel"), RULES).ok
    assert not rules.validate({"account_number": ACCT}, ctx(tool="cancel"), RULES).ok
    assert not rules.validate(c, ctx(tool="cancel", mode="paper"), RULES).ok


def test_refusal_message_tells_an_exit_to_fix_and_resend():
    from focos.sandbox import gate

    v = rules.validate(sell(ref_id="buy-1"), ctx(proposal=BUY_PROP), RULES)
    msg = gate.refusal_message(v)
    assert "send it again in this pass" in msg and "must go through" in msg
    buy = rules.Verdict(ok=False, reasons=["notional 900.00 exceeds max_order_usd 500.00"], side="buy")
    assert "Do not retry" in gate.refusal_message(buy)


# ---------------------------------------------------------------- the exit plan
def _write(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj), encoding="utf-8")


def _view(**over):
    v = {"asof": "2026-09-30T14:30:00+00:00", "last4": "3333",
         "positions": [{"symbol": "BIOX", "quantity": 11, "sellable": 11, "price": 31.6, "avg_cost": 41.1},
                       {"symbol": "CHIP", "quantity": 3, "sellable": 0, "price": 116.5, "avg_cost": 122.5},
                       {"symbol": "MUSC", "quantity": 2, "sellable": 2, "price": 130.7, "avg_cost": 127.2},
                       {"symbol": "XYZ", "quantity": 1, "sellable": 1, "price": 10.0, "avg_cost": 9.0}],
         "quotes": {}, "open_orders": [{"id": "stop-intc", "symbol": "CHIP", "side": "sell", "type": "stop_market",
                                        "stop_price": 112.5, "quantity": 3}]}
    v.update(over)
    return v


def _seed(home: Path):
    paths.ensure_dirs()
    _write(paths.PROPOSALS / "2026-09-22-BIOX-buy.json", BUY_PROP)
    _write(paths.PROPOSALS / "2026-09-22-CHIP-buy.json", {**BUY_PROP, "ref_id": "buy-2", "symbol": "CHIP",
                                                          "stop_loss": 112.5, "target": 145})
    _write(paths.PROPOSALS / "2026-09-24-MUSC-buy.json", {**BUY_PROP, "ref_id": "buy-3", "symbol": "MUSC", "date": "2026-09-24",
                                                       "stop_loss": 118.3, "target": 150})
    with journal.orders_file().open("w", encoding="utf-8") as f:
        for ref, sym in (("buy-1", "BIOX"), ("buy-2", "CHIP"), ("buy-3", "MUSC")):
            f.write(json.dumps({"ts": "2026-09-22T15:01:35-04:00", "ok": True,
                                "order": {"symbol": sym, "side": "buy", "type": "limit", "quantity": "1",
                                          "limit_price": "10", "ref_id": ref}}) + "\n")


def test_plan_requires_the_breached_exit_and_protects_the_rest(initialized_home: Path):
    _seed(initialized_home)
    plan = exits.build(_view(), today="2026-09-30")
    assert [e["symbol"] for e in plan["required_exits"]] == ["BIOX"]
    order = plan["required_exits"][0]["order"]
    assert order["type"] == "market" and order["quantity"] == "11" and order["ref_id"] != "buy-1"
    # the exit's proposal file was written with the same fresh ref_id, so the gate can match it
    prop = json.loads((paths.PROPOSALS / "2026-09-30-BIOX-sell-stop.json").read_text(encoding="utf-8"))
    assert prop["ref_id"] == order["ref_id"] and prop["side"] == "sell" and prop["exit_of"] == "buy-1"
    # CHIP already has a resting stop; P does not; XYZ has no plan at all
    assert [s["symbol"] for s in plan["missing_stops"]] == ["MUSC"]
    assert plan["missing_stops"][0]["order"]["type"] == "stop_market"
    assert plan["missing_stops"][0]["order"]["time_in_force"] == "gtc"
    assert plan["unmanaged"] == ["XYZ"]
    # a second pass the same day re-sends the same unspent order instead of inventing a new one
    again = exits.build(_view(), today="2026-09-30")
    assert again["required_exits"][0]["order"]["ref_id"] == order["ref_id"]
    block = exits.prompt_block(plan)
    assert "Required exits" in block and order["ref_id"] in block


def test_verify_reads_the_journal_not_the_model(initialized_home: Path):
    _seed(initialized_home)
    plan = exits.build(_view(), today="2026-09-30")
    assert exits.verify(plan)["exits_missed"] == ["BIOX"]
    with journal.orders_file().open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": "2026-09-30T10:31:00-04:00", "ok": True,
                            "order": plan["required_exits"][0]["order"]}) + "\n")
    check = exits.verify(plan)
    assert check["exits_done"] == ["BIOX"] and check["exits_missed"] == []
    assert check["stops_missed"] == ["MUSC"]


# ---------------------------------------------------------------- scorecard, alerts, notifications
def test_resting_stops_are_not_fills_and_broker_fills_win(initialized_home: Path):
    paths.ensure_dirs()
    with journal.orders_file().open("w", encoding="utf-8") as f:
        f.write(json.dumps({"ts": "2026-09-22T10:31:00-04:00", "ok": True, "order": {
            "symbol": "CHIP", "side": "buy", "type": "limit", "quantity": "3", "limit_price": "122.50", "ref_id": "a"}}) + "\n")
        f.write(json.dumps({"ts": "2026-09-22T10:40:00-04:00", "ok": True, "order": {
            "symbol": "CHIP", "side": "sell", "type": "stop_market", "quantity": "3", "stop_price": "112.50", "ref_id": "b"}}) + "\n")
    fills = performance._fills([])
    assert [(f["side"], f["symbol"]) for f in fills] == [("buy", "CHIP")]
    n = performance.record_fills([
        {"id": "o1", "symbol": "CHIP", "side": "buy", "state": "filled", "quantity": 3, "average_price": 122.49,
         "created_at": "2026-09-22T14:31:00Z"},
        {"id": "o2", "symbol": "CHIP", "side": "sell", "state": "filled", "cumulative_quantity": 3,
         "average_price": 112.40, "last_transaction_at": "2026-09-30T13:31:00Z"},
        {"id": "o3", "symbol": "CHIP", "side": "sell", "state": "cancelled", "quantity": 3},
    ])
    assert n == 2 and performance.record_fills([{"id": "o1", "symbol": "CHIP", "side": "buy", "state": "filled",
                                                 "quantity": 3, "average_price": 122.49}]) == 0
    closed, open_lots = performance._match(performance._fills([]))
    assert len(closed) == 1 and not open_lots and round(closed[0]["pnl_usd"], 2) == -30.27


def test_feed_and_decision_alerts(initialized_home: Path):
    from focos.run import attention

    a = attention.feed_alerts({"pull": {"errors": ["Connection to Example Bank may need attention. Auth required"]}})
    assert a and a[0]["code"] == "feed_auth" and "Example Bank" in a[0]["text"]
    paths.DECISIONS.parent.mkdir(parents=True, exist_ok=True)
    paths.DECISIONS.write_text("\n".join(json.dumps(r) for r in [
        {"id": "decision_4", "date": "2026-09-13", "kind": "recommendation", "text": "redirect DCA"},
        {"id": "decision_8", "date": "2026-09-17", "kind": "recommendation", "text": "renew login"},
        {"date": "2026-09-22", "kind": "resolution", "ref": "decision_8", "status": "acted"},
        {"id": "decision_13", "date": "2026-09-27", "kind": "recommendation", "text": "too new"},
    ]) + "\n", encoding="utf-8")
    d = attention.decision_alerts("2026-09-29")
    assert d and d[0]["data"]["ids"] == ["decision_4"]


def test_issues_are_pushed_once_then_weekly(initialized_home: Path, _no_real_notifications):
    alert = {"severity": "warn", "code": "feed_auth", "text": "Example Bank needs you"}
    notify.sync_issues([alert], "2026-09-14")
    notify.sync_issues([alert], "2026-09-15")
    assert len(_no_real_notifications) == 1
    issues = notify.sync_issues([alert], "2026-09-21")
    assert len(_no_real_notifications) == 2 and issues["feed_auth"]["days_open"] == 7
    # a condition that clears drops out, and returning starts the clock again
    notify.sync_issues([], "2026-09-22")
    assert notify.sync_issues([alert], "2026-09-23")["feed_auth"]["days_open"] == 0


def test_send_dedupes_by_key(initialized_home: Path, _no_real_notifications):
    notify.send("t", "b", "critical", key="k1")
    notify.send("t", "b", "critical", key="k1")
    assert len(_no_real_notifications) == 1
    assert "toast" in notify.toast_xml("a & b", "<c>") and "&amp;" in notify.toast_xml("a & b", "<c>")


def test_auto_update_waits_for_a_run_in_flight(initialized_home: Path, monkeypatch):
    from focos import updater
    from focos.run import status

    monkeypatch.setattr(updater, "is_dev_checkout", lambda app=None: False)
    status.start("trade", "trade-x")
    assert "in flight" in updater.auto_update()["skipped"]
    status.finish("trade", True)
    monkeypatch.setattr(updater, "check", lambda repo=None: {"current": "0.3.7", "available": "v0.3.7", "newer": False})
    assert updater.auto_update()["updated"] is False


# ---------------------------------------------------------------- the pass end to end
def _pass_setup(home: Path, monkeypatch):
    import yaml

    from focos.orchestrator import trade
    from focos.sandbox import live
    from focos.sandbox import state as sb_state

    (home / "config" / "focos.yml").write_text(yaml.safe_dump({"agent": {"sandbox_enabled": True}}))
    settings.reset()
    _seed(home)
    monkeypatch.setattr(trade, "market_now", lambda: datetime(2026, 9, 30, 10, 30, tzinfo=ET))
    monkeypatch.setattr(sb_state, "trading_enabled", lambda: True)

    def fake_capture(date, run_id):
        return live.write(_view())

    monkeypatch.setattr(trade, "capture_live", fake_capture)
    return trade


def test_a_pass_that_skips_a_required_exit_fails_loudly(initialized_home: Path, monkeypatch, _no_real_notifications):
    trade = _pass_setup(initialized_home, monkeypatch)
    seen = {}

    def fake_run(prompt, args, **k):
        seen["prompt"] = prompt
        return {"result": '```json\n{"summary_line": "no action", "proposals": [], "trades_placed": []}\n```',
                "is_error": False, "subtype": "success"}

    monkeypatch.setattr(trade.claude_cli, "run", fake_run)
    res = trade.run_pass(date="2026-09-30")
    assert "Required exits" in seen["prompt"] and "BIOX" in seen["prompt"]
    assert not res.ok
    from focos.run import status
    st = status.get()["trade"]
    assert st["ok"] is False and "BIOX" in (st["error"] or "")
    assert any("stop exit did not go through" in n["title"] for n in _no_real_notifications)


def test_a_pass_that_sends_the_exit_passes(initialized_home: Path, monkeypatch, _no_real_notifications):
    trade = _pass_setup(initialized_home, monkeypatch)

    def fake_run(prompt, args, **k):
        plan = json.loads(exits.plan_file().read_text(encoding="utf-8"))
        with journal.orders_file().open("a", encoding="utf-8") as f:
            for o in [plan["required_exits"][0]["order"], plan["missing_stops"][0]["order"]]:
                f.write(json.dumps({"ts": datetime.now(settings.tz()).isoformat(timespec="seconds"), "ok": True,
                                    "order": o}) + "\n")
        return {"result": '```json\n{"summary_line": "sold BIOX", "proposals": [], "trades_placed": ["BIOX"]}\n```',
                "is_error": False, "subtype": "success"}

    monkeypatch.setattr(trade.claude_cli, "run", fake_run)
    res = trade.run_pass(date="2026-09-30")
    assert res.ok, res.stages
    assert "missed -" in res.stages["V"]
    assert any("2 order(s)" in n["title"] for n in _no_real_notifications)


def test_asset_update_records_a_vehicle(initialized_home: Path, monkeypatch):
    from focos.ledger import properties, providers
    from focos.updates import apply as upd_apply

    monkeypatch.setattr(providers, "current", lambda: None)
    recs = upd_apply.apply([{"target": "asset", "op": "add", "id": "truck", "name": "2019 Example Pickup",
                             "kind": "vehicle", "value": 25000, "entity": "personal", "reason": "note"}],
                           actor="model", run="daily-x", date="2026-09-30")
    assert recs[0]["ok"], recs[0]
    p = next(p for p in properties.load() if p["key"] == "truck")
    assert p["kind"] == "vehicle" and p["manual_value"] == 25000 and p["source"] == "manual"
    bad = upd_apply.apply([{"target": "asset", "op": "add", "id": "x", "value": 5}], actor="model", run="r")
    assert not bad[0]["ok"] and "name" in bad[0]["error"]
