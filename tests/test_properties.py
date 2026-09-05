"""Property values land in a manual ledger account mapped to the property's entity (no Zillow, no network)."""
from focos import settings
from focos.ledger import properties
from focos.ledger.providers import simplefin as sf
from focos.ledger.providers.sqlite_store import SQLiteStore


def test_manual_property_gets_ledger_account_and_entity(initialized_home):
    (initialized_home / "config" / "properties.yml").write_text(
        "# header kept\nproperties:\n- key: home\n  name: Primary residence\n  entity: personal\n  source: manual\n  manual_value: 350000\n",
        encoding="utf-8")
    settings.reset()
    store = SQLiteStore(initialized_home / "state" / "ledger.sqlite")
    p = sf.SimpleFINProvider(store=store, access_url="", feeds=[])
    out = properties.refresh("2026-03-01", push=True, provider=p)
    row = out["properties"][0]
    assert out["total_value"] == 350000 and row["pushed"] and row["ledger_account_id"] == "manual:prop_home"
    acct = next(a for a in p.accounts() if a.id == "manual:prop_home")
    assert acct.account_type == "property" and acct.balance == 350000.0 and acct.is_manual
    assert store.balances(__import__("datetime").date(2026, 3, 1), __import__("datetime").date(2026, 3, 1), ["manual:prop_home"])[0].balance == 350000.0
    assert "manual:prop_home" in settings.entities_v2()["entities"]["personal"]["account_ids"]
    text = (initialized_home / "config" / "properties.yml").read_text(encoding="utf-8")
    assert text.startswith("# header kept") and "ledger_account_id: manual:prop_home" in text
    properties.refresh("2026-03-02", push=True, provider=p)  # idempotent
    assert len([a for a in p.accounts() if a.account_type == "property"]) == 1
    assert (initialized_home / "state" / "derived" / "latest" / "properties.json").exists()


def test_refresh_without_provider_only_computes(initialized_home):
    (initialized_home / "config" / "properties.yml").write_text("properties:\n- key: cabin\n  name: Cabin\n  source: manual\n  manual_value: 90000\n", encoding="utf-8")
    settings.reset()
    out = properties.refresh("2026-03-01", push=False)
    assert out["total_value"] == 90000 and "pushed" not in out["properties"][0] and out["properties"][0]["ledger_account_id"] is None
