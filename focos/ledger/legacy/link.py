"""Match live feed accounts (SimpleFIN, Mercury) to imported legacy accounts so their history continues under
one identity. Exact matches use the SimpleFIN account id Sure stored; the rest fall back to institution, name,
and last balance."""
from __future__ import annotations

from ..providers.base import LedgerAccount
from ..providers.sqlite_store import SQLiteStore

EXACT_SCORE = 10.0
MIN_SCORE = 1.5


def _heuristic(a: LedgerAccount, b: LedgerAccount) -> float:
    s = 0.0
    ai, bi = (a.institution_name or "").lower(), (b.institution_name or "").lower()
    if ai and bi and (ai[:6] in bi or bi[:6] in ai):
        s += 1.0
    if "mercury" in ai and ("mercury" in bi or "mercury" in b.name.lower()):
        s += 1.0
    words = set(a.name.lower().split()) & set(b.name.lower().split())
    s += 0.5 * len(words)
    if a.balance and b.balance and abs(a.balance - b.balance) < max(5.0, 0.02 * abs(a.balance)):
        s += 1.5
    return s


def propose(store: SQLiteStore, primary: tuple[str, ...], legacy_providers: list[str]) -> dict:
    live = store.accounts(providers=primary)
    legacy = store.accounts(providers=legacy_providers) if legacy_providers else []
    raw = {b.id: store.account_raw(b.id) for b in legacy}
    by_sf_id = {str(r.get("simplefin_account_id")): b for b in legacy if (r := raw[b.id]).get("simplefin_account_id")}
    proposals, taken = [], set()
    for a in live:
        best, score, how = None, 0.0, "heuristic"
        if a.provider == "simplefin":
            hit = by_sf_id.get(a.id.split(":", 1)[1])
            if hit and hit.id not in taken:
                best, score, how = hit, EXACT_SCORE, "simplefin_id"
        if best is None:
            for b in legacy:
                if b.id in taken:
                    continue
                s = _heuristic(a, b)
                if s > score:
                    best, score = b, s
        if best and score >= MIN_SCORE:
            taken.add(best.id)
            proposals.append({"live": a.id, "name": a.name, "legacy": best.id, "legacy_name": best.name, "score": score, "how": how})
    unmatched = [{"id": b.id, "name": b.name, "type": b.account_type, "classification": b.classification, "balance": b.balance,
                  "status": raw[b.id].get("status"), "kind": raw[b.id].get("accountable_type")}
                 for b in legacy if b.id not in taken]
    return {"proposals": proposals, "unmatched_legacy": unmatched}


def apply(store: SQLiteStore, proposals: list[dict], primary: tuple[str, ...]) -> dict:
    """Record aliases, move entity mappings to the live ids, and set the global legacy cutoff to the first day
    the live feeds cover (unless one is already set)."""
    from ...config.models import HOUSEHOLD
    from .. import entities as ent

    entity_of = ent.account_entity_map()
    moved = []
    for p in proposals:
        store.set_aliases(p["live"], [p["legacy"]])
        key = entity_of.get(ent._bare(p["legacy"]))
        if key:
            ent.add_account_id(key, p["live"], replace=p["legacy"])
            moved.append({"live": p["live"], "entity": key})
        elif not entity_of.get(ent._bare(p["live"])):
            moved.append({"live": p["live"], "entity": None, "note": f"not mapped; assign it in Setup (defaults to {HOUSEHOLD})"})
    cutoff = store.get_meta("legacy_cutoff")
    if not cutoff:
        starts = [fp["start_date"] for prov in primary if (fp := store.first_pull(prov)) and fp.get("start_date")]
        if starts:
            cutoff = min(starts)
            store.set_meta("legacy_cutoff", cutoff)
    return {"aliased": len(proposals), "entities_updated": moved, "legacy_cutoff": cutoff}
