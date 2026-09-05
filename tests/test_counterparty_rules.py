from focos.ledger import netting

ENTITY_OF = {"p-chk": "personal", "t-merc": "shop", "l-sccu": "rental"}
RULES = [
    {"name": "tl pays me", "match": "(CORNER SHOP|BIZBANKACH)", "direction": "inflow", "entity": "personal",
     "counterparty": "shop", "classify_as": "owner_pay"},
    {"name": "newrez", "match": "(NEWREZ|SHELLPOINT)", "direction": "outflow", "entity": "personal", "classify_as": "debt_payment"},
    {"name": "into sccu", "match": "(HOME CU|TRANSFER)", "direction": "inflow", "entity": "rental",
     "counterparty": "personal", "classify_as": "capital_contribution"},
]
IGNORE = ["ALDI", "CHRISTIANCAREMIN"]


def tx(i, acct, amount, name, d="2026-08-11"):
    return {"id": f"t{i}", "date": d, "account_id": acct, "account_name": acct, "amount": amount, "name": name,
            "merchant": None, "category": None, "tags": [], "transfer_id": None, "other_account_id": None,
            "external_id": None, "source": "test"}


def test_one_legged_counterparty_flows_and_ignores():
    txs = [
        tx(1, "p-chk", 5100.25, "Corner Shop LLC - DEPOSIT BizBankACH"),
        tx(2, "p-chk", -1601.29, "Shellpoint Mortgage Servicing NEWREZ"),
        tx(3, "p-chk", -19.0, "Grocery Mart - GROCERY 12345 Springfield"),
        tx(4, "p-chk", -734.95, "ChristianCareMin XFER"),
        tx(5, "l-sccu", 1300.50, "Transfer from HOME CU"),
        tx(6, "t-merc", 8000, "GUARANTEED PAYMENT"),
        {**tx(7, "p-loan", 1601.29, "Payment received"), "account_type": "loan"},   # loan-side credit
        {**tx(8, "p-loan", -812.10, "Interest charged"), "account_type": "loan"},
    ]
    ENTITY_OF["p-loan"] = "personal"
    r = netting.net(txs, ENTITY_OF, RULES, {("shop", "personal"), ("personal", "shop")},
                    ignore_patterns=IGNORE)
    p = r["per_entity"]["personal"]
    assert p["income"] == 0                       # Shop deposit is not personal income
    assert p["inter_in"] == 5100.25
    assert p["expense"] == 19.0 + 734.95 + 812.10  # mortgage payment is a transfer; groceries, health share, interest are spend
    assert p["transfers_by_class"]["debt_payment"] == 1601.29
    assert p["transfers_by_class"]["debt_payment_received"] == 1601.29
    l = r["per_entity"]["rental"]
    assert l["income"] == 0 and l["inter_in"] == 1300.50
    flows = {(f["from_entity"], f["to_entity"], f["amount"]) for f in r["inter_entity_flows"]}
    assert ("shop", "personal", 5100.25) in flows
    assert ("personal", "rental", 1300.50) in flows
    assert r["unmatched"] == []                    # ALDI and ChristianCareMin suppressed, XFER ignored
    assert r["consolidated"]["income"] == 8000
