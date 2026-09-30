"""A loan the feed lost: record the statement number on the feed's own account, let it amortize itself after each
payment, let a returning feed take over, and stop asking the owner to reconnect it meanwhile."""
from pathlib import Path

import pytest

from focos.ledger import manual_balance
from focos.ledger.providers.base import LedgerAccount
from focos.ledger.providers.sqlite_store import SQLiteStore


class P:
    def __init__(self, store):
        self.store = store


@pytest.fixture
def prov(tmp_path: Path):
    store = SQLiteStore(tmp_path / "ledger.sqlite")
    store.upsert_account(LedgerAccount(id="simplefin:ACT-1", provider="simplefin", name="Home Equity Line of Credit",
                                       institution_name="Example Lender", account_type="loan", classification="liability"))
    store.upsert_account(LedgerAccount(id="sure:old-1", provider="sure", name="Example Lender HELOC (imported)",
                                       account_type="loan", classification="liability"))
    store.upsert_account(LedgerAccount(id="simplefin:ACT-2", provider="simplefin", name="Checking",
                                       institution_name="Example Bank", account_type="depository"))
    store.upsert_balance("simplefin:ACT-1", "2026-09-08", -65551.0, balance_ts=1, source="feed")
    return P(store)


def test_statement_balance_lands_on_the_feed_account_as_a_liability(prov):
    out = manual_balance.set_balance("lender", 64574.14, "2026-09-30", provider=prov)
    assert out["account_id"] == "simplefin:ACT-1"                 # the live account, not the imported history
    assert prov.store.latest_balance("simplefin:ACT-1").balance == -64574.14


def test_a_loan_keeps_itself_current_after_each_payment(prov):
    manual_balance.set_balance("simplefin:ACT-1", 64574.14, "2026-09-30", rate_pct=10.3, payment=1550, day=21,
                               provider=prov)
    assert manual_balance.project("2026-10-20", provider=prov) == []           # no payment yet
    wrote = manual_balance.project("2026-11-25", provider=prov)
    assert [w["date"] for w in wrote] == ["2026-10-21", "2026-11-21"]
    first = round(64574.14 + round(64574.14 * 0.103 / 12, 2) - 1550, 2)
    assert wrote[0]["balance"] == -first and wrote[0]["interest"] == 554.26
    assert prov.store.latest_balance("simplefin:ACT-1").date == "2026-11-21"
    assert manual_balance.project("2026-11-25", provider=prov) == []           # idempotent
    # a newer statement resets the projection
    manual_balance.set_balance("simplefin:ACT-1", 62000, "2026-11-30", provider=prov)
    assert prov.store.latest_balance("simplefin:ACT-1").balance == -62000


def test_a_returning_feed_wins(prov):
    manual_balance.set_balance("simplefin:ACT-1", 64574.14, "2026-09-30", rate_pct=10.3, payment=1550, day=21,
                               provider=prov)
    assert manual_balance.tracked_institutions(prov) == {"Example Lender"}
    prov.store.upsert_balance("simplefin:ACT-1", "2026-10-05", -64000.0, balance_ts=2, source="feed")
    assert manual_balance.project("2026-10-25", provider=prov) == []
    assert manual_balance.tracked_institutions(prov) == set()


def test_ambiguous_or_incomplete_requests_are_refused(prov):
    with pytest.raises(ValueError, match="matches 0"):
        manual_balance.set_balance("nobody", 1, provider=prov)
    with pytest.raises(ValueError, match="--rate, --payment, and --day"):
        manual_balance.set_balance("lender", 1, rate_pct=10.3, provider=prov)


def test_no_reconnect_nag_for_an_institution_kept_by_hand():
    from focos.run import attention

    cons = {"pull": {"errors": ["Connection to Example Lender may need attention. Auth required"]}}
    assert attention.feed_alerts(cons)
    assert attention.feed_alerts({**cons, "manually_tracked": ["Example Lender"]}) == []
