"""The taxonomy is defined once in Python and mirrored in the dashboard; keep them identical."""
import re
from pathlib import Path

from focos.ledger import categories

TS = Path(__file__).resolve().parents[1] / "dashboard" / "lib" / "categories.ts"


def test_taxonomy_matches_dashboard():
    block = re.search(r"CATEGORIES = \[(.*?)\] as const", TS.read_text(encoding="utf-8"), re.S).group(1)
    ts = re.findall(r'"([a-z_]+)"', block)
    assert tuple(ts) == categories.CATEGORIES
    labels = re.findall(r"^\s+([a-z_]+): \"", TS.read_text(encoding="utf-8"), re.M)
    assert set(labels) == set(categories.CATEGORIES)


def test_buckets_and_seeds():
    assert categories.CORE.isdisjoint(categories.DISCRETIONARY)
    assert categories.CORE | categories.DISCRETIONARY | categories.BUSINESS | {categories.UNCATEGORIZED, categories.TRANSFER} == set(categories.CATEGORIES)
    assert categories.bucket("transfer") == "transfer" and categories.seed_category("CHASE CREDIT CRD AUTOPAY") == "transfer"
    assert categories.seed_category("AMERICAN EXPRESS ACH PMT") == "transfer"
    assert categories.bucket("dining") == "discretionary" and categories.bucket("groceries") == "core"
    assert categories.bucket("dining", "business") == "core" and categories.bucket(None) == "uncategorized"
    assert categories.seed_category("STARBUCKS") == "dining" and categories.seed_category("ALDI") == "groceries"
    assert categories.seed_category("FPL") == "utilities" and categories.seed_category("BP") == "transport"
    assert categories.seed_category("BPX HOLDINGS") is None  # whole-token match only
    assert categories.seed_category("SOMETHING NEW") is None
    assert all(c in categories.DEFINITIONS for c in categories.CATEGORIES)
