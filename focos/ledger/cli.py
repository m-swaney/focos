"""`focos ledger ...`: connect SimpleFIN, pull, inspect, manual accounts, and one-time imports from Sure."""
from __future__ import annotations

import json
import os
from datetime import date as _date
from datetime import timedelta
from pathlib import Path

import typer

from .. import paths, settings

ledger_app = typer.Typer(no_args_is_help=True, help="Bank/card/loan ledger (SimpleFIN into SQLite, or Sure).")


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


@ledger_app.command("claim")
def ledger_claim(token: str = typer.Option(..., "--token", help="SimpleFIN setup token (one-time use)"),
                 pull: bool = typer.Option(True, help="pull accounts right away")) -> None:
    """Exchange a SimpleFIN setup token for an access URL, store it in .env, and pull the first window."""
    from .providers.simplefin import ENV_ACCESS_URL, SimpleFINClient, SimpleFINProvider

    access = SimpleFINClient.claim(token)
    write_env_value(ENV_ACCESS_URL, access)
    settings.reset()
    out = {"stored": ENV_ACCESS_URL, "host": access.split("@")[-1].split("/")[0]}
    if pull:
        res = SimpleFINProvider(access_url=access).refresh(_date.today(), force=True)
        out["pull"] = res.model_dump()
    _echo(out)


@ledger_app.command("refresh")
def ledger_refresh(force: bool = typer.Option(False, "--force", help="ignore refresh_min_hours")) -> None:
    """Pull the latest window from the provider (SimpleFIN) or trigger its sync (Sure)."""
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
    """Add or update a manually valued account (property, private loan, vehicle...)."""
    from . import providers
    from .providers.base import ManualAccountSpec

    p = providers.current()
    if p is None:
        typer.echo("no ledger provider configured", err=True)
        raise typer.Exit(2)
    spec = ManualAccountSpec(key=key, name=name, entity=entity, account_type=type_, subtype=subtype,
                             classification="liability" if liability else "asset", balance=balance)
    _echo(p.upsert_manual_account(spec).as_row())


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


@ledger_app.command("import-sure")
def ledger_import_sure(since: str = typer.Option(..., help="YYYY-MM-DD"), until: str = typer.Option(None, help="YYYY-MM-DD (default today)"),
                       dry_run: bool = False) -> None:
    """One-time copy of Sure accounts and transactions into the local SQLite ledger (before switching providers)."""
    from ..sources.sure import SureClient
    from .providers.sqlite_store import SQLiteStore
    from .providers.sure import SureProvider

    src = SureProvider(SureClient())
    store = SQLiteStore(paths.LEDGER_DB)
    start, end = _date.fromisoformat(since), _date.fromisoformat(until) if until else _date.today()
    accounts = src.accounts()
    n_tx = 0
    if not dry_run:
        for a in accounts:
            store.upsert_account(a, raw=getattr(a, "raw", None))
            if a.balance_date:
                store.upsert_balance(a.id, a.balance_date, a.balance, source="sure")
    cur = start
    while cur <= end:
        win_end = min(cur + timedelta(days=89), end)
        txs = src.transactions(cur, win_end)
        by_acct: dict[str, list] = {}
        for t in txs:
            by_acct.setdefault(t.account_id, []).append({"id": t.id, "posted_date": t.date, "amount": t.amount, "description": t.name,
                                                         "payee": t.merchant, "memo": None, "pending": False, "raw": {}})
        if not dry_run:
            for aid, rows in by_acct.items():
                store.upsert_transactions(aid, rows, seen_ids_this_pull=set())
        n_tx += len(txs)
        cur = win_end + timedelta(days=1)
    # daily balances from the historical Sure snapshots kept under state/
    n_bal = 0
    for f in sorted(paths.SNAPSHOTS_SURE.glob("*.json")) if paths.SNAPSHOTS_SURE.exists() else []:
        snap = settings.read_json(f, {}) or {}
        for a in snap.get("accounts", []):
            from .entities import money

            if not dry_run:
                store.upsert_balance(f"sure:{a.get('id')}", snap.get("date") or f.stem, money(a), source="sure")
            n_bal += 1
    _echo({"accounts": len(accounts), "transactions": n_tx, "balance_points": n_bal, "dry_run": dry_run, "db": str(paths.LEDGER_DB)})


@ledger_app.command("link-legacy")
def ledger_link_legacy(apply: bool = typer.Option(False, "--apply", help="write aliases into the store and entities.yml")) -> None:
    """Propose SimpleFIN <-> imported Sure account matches (institution + name + last balance) and record them as aliases."""
    from .providers.sqlite_store import SQLiteStore

    store = SQLiteStore(paths.LEDGER_DB)
    sf = store.accounts(providers=("simplefin",))
    legacy = store.accounts(providers=("sure",))
    proposals = []
    for a in sf:
        best, score = None, 0.0
        for b in legacy:
            s = 0.0
            if a.institution_name and b.institution_name and a.institution_name.lower()[:6] in b.institution_name.lower():
                s += 1.0
            words = set(a.name.lower().split()) & set(b.name.lower().split())
            s += 0.5 * len(words)
            if a.balance and b.balance and abs(a.balance - b.balance) < max(5.0, 0.02 * abs(a.balance)):
                s += 1.5
            if s > score:
                best, score = b, s
        if best and score >= 1.5:
            proposals.append({"simplefin": a.id, "name": a.name, "sure": best.id, "sure_name": best.name, "score": score})
    if apply:
        import yaml

        ents = settings.entities_v2()
        changed = False
        for p in proposals:
            store.set_aliases(p["simplefin"], [p["sure"]])
            for ent in ents.get("entities", {}).values():
                ids = ent.get("account_ids") or []
                if p["sure"] in ids and p["simplefin"] not in ids:
                    ids.append(p["simplefin"])
                    ent["account_ids"] = ids
                    changed = True
        if changed:
            (paths.CONFIG / "entities.yml").write_text("# Entities (v2 layout; aliases added by focos ledger link-legacy).\n"
                                                         + yaml.safe_dump(ents, sort_keys=False, allow_unicode=True), encoding="utf-8")
            settings.reset()
    _echo({"proposals": proposals, "applied": apply})
