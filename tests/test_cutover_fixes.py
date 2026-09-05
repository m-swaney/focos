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
