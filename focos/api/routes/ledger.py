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


class SureConfigure(BaseModel):
    api_url: str = "http://127.0.0.1:3000"
    api_key_rw: str | None = None
    api_key_ro: str | None = None


@router.post("/sure/configure")
def sure_configure(body: SureConfigure):
    writer.set_env("SURE_API_URL", body.api_url.strip())
    if body.api_key_rw:
        writer.set_env("SURE_API_KEY_RW", body.api_key_rw.strip())
    if body.api_key_ro:
        writer.set_env("SURE_API_KEY_RO", body.api_key_ro.strip())
    ledger = dict(settings.focos().get("ledger") or {})
    ledger["provider"] = "sure"
    ledger.setdefault("sure", {})["api_url"] = body.api_url.strip()
    writer.write_section("focos.yml", "ledger", ledger)
    return {"ok": True, **_accounts_payload()}


class SetProvider(BaseModel):
    provider: str  # simplefin | sure | none


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
