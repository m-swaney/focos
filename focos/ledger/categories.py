"""The spending taxonomy (small, fixed) and the generic seed rules that label national chains without any model
call. dashboard/lib/categories.ts mirrors CATEGORIES; a test keeps them equal."""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import yaml

UNCATEGORIZED = "uncategorized"
CATEGORIES: tuple[str, ...] = (
    "housing", "utilities", "groceries", "dining", "transport", "health", "insurance", "shopping", "travel", "entertainment",
    "subscriptions", "kids_family", "education", "gifts_donations", "personal_care", "fees_interest", "taxes", "business_ops",
    "professional_services", UNCATEGORIZED,
)
DEFINITIONS: dict[str, str] = {
    "housing": "rent, mortgage escrow items, HOA dues, home repairs and maintenance, furniture",
    "utilities": "electric, gas, water, trash, internet, mobile phone",
    "groceries": "supermarkets, warehouse clubs, food delivery of groceries",
    "dining": "restaurants, coffee shops, fast food, bars, meal delivery",
    "transport": "fuel, rideshare, parking, tolls, transit, car repairs and parts, registration",
    "health": "pharmacy, doctors, dentists, therapy, gym and fitness",
    "insurance": "auto, home, renters, life, umbrella, health premiums paid directly",
    "shopping": "general retail, clothing, electronics, home goods, online marketplaces",
    "travel": "airlines, hotels, car rental, vacation rentals, cruises",
    "entertainment": "streaming rentals, movies, concerts, games, hobbies, sports events",
    "subscriptions": "recurring digital services: streaming, software, news, cloud storage, memberships",
    "kids_family": "childcare, school supplies, baby gear, kids activities, pet care",
    "education": "tuition, courses, books, certifications",
    "gifts_donations": "gifts, charity, tithes",
    "personal_care": "haircuts, salons, cosmetics, laundry",
    "fees_interest": "bank fees, late fees, interest charges, ATM fees",
    "taxes": "federal, state, and property tax payments; tax software",
    "business_ops": "software, hosting, supplies, advertising, and other operating costs of a business entity",
    "professional_services": "accountants, lawyers, consultants, payroll services, registered agents",
    UNCATEGORIZED: "unknown; use only when nothing else fits",
}
CORE = frozenset({"housing", "utilities", "groceries", "transport", "health", "insurance", "kids_family", "education",
                  "fees_interest", "taxes"})
DISCRETIONARY = frozenset({"dining", "shopping", "travel", "entertainment", "subscriptions", "gifts_donations", "personal_care"})
BUSINESS = frozenset({"business_ops", "professional_services"})
SEEDS_FILE = Path(__file__).with_name("category_seeds.yml")


def is_category(name: str | None) -> bool:
    return name in CATEGORIES


def bucket(category: str | None, entity_kind: str | None = None) -> str:
    """core | discretionary | uncategorized for one expense. A business entity's spending is all operating cost."""
    cat = category or UNCATEGORIZED
    if cat == UNCATEGORIZED:
        return "uncategorized"
    if entity_kind and entity_kind != "household":
        return "core"
    if cat in DISCRETIONARY:
        return "discretionary"
    return "core"


@lru_cache(maxsize=1)
def seeds() -> list[tuple[re.Pattern, str]]:
    """[(compiled pattern, category)] from category_seeds.yml, in file order (first match wins)."""
    data = yaml.safe_load(SEEDS_FILE.read_text(encoding="utf-8")) or {}
    out: list[tuple[re.Pattern, str]] = []
    for cat, patterns in data.items():
        if cat not in CATEGORIES:
            continue
        for p in patterns or []:
            out.append((re.compile(rf"(?<![A-Z0-9]){p}(?![A-Z0-9])", re.I), cat))
    return out


def seed_category(merchant_key: str) -> str | None:
    for pat, cat in seeds():
        if pat.search(merchant_key or ""):
            return cat
    return None


def taxonomy_text() -> str:
    return "\n".join(f"- {c}: {DEFINITIONS[c]}" for c in CATEGORIES)
