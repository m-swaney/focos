from focos.ledger import netting

ENTITY_OF = {"t-merc": "shop", "l-sccu": "rental", "p-chk": "personal"}
LABELS = {
    "shop": [{"label": "guaranteed_payment", "match": "GUARANTEED"}, {"label": "guaranteed_payment", "amount": 8000},
                   {"label": "distribution", "match": "DISTRIB"}, {"label": "other_income", "match": ".*"}],
    "rental": [{"label": "rent", "match": "(RENT|ZELLE)"}, {"label": "other_income", "match": ".*"}],
}
RULES = [{"name": "reimb", "match": "REIMB", "direction": "inflow", "entity": "shop", "classify_as": "reimbursement"},
         {"name": "lmcu", "match": "HOME CU", "direction": "inflow", "entity": "rental", "classify_as": "capital_contribution"}]


def tx(i, acct, amount, name, d="2026-08-10"):
    return {"id": f"t{i}", "date": d, "account_id": acct, "account_name": acct, "amount": amount, "name": name,
            "merchant": None, "category": None, "tags": [], "transfer_id": None, "other_account_id": None,
            "external_id": None, "source": "test"}


def test_income_labels_and_reimbursement_exclusion():
    txs = [
        tx(1, "t-merc", 8000, "ACH CREDIT SOMEFIRM LLC"),        # exact amount -> guaranteed_payment
        tx(2, "t-merc", 4200, "SOMEFIRM DISTRIBUTION Q3"),
        tx(3, "t-merc", 312.5, "SOMEFIRM REIMB TRAVEL"),          # reimbursement, not income
        tx(4, "l-sccu", 2150, "ZELLE FROM TENANT"),
        tx(5, "l-sccu", 5000, "HOME CU TRANSFER IN"),                # capital contribution, not income
        tx(6, "t-merc", -89, "AWS"),
    ]
    r = netting.net(txs, ENTITY_OF, RULES, set(), income_labels=LABELS)
    t = r["per_entity"]["shop"]
    assert t["income"] == 8000 + 4200
    assert t["income_by_label"] == {"guaranteed_payment": 8000, "distribution": 4200}
    assert t["transfers_by_class"] == {"reimbursement": 312.5}
    assert t["expense"] == 89
    l = r["per_entity"]["rental"]
    assert l["income_by_label"] == {"rent": 2150}
    assert l["transfers_by_class"] == {"capital_contribution": 5000}
    assert r["consolidated"]["income"] == 8000 + 4200 + 2150
