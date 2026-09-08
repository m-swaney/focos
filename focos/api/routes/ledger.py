from __future__ import annotations

from datetime import date as _date

from fastapi import APIRouter
from pydantic import BaseModel

from ... import settings
from ...config import seed_rules, writer
from ...config.models import HOUSEHOLD
from ...ledger import entities as ent
from ...ledger import providers
from ...ledger.providers.base import ManualAccountSpec

router = APIRouter(prefix="/ledger")


def _store():
    from ... import paths
    from ...ledger.providers.sqlite_store import SQLiteStore

    return SQLiteStore(paths.LEDGER_DB) if paths.LEDGER_DB.exists() else None


@router.get("/categories")
def categories(days: int = 90):
    from datetime import timedelta

    from ...ledger import categories as cats

    store = _store()
    counts = store.category_counts((_date.today() - timedelta(days=days)).isoformat()) if store else {}
    if store:
        store.close()
    return {"categories": list(cats.CATEGORIES), "core": sorted(cats.CORE), "discretionary": sorted(cats.DISCRETIONARY),
            "definitions": cats.DEFINITIONS, "counts": counts}


@router.get("/merchants")
def merchants(uncategorized: int = 1, n: int = 50, days: int = 95):
    from datetime import timedelta

    store = _store()
    if store is None:
        return {"merchants": []}
    try:
        if uncategorized:
            rows = store.uncategorized_merchants((_date.today() - timedelta(days=days)).isoformat(), _date.today().isoformat(), limit=n)
        else:
            rows = list(store.merchant_rules().values())[:n]
    finally:
        store.close()
    return {"merchants": rows}


class Rule(BaseModel):
    merchant_key: str
    category: str


@router.post("/categories/rule")
def set_rule(body: Rule):
    from ...updates import apply as apply_mod

    changes = apply_mod.apply([{"target": "merchant_rule", "id": body.merchant_key.strip().upper(), "category": body.category,
                               "reason": "dashboard"}], actor="user", run="dashboard", date=_date.today().isoformat())
    c = changes[0]
    return {"ok": c["ok"], "error": c.get("error"), "change": dict(c, summary=apply_mod.describe(c))}


def _accounts_payload():
    p = providers.current()
    if p is None:
        return {"provider": None, "accounts": []}
    rows = [a.as_row() for a in p.accounts()]
    entity_of = ent.account_entity_map(accounts=rows)
    br = {(a.get("match") or {}).get("ledger_account_id") or a.get("ledger_account_id"): a for a in settings.brokerage()}
    return {"provider": p.name, "health": p.health().model_dump(),
            "accounts": [{**r, "entity": entity_of.get(r["id"]), "brokerage": br.get(r["id"])} for r in rows],
            "entities": settings.entities_v2().get("entities")}


class Claim(BaseModel):
    setup_token: str


@router.post("/simplefin/claim")
def simplefin_claim(body: Claim):
    from ...ledger.providers.simplefin import ENV_ACCESS_URL, SimpleFINClient, SimpleFINProvider

    access = SimpleFINClient.claim(body.setup_token)
    writer.set_env(ENV_ACCESS_URL, access)
    ledger = dict(settings.focos().get("ledger") or {})
    ledger["provider"] = "simplefin"
    writer.write_section("focos.yml", "ledger", ledger)
    res = SimpleFINProvider(access_url=access).refresh(_date.today(), force=True)
    return {"ok": res.ok, "pull": res.model_dump(), **_accounts_payload()}


class MercuryConfigure(BaseModel):
    token: str


@router.post("/mercury/configure")
def mercury_configure(body: MercuryConfigure):
    """Direct Mercury feed for business accounts SimpleFIN does not carry. Validates the token before saving."""
    from ... import paths
    from ...ledger.feeds.mercury import ENV_TOKEN, MercuryClient, MercuryFeed
    from ...ledger.providers.sqlite_store import SQLiteStore

    token = body.token.strip()
    try:
        n = len(MercuryClient(token).accounts())
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:300]}
    writer.set_env(ENV_TOKEN, token)
    ledger = dict(settings.focos().get("ledger") or {})
    if ledger.get("provider") != "simplefin":
        ledger["provider"] = "simplefin"
    ledger["mercury"] = {"enabled": True}
    writer.write_section("focos.yml", "ledger", ledger)
    settings.reset()
    res = MercuryFeed(SQLiteStore(paths.LEDGER_DB), token=token).pull(_date.today(), force=True)
    return {"ok": res.ok, "mercury_accounts": n, "pull": res.model_dump(), **_accounts_payload()}


class SetProvider(BaseModel):
    provider: str  # simplefin | none


@router.post("/provider")
def set_provider(body: SetProvider):
    ledger = dict(settings.focos().get("ledger") or {})
    ledger["provider"] = body.provider
    issues = writer.write_section("focos.yml", "ledger", ledger)
    return {"ok": not issues, "issues": [i.as_dict() for i in issues]}


@router.get("/accounts")
def accounts():
    return _accounts_payload()


@router.post("/refresh")
def refresh(force: bool = True):
    p = providers.current()
    if p is None:
        return {"ok": False, "error": "no ledger provider"}
    return {"ok": True, "refresh": p.refresh(_date.today(), force=force).model_dump(), **_accounts_payload()}


class EntityIn(BaseModel):
    key: str
    label: str
    kind: str = "business"


class AccountAssign(BaseModel):
    id: str
    entity: str = HOUSEHOLD
    type: str | None = None           # depository | credit_card | loan | investment | property | vehicle | other
    subtype: str | None = None
    classification: str | None = None
    ignore: bool = False
    brokerage_key: str | None = None  # set to analyze holdings of this account
    brokerage_label: str | None = None
    brokerage_role: str | None = None


class Assign(BaseModel):
    entities: list[EntityIn] = []
    accounts: list[AccountAssign]
    seed_transfer_rules: bool = True


@router.post("/assign")
def assign(body: Assign):
    ents_doc = settings.entities_v2()
    ents = ents_doc.get("entities") or {}
    ents.setdefault(HOUSEHOLD, {"label": "Personal", "kind": "household", "account_ids": []})
    for e in body.entities:
        cur = ents.get(e.key) or {"account_ids": []}
        ents[e.key] = {**cur, "label": e.label, "kind": e.kind}
    for e in ents.values():
        e["account_ids"] = [i for i in (e.get("account_ids") or []) if i not in {a.id for a in body.accounts}]
    types = dict(ents_doc.get("account_types") or {})
    brokerage = [a for a in settings.brokerage() if a.get("ledger_account_id") not in {x.id for x in body.accounts}]
    for a in body.accounts:
        if a.ignore:
            continue
        target = a.entity if a.entity in ents else HOUSEHOLD
        ents[target].setdefault("account_ids", []).append(a.id)
        if a.type:
            types[a.id] = {"type": a.type, "subtype": a.subtype,
                           "classification": a.classification or ("liability" if a.type in ("credit_card", "loan") else "asset")}
        if a.brokerage_key:
            brokerage.append({"key": a.brokerage_key, "label": a.brokerage_label or a.brokerage_key, "role": a.brokerage_role or "taxable",
                              "entity": target, "source": "simplefin_holdings", "match": {"ledger_account_id": a.id},
                              "ledger_account_id": a.id})
    issues = writer.write_file("entities.yml", {"version": 2, "entities": ents, "corridors": ents_doc.get("corridors") or [],
                                                "account_types": types})
    issues += writer.write_file("accounts.yml", {"version": 2, "brokerage": brokerage})
    if issues:
        return {"ok": False, "issues": [i.as_dict() for i in issues]}
    if brokerage and (settings.focos().get("holdings") or {}).get("source") == "none":
        writer.write_section("focos.yml", "holdings", {"source": "simplefin_holdings"})
    seeded = None
    if body.seed_transfer_rules and not (settings.transfer_rules().get("rules") or []):
        p = providers.current()
        rows = [x.as_row() for x in p.accounts()] if p else []
        entity_of = ent.account_entity_map(accounts=rows)
        seeded = seed_rules.seed(rows, entity_of, settings.entities_v2())
        writer.write_file("transfer_rules.yml", seeded)
    return {"ok": True, "seeded_rules": len((seeded or {}).get("rules") or []), **_accounts_payload()}


class ManualIn(BaseModel):
    key: str
    name: str
    entity: str = HOUSEHOLD
    account_type: str = "other"
    subtype: str | None = None
    classification: str = "asset"
    balance: float = 0.0
    notes: str | None = None


@router.post("/manual-accounts")
def manual_accounts(body: list[ManualIn]):
    p = providers.current()
    if p is None:
        return {"ok": False, "error": "no ledger provider"}
    created = []
    ents = settings.entities_v2()
    for m in body:
        acct = p.upsert_manual_account(ManualAccountSpec(**m.model_dump()))
        created.append(acct.as_row())
        target = ents["entities"].get(m.entity) or ents["entities"][HOUSEHOLD]
        if acct.id not in (target.get("account_ids") or []):
            target.setdefault("account_ids", []).append(acct.id)
    writer.write_file("entities.yml", ents)
    return {"ok": True, "created": created, **_accounts_payload()}
