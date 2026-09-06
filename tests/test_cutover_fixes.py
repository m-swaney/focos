"""Found during the first real cutover: Bridge's range-capped notice is not a failure, and the retired ledger's
account types must carry onto the live accounts it is aliased to."""
import json
from datetime import date
from pathlib import Path

from focos import settings
from focos.ledger.legacy import link
from focos.ledger.legacy import sure_dump as sd
from focos.ledger.providers import simplefin as sf
from focos.ledger.providers.base import LedgerAccount
from focos.ledger.providers.sqlite_store import SQLiteStore

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "simplefin_accounts.json").read_text(encoding="utf-8"))
DUMP = Path(__file__).parent / "fixtures" / "sure_dump.sql"


def test_capped_range_notice_is_a_warning_not_a_failure(initialized_home, tmp_path):
    payload = json.loads(json.dumps(FIXTURE))
    payload["errors"] = ["Requested date range exceeds limit of 90 days and was capped."]
    p = sf.SimpleFINProvider(store=SQLiteStore(tmp_path / "l.sqlite"), fetcher=lambda s, e, bo: payload,
                             access_url="https://u:p@bridge.simplefin.org/simplefin", feeds=[])
    res = p.refresh(date(2026, 3, 2), force=True)
    assert res.ok and res.errors == [] and "capped" in res.warnings[0]
    assert p.health().ok is True and p.sync_status().last_error is None
    payload["errors"] = ["Connection to Example Bank failed"]
    res = p.refresh(date(2026, 3, 3), force=True)
    assert res.errors == ["Connection to Example Bank failed"] and res.warnings == []


def test_apply_carries_legacy_types_onto_live_accounts(initialized_home, tmp_path):
    store = SQLiteStore(tmp_path / "l.sqlite")
    sd.import_dump(DUMP, store)
    # the feed only sees a masked name, so it infers "checking" for what Sure knew was a credit card
    store.upsert_account(LedgerAccount(id="simplefin:ACT-CARD-1", provider="simplefin", name="******1234 (1234)", institution_name="Example Card",
                                       account_type="depository", subtype="checking", classification="asset", balance=-410.55))
    store.upsert_balance("simplefin:ACT-CARD-1", "2026-01-10", -410.55)
    store.record_pull("simplefin", "2026-01-03", "2026-01-10", 1, 0, [])
    res = link.apply(store, [{"live": "simplefin:ACT-CARD-1", "legacy": "sure:acc-card", "how": "manual", "score": 9.0}], sf.PRIMARY_PROVIDERS)
    assert res["types_carried"] == [{"id": "simplefin:ACT-CARD-1", "name": "******1234 (1234)", "from": "depository", "to": "credit_card"}]
    acct = next(a for a in store.accounts(providers=("simplefin",)))
    assert (acct.account_type, acct.subtype, acct.classification) == ("credit_card", None, "liability")
    assert settings.entities_v2()["account_types"]["simplefin:ACT-CARD-1"]["classification"] == "liability"
    # idempotent, and confirmed types in entities.yml are never overridden
    assert link.apply(store, [], sf.PRIMARY_PROVIDERS)["types_carried"] == []


def test_crypto_code_aliases_normalized():
    from focos.holdings.robinhood_mcp import normalize_crypto_keys

    payload = {"accounts": [{"crypto_positions": [{"asset": "btc", "quantity": 0.5}, {"code": "ETH", "quantity": 1}, {"symbol": "SOL", "quantity": 2}]}]}
    normalize_crypto_keys(payload)
    assert [p["code"] for p in payload["accounts"][0]["crypto_positions"]] == ["BTC", "ETH", "SOL"]
    normalize_crypto_keys({"accounts": [{"crypto_positions": None}]})  # tolerant of missing lists


def test_missing_quotes_degrades_instead_of_failing():
    from focos.holdings.robinhood_mcp import ensure_quotes
    from focos.sources import robinhood_snapshot as rh

    payload = {"accounts": [], "notes": ["get_equity_quotes: batch of 21 exceeded the limit"]}
    ensure_quotes(payload)
    assert payload["quotes"] == [] and payload["notes"].startswith("get_equity_quotes") and "quotes missing" in payload["notes"]
    assert rh.validate(payload) == []
    p2 = {"accounts": [], "notes": "x"}
    ensure_quotes(p2)
    assert p2["quotes"] == [] and p2["notes"].startswith("x; ")


def test_news_keyed_by_symbol_is_flattened():
    from focos.holdings.robinhood_mcp import normalize_snapshot
    from focos.sources import robinhood_snapshot as rh

    payload = {"accounts": [], "quotes": [], "notes": ["a", "b"],
               "news": {"NVDA": [{"title": "t1", "publisher": "Benzinga"}, {"title": "t2"}], "SPY": {"title": "t3"}},
               "earnings": {"NVDA": [{"date": "2026-09-10"}]}}
    normalize_snapshot(payload)
    assert rh.validate(payload) == []
    assert [n["symbol"] for n in payload["news"]] == ["NVDA", "NVDA", "SPY"] and payload["news"][0]["source"] == "Benzinga"
    assert payload["earnings"] == [{"symbol": "NVDA", "date": "2026-09-10"}] and payload["notes"] == "a; b"


def test_snapshot_prompt_includes_schema(initialized_home):
    from focos.brief import prompts

    text = prompts.render("snapshot", "2026-03-01", run_mode="daily")
    assert '"title": "RobinhoodSnapshot"' in text and text.rstrip().endswith("before or after.")


def test_push_reports_instead_of_raising(initialized_home, monkeypatch):
    from focos.orchestrator import git_ops

    (initialized_home / "state" / "x.json").write_text("{}", encoding="utf-8")
    assert git_ops.commit_run(initialized_home, "t", ("state",), push=True)
    assert git_ops.last_push == {"ok": False, "method": None, "error": "no origin remote"}
    # a remote that cannot be reached: system git fails, dulwich fails, the commit still stands
    from dulwich import porcelain
    porcelain.remote_add(str(initialized_home), "origin", "https://127.0.0.1:9/nobody/nothing.git")
    monkeypatch.setattr(git_ops.shutil, "which", lambda _: None)
    res = git_ops.push_origin(initialized_home, timeout=5)
    assert res["ok"] is False and "git not installed" in res["error"] and "dulwich:" in res["error"]
