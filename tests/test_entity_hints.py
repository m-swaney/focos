from focos.ledger import entities as ent

CFG = {
    "entities": {
        "personal": {"sure_account_ids": ["rh-1"]},
        "shop": {"sure_account_ids": []},
        "rental": {"sure_account_ids": []},
    },
    "name_hints": {
        "shop": "(CORNER SHOP|BIZ BANK)",
        "rental": "(RENTAL|COAST CU|ROCKET)",
        "personal": "(CHASE|AMEX|NEWREZ|ROBINHOOD)",
    },
}

ACCOUNTS = [
    {"id": "rh-1", "name": "Robinhood Individual"},
    {"id": "m-1", "name": "Shop Biz Bank Checking", "institution_name": "Biz Bank"},
    {"id": "r-1", "name": "Rocket Mortgage 1234", "institution_name": "Rocket Mortgage"},
    {"id": "n-1", "name": "NewRez Home Loan", "institution_name": "NewRez"},
    {"id": "c-1", "name": "Sapphire Preferred", "institution_name": "Chase"},
    {"id": "x-1", "name": "Mystery Bank", "institution_name": "Unknown"},
]


def test_hints_map_by_name_and_institution_but_explicit_wins():
    m = ent.account_entity_map(CFG, ACCOUNTS)
    assert m["rh-1"] == "personal"
    assert m["m-1"] == "shop"
    assert m["r-1"] == "rental"
    assert m["n-1"] == "personal"
    assert m["c-1"] == "personal"
    assert "x-1" not in m
