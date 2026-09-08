"""`focos ledger ...`: connect SimpleFIN and Mercury, pull, inspect, manual accounts, and legacy imports."""
from __future__ import annotations

import json
import os
from datetime import date as _date
from datetime import timedelta
from pathlib import Path

import typer

from .. import paths, settings

ledger_app = typer.Typer(no_args_is_help=True, help="Bank/card/loan ledger (SimpleFIN and Mercury into a local SQLite file).")


def _echo(obj) -> None:
    typer.echo(json.dumps(obj, indent=2, default=str))


def write_env_value(key: str, value: str) -> None:
    """Set or replace one KEY=value line in <home>/.env (created if missing)."""
    env = paths.ENV_FILE
    lines = env.read_text(encoding="utf-8").splitlines() if env.exists() else []
    out, done = [], False
    for line in lines:
        if line.split("=", 1)[0].strip() == key:
            out.append(f"{key}={value}")
            done = True
        else:
            out.append(line)
    if not done:
        out.append(f"{key}={value}")
    env.write_text("\n".join(out) + "\n", encoding="utf-8")
    os.environ[key] = value


def _set_ledger(**changes) -> None:
    from ..config import writer

    ledger = dict(settings.focos().get("ledger") or {})
    ledger.update(changes)
    writer.write_section("focos.yml", "ledger", ledger)
    settings.reset()


def _store():
    from .providers.sqlite_store import SQLiteStore

    return SQLiteStore(paths.LEDGER_DB)


def _legacy_providers(store) -> list[str]:
    from .providers.simplefin import MANUAL_PROVIDER, PRIMARY_PROVIDERS

    return [p for p in store.providers_present() if p not in PRIMARY_PROVIDERS and p != MANUAL_PROVIDER]


@ledger_app.command("categorize")
def ledger_categorize(force: bool = typer.Option(False, "--force", help="ask the model again even if it ran today"),
                      dry_run: bool = typer.Option(False, "--dry-run", help="show what would be asked; write nothing")) -> None:
    """Apply merchant rules and label new merchants (rules first, one model batch for the rest)."""
    from datetime import date as _date

    from . import categorize

    store = _store()
    try:
        out = categorize.run(store, _date.today().isoformat(), force=force, dry_run=dry_run)
    finally:
        store.close()
    _echo(out)
    if out.get("error"):
        raise typer.Exit(1)


@ledger_app.command("merchants")
def ledger_merchants(uncategorized: bool = typer.Option(True, "--uncategorized/--all", help="only merchants without a category"),
                     n: int = 50, days: int = 95) -> None:
    """Merchants seen in the window, with their categories (or without one)."""
    from datetime import date as _date
    from datetime import timedelta

    store = _store()
    try:
        if uncategorized:
            rows = store.uncategorized_merchants((_date.today() - timedelta(days=days)).isoformat(), _date.today().isoformat(), limit=n)
        else:
            rows = list(store.merchant_rules().values())[:n]
    finally:
        store.close()
    _echo(rows)


@ledger_app.command("set-category")
def ledger_set_category(merchant_key: str, category: str) -> None:
    """Teach focos a merchant's category (a user rule; it beats seeds and the model)."""
    from datetime import date as _date

    from ..updates import apply as apply_mod

    changes = apply_mod.apply([{"target": "merchant_rule", "id": merchant_key.strip().upper(), "category": category, "reason": "cli"}],
                              actor="user", run="cli", date=_date.today().isoformat())
    _echo({"ok": changes[0]["ok"], "summary": apply_mod.describe(changes[0]), "error": changes[0].get("error")})
    if not changes[0]["ok"]:
        raise typer.Exit(1)


@ledger_app.command("claim")
def ledger_claim(token: str = typer.Option(..., "--token", help="SimpleFIN setup token (one-time use)"),
                 pull: bool = typer.Option(True, help="pull accounts right away")) -> None:
    """Exchange a SimpleFIN setup token for an access URL, store it in .env, and pull the first window."""
    from .providers.simplefin import ENV_ACCESS_URL, SimpleFINClient, SimpleFINProvider

    access = SimpleFINClient.claim(token)
    write_env_value(ENV_ACCESS_URL, access)
    _set_ledger(provider="simplefin")
    out = {"stored": ENV_ACCESS_URL, "host": access.split("@")[-1].split("/")[0]}
    if pull:
        res = SimpleFINProvider(access_url=access).refresh(_date.today(), force=True)
        out["pull"] = res.model_dump()
    _echo(out)


@ledger_app.command("mercury")
def ledger_mercury(token: str = typer.Option(..., "--token", help="Mercury read-only API token"),
                   pull: bool = typer.Option(True, help="pull accounts right away")) -> None:
    """Connect Mercury business banking directly (for accounts SimpleFIN does not carry)."""
    from .feeds.mercury import ENV_TOKEN, MercuryClient, MercuryFeed

    n = len(MercuryClient(token).accounts())
    write_env_value(ENV_TOKEN, token.strip())
    provider = str((settings.focos().get("ledger") or {}).get("provider") or "none")
    _set_ledger(provider="simplefin" if provider == "none" else provider, mercury={"enabled": True})
    out = {"stored": ENV_TOKEN, "mercury_accounts": n}
    if pull:
        out["pull"] = MercuryFeed(_store(), token=token.strip()).pull(_date.today(), force=True).model_dump()
    _echo(out)


@ledger_app.command("refresh")
def ledger_refresh(force: bool = typer.Option(False, "--force", help="ignore refresh_min_hours")) -> None:
    """Pull the latest window from every configured feed."""
    from . import providers

    p = providers.current()
    if p is None:
        typer.echo("no ledger provider configured (config/focos.yml ledger.provider)", err=True)
        raise typer.Exit(2)
    _echo({"provider": p.name, "health": p.health().model_dump(), "refresh": p.refresh(_date.today(), force=force).model_dump()})


@ledger_app.command("accounts")
def ledger_accounts() -> None:
    """List ledger accounts with inferred types and the entity each maps to."""
    from . import entities as ent
    from . import providers

    p = providers.current()
    if p is None:
        _echo([])
        return
    rows = [a.as_row() for a in p.accounts()]
    entity_of = ent.account_entity_map(accounts=rows)
    _echo([{"id": r["id"], "name": r["name"], "institution": r["institution_name"], "type": r["account_type"],
            "subtype": r["subtype"], "classification": r["classification"], "balance": r["balance"],
            "entity": entity_of.get(r["id"])} for r in rows])


@ledger_app.command("pull")
def ledger_pull(date: str = typer.Option(None), mode: str = "manual", force: bool = False) -> None:
    """Run the ledger step alone and write consolidated.json / entities.json."""
    from .. import holdings
    from . import stage

    date = date or _date.today().isoformat()
    cur, _ = holdings.latest_two()
    out = stage.run(cur, date, mode, trigger_sync=False, force_refresh=force)
    for name in ("consolidated", "entities"):
        settings.write_json(paths.LATEST / f"{name}.json", out[name])
    _echo({k: v for k, v in out.items() if k not in ("consolidated", "entities")})


@ledger_app.command("status")
def ledger_status() -> None:
    from . import providers

    p = providers.current()
    if p is None:
        _echo({"provider": None})
        return
    _echo({"provider": p.name, "health": p.health().model_dump(), "sync": p.sync_status().model_dump()})


@ledger_app.command("manual")
def ledger_manual(key: str = typer.Argument(...), name: str = typer.Option(...), balance: float = typer.Option(...),
                  entity: str = "personal", type_: str = typer.Option("other", "--type", help="depository | credit_card | loan | investment | property | vehicle | other"),
                  subtype: str = typer.Option(None), liability: bool = typer.Option(False, "--liability")) -> None:
    """Add or update a manually valued account (property, private loan, vehicle...) and map it to its entity."""
    from . import entities as ent
    from . import providers
    from .providers.base import ManualAccountSpec

    p = providers.current()
    if p is None:
        typer.echo("no ledger provider configured", err=True)
        raise typer.Exit(2)
    spec = ManualAccountSpec(key=key, name=name, entity=entity, account_type=type_, subtype=subtype,
                             classification="liability" if liability else "asset", balance=balance)
    acct = p.upsert_manual_account(spec)
    ent.add_account_id(entity, acct.id)
    _echo(acct.as_row())


@ledger_app.command("export")
def ledger_export(out: Path = typer.Option(None, "--out"), days: int = 365) -> None:
    """Write transactions of the last N days to CSV (never includes account numbers)."""
    import csv

    from . import providers

    p = providers.current()
    if p is None:
        raise typer.Exit(2)
    end = _date.today()
    rows = p.transactions(end - timedelta(days=days), end)
    out = out or (paths.STATE / f"transactions-{end.isoformat()}.csv")
    with out.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "account", "amount", "description", "merchant", "pending"])
        for t in rows:
            w.writerow([t.date, t.account_name, f"{t.amount:.2f}", t.name, t.merchant, int(t.pending)])
    _echo({"written": str(out), "rows": len(rows)})


# ---------------------------------------------------------------- legacy (Sure) history
@ledger_app.command("import-sure")
def ledger_import_sure(dump: Path = typer.Option(..., "--dump", exists=True, dir_okay=False, help="plain-format pg_dump of the Sure database"),
                       since: str = typer.Option(None, help="YYYY-MM-DD: skip rows before this date"),
                       until: str = typer.Option(None, help="YYYY-MM-DD: skip rows after this date and stop reading legacy history after it"),
                       dry_run: bool = False) -> None:
    """One-time import of a Sure pg_dump (accounts, transactions with transfer pairs, daily balances)."""
    from .legacy import sure_dump

    store = _store()
    s = _date.fromisoformat(since) if since else None
    u = _date.fromisoformat(until) if until else None
    out = sure_dump.import_dump(dump, store, since=s, until=u, dry_run=dry_run)
    if u and not dry_run:
        store.set_meta("legacy_cutoff", (u + timedelta(days=1)).isoformat())
        out["legacy_cutoff"] = (u + timedelta(days=1)).isoformat()
    _echo(out)


@ledger_app.command("legacy")
def ledger_legacy() -> None:
    """Show imported legacy accounts, their aliases, and the date focos stops reading each one."""
    from .providers.simplefin import PRIMARY_PROVIDERS

    store = _store()
    legacy = _legacy_providers(store)
    cutoffs = store.legacy_cutoffs(PRIMARY_PROVIDERS, legacy) if legacy else {}
    alias_of = {alias: a.id for a in store.accounts(providers=PRIMARY_PROVIDERS) for alias in a.aliases}
    rows = [{"id": a.id, "name": a.name, "type": a.account_type, "classification": a.classification, "balance": a.balance,
             "balance_date": a.balance_date, "aliased_to": alias_of.get(a.id), "read_before": cutoffs.get(a.id, "all"),
             "status": store.account_raw(a.id).get("status")} for a in store.accounts(providers=legacy)]
    _echo({"legacy_providers": legacy, "global_cutoff": store.get_meta("legacy_cutoff"), "accounts": rows})


@ledger_app.command("link-legacy")
def ledger_link_legacy(apply: bool = typer.Option(False, "--apply", help="write aliases, move entity mappings, set the legacy cutoff")) -> None:
    """Match live feed accounts to imported legacy accounts (exact SimpleFIN id first, then name and balance)."""
    from .legacy import link
    from .providers.simplefin import PRIMARY_PROVIDERS

    store = _store()
    out = link.propose(store, PRIMARY_PROVIDERS, _legacy_providers(store))
    if apply:
        out["applied"] = link.apply(store, out["proposals"], PRIMARY_PROVIDERS)
    for u in out["unmatched_legacy"]:
        u["adopt"] = (f"focos ledger adopt-legacy {u['id']} --key <key> --entity <entity> --type {u['type']}"
                      + (" --liability" if u["classification"] == "liability" else ""))
    _echo(out)


@ledger_app.command("adopt-legacy")
def ledger_adopt_legacy(legacy_id: str = typer.Argument(..., help="imported account id, e.g. sure:<uuid>"),
                        key: str = typer.Option(..., help="short key for the manual account (becomes manual:<key>)"),
                        entity: str = "personal", name: str = typer.Option(None),
                        type_: str = typer.Option(None, "--type", help="depository | credit_card | loan | investment | property | vehicle | other"),
                        subtype: str = typer.Option(None), liability: bool = typer.Option(False, "--liability")) -> None:
    """Turn an imported account no live feed carries (student loan, property...) into a manual account, keeping its history."""
    from . import entities as ent
    from . import properties
    from .providers.base import ManualAccountSpec

    store = _store()
    old = next((a for a in store.accounts() if a.id == legacy_id), None)
    if old is None:
        typer.echo(f"{legacy_id} is not in the ledger (see `focos ledger legacy`)", err=True)
        raise typer.Exit(2)
    valid = {"depository", "credit_card", "loan", "investment", "property", "vehicle", "other"}
    spec = ManualAccountSpec(key=key, name=name or old.name, entity=entity,
                             account_type=type_ or (old.account_type if old.account_type in valid else "other"),
                             subtype=subtype or old.subtype,
                             classification="liability" if (liability or old.classification == "liability") else "asset",
                             balance=old.balance)
    acct = store.adopt_account(legacy_id, spec)
    ent.add_account_id(entity, acct.id, replace=legacy_id)
    props = properties.load()
    hit = False
    for p in props:
        if properties.account_key(p) == key or (p.get("sure_account_id") and legacy_id.endswith(str(p["sure_account_id"]))):
            p["ledger_account_id"] = acct.id
            hit = True
    if hit:
        properties.save(props)
    _echo({**acct.as_row(), "was": legacy_id, "property_linked": hit})
