"""Property accounts: ensure they exist in Sure, refresh values (Zillow or manual), push valuations."""
from __future__ import annotations

import subprocess
import time
from datetime import date

import yaml

from .. import paths, settings
from ..sources.sure import SureClient, SureError

def cfg_path():
    return paths.CONFIG / "properties.yml"




def load() -> list[dict]:
    return (settings._load_yaml("properties.yml") or {}).get("properties", [])


def save(props: list[dict]) -> None:
    cfg = cfg_path()
    text = cfg.read_text(encoding="utf-8")
    header = text.split("properties:")[0]
    cfg.write_text(header + yaml.safe_dump({"properties": props}, sort_keys=False, allow_unicode=True), encoding="utf-8")


def ensure_accounts(props: list[dict]) -> list[dict]:
    """Create a Sure Property account for any entry without sure_account_id (via rails runner)."""
    missing = [p for p in props if not p.get("sure_account_id")]
    if not missing:
        return props
    ruby = 'fam = Family.first\n'
    for p in missing:
        val = float(p.get("manual_value") or p.get("initial_value") or 0)
        ruby += (f'a = fam.accounts.find_by(name: {p["name"]!r}) || Account.create_and_sync({{ family: fam, name: {p["name"]!r}, '
                 f'balance: {val}, currency: "USD", accountable_type: "Property", accountable_attributes: {{}} }}, '
                 f'skip_initial_sync: true, opening_balance_date: Date.today)\n'
                 f'puts "PROP|{p["key"]}|#{{a.id}}"\n')
    r = subprocess.run(["docker", "compose", "exec", "-T", "web", "bin/rails", "runner", ruby],
                       cwd=paths.ROOT / "sure", capture_output=True, text=True)
    ids = {}
    for line in r.stdout.splitlines():
        if line.startswith("PROP|"):
            _, key, aid = line.strip().split("|")
            ids[key] = aid
    for p in props:
        if p["key"] in ids:
            p["sure_account_id"] = ids[p["key"]]
    if ids:
        save(props)
    return props


MIN_DAYS_BETWEEN_ZILLOW_CALLS = 20  # free RapidAPI plan: 25 requests/month, so refresh Zillow at most ~monthly


def refresh(asof: str | None = None, push: bool = True, force: bool = False) -> dict:
    asof = asof or date.today().isoformat()
    props = ensure_accounts(load())
    results = []
    client = None
    zillow = None
    for p in props:
        row = {"key": p["key"], "name": p["name"], "entity": p.get("entity"), "source": p.get("source"),
               "sure_account_id": p.get("sure_account_id")}
        try:
            if p.get("source") == "zillow":
                last = p.get("last_refreshed")
                fresh = last and (date.fromisoformat(asof) - date.fromisoformat(str(last)[:10])).days < MIN_DAYS_BETWEEN_ZILLOW_CALLS
                if fresh and not force and p.get("last_value"):
                    row["value"] = float(p["last_value"])
                    row["cached"] = True
                    row["last_refreshed"] = last
                else:
                    from ..sources.zillow import ZillowClient
                    zillow = zillow or ZillowClient()
                    info = zillow.value(p.get("address"), p.get("zpid"))
                    time.sleep(1.0)
                    row.update(info)
                    row["value"] = info.get("zestimate")
                    if not p.get("zpid") and info.get("zpid"):
                        p["zpid"] = info["zpid"]
                    p["last_value"] = info.get("zestimate")
                    p["last_rent_estimate"] = info.get("rent_zestimate")
                    p["last_refreshed"] = asof
            else:
                row["value"] = float(p.get("manual_value") or 0)
            if push and row.get("value") and p.get("sure_account_id"):
                client = client or SureClient()
                client.create_valuation(p["sure_account_id"], asof, float(row["value"]),
                                        notes=f"focos {p.get('source')} value {asof}")
                row["pushed"] = True
        except (SureError, Exception) as e:  # noqa: BLE001
            row["error"] = f"{type(e).__name__}: {str(e)[:200]}"
        results.append(row)
    save(props)
    out = {"asof": asof, "properties": results,
           "total_value": sum(r.get("value") or 0 for r in results if not r.get("error"))}
    settings.write_json(paths.LATEST / "properties.json", out)
    return out
