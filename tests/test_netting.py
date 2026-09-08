from focos.ledger import entities as ent
from focos.ledger import netting

ENTITY_OF = {"p-chk": "personal", "p-cc": "personal", "t-merc": "shop", "l-sccu": "rental"}
CORRIDORS = {("shop", "personal"), ("personal", "shop"), ("rental", "personal"), ("personal", "rental")}
RULES = [{"name": "RH deposit", "match": "ROBINHOOD", "direction": "outflow", "entity": "personal",
          "classify_as": "investment_contribution"}]


def tx(i, acct, amount, name, d="2026-08-10", transfer_id=None, other=None):
    return {"id": f"t{i}", "date": d, "account_id": acct, "account_name": acct, "amount": amount, "name": name,
            "merchant": None, "category": None, "tags": [], "transfer_id": transfer_id, "other_account_id": other,
            "external_id": None, "source": "test"}


def test_sure_matched_pair_is_inter_entity_and_excluded():
    txs = [
        tx(1, "t-merc", -2000, "Owner draw", transfer_id="x1", other="p-chk"),
        tx(2, "p-chk", 2000, "Deposit from Biz Bank", transfer_id="x1", other="t-merc"),
        tx(3, "t-merc", 5000, "Client payment"),
        tx(4, "p-chk", -120, "Groceries"),
    ]
    r = netting.net(txs, ENTITY_OF, RULES, CORRIDORS)
    assert r["per_entity"]["shop"]["income"] == 5000
    assert r["per_entity"]["shop"]["inter_out"] == 2000
    assert r["per_entity"]["personal"]["inter_in"] == 2000
    assert r["per_entity"]["personal"]["income"] == 0  # the draw is not income
    assert r["consolidated"]["income"] == 5000 and r["consolidated"]["expense"] == 120
    assert r["inter_entity_flows"][0]["from_entity"] == "shop"
    assert r["inter_entity_flows"][0]["to_entity"] == "personal"


def test_rule_based_one_legged_transfer():
    txs = [tx(1, "p-chk", -500, "ROBINHOOD ACH"), tx(2, "p-chk", 3000, "Payroll")]
    r = netting.net(txs, ENTITY_OF, RULES, CORRIDORS)
    assert r["per_entity"]["personal"]["expense"] == 0
    assert r["per_entity"]["personal"]["one_legged_out"] == 500
    assert r["per_entity"]["personal"]["income"] == 3000


def test_heuristic_pairing_on_corridor_and_unmatched_detection():
    txs = [
        tx(1, "l-sccu", -1500, "Transfer to member", d="2026-08-01"),
        tx(2, "p-chk", 1500, "COAST CU transfer", d="2026-08-03"),
        tx(3, "p-chk", -1500, "Zelle to someone else", d="2026-08-20"),  # no partner -> unmatched
        tx(4, "l-sccu", 2200, "Rent received"),
    ]
    r = netting.net(txs, ENTITY_OF, RULES, CORRIDORS)
    assert r["counts"]["transfers"] == 2
    assert r["per_entity"]["rental"]["inter_out"] == 1500
    assert r["per_entity"]["rental"]["income"] == 2200
    assert [u["id"] for u in r["unmatched"]] == ["t3"]
    # invariant: consolidated equals the sum of entities
    assert abs(r["consolidated"]["income"] - sum(e["income"] for e in r["per_entity"].values())) < 1e-9
    assert abs(r["consolidated"]["expense"] - sum(e["expense"] for e in r["per_entity"].values())) < 1e-9


def test_expense_by_category_and_buckets():
    txs = [
        dict(tx(1, "p-chk", -120, "ALDI"), category="groceries"),
        dict(tx(2, "p-cc", -40, "STARBUCKS"), category="dining"),
        dict(tx(3, "p-chk", -35, "MYSTERY SHOP")),
        dict(tx(4, "t-merc", -99, "VERCEL"), category="subscriptions"),
        tx(5, "p-chk", 3000, "Payroll"),
    ]
    r = netting.net(txs, ENTITY_OF, RULES, CORRIDORS, entity_kinds={"personal": "household", "shop": "business"})
    p = r["per_entity"]["personal"]
    assert p["expense_by_category"] == {"groceries": 120, "dining": 40, "uncategorized": 35}
    assert p["core_expense"] == 120 and p["discretionary_expense"] == 40 and p["uncategorized_expense"] == 35
    assert abs(sum(p["expense_by_category"].values()) - p["expense"]) < 1e-9
    shop = r["per_entity"]["shop"]
    assert shop["core_expense"] == 99 and shop["discretionary_expense"] == 0  # a business spends on operations
    c = r["consolidated"]
    assert c["expense_by_category"]["subscriptions"] == 99 and abs(sum(c["expense_by_category"].values()) - c["expense"]) < 1e-9
    assert c["core_expense"] + c["discretionary_expense"] + c["uncategorized_expense"] == c["expense"]


def test_balance_sheets_and_robinhood_no_double_count():
    accounts = [
        {"id": "p-chk", "name": "Checking", "balance": 5000, "classification": "asset", "account_type": "depository", "subtype": "checking"},
        {"id": "p-cc", "name": "Card", "balance": 800, "classification": "liability", "account_type": "credit_card"},
        {"id": "t-merc", "name": "Biz Bank", "balance": 20000, "classification": "asset", "account_type": "depository", "subtype": "checking"},
        {"id": "zzz", "name": "Unknown", "balance": 1, "classification": "asset", "account_type": "depository"},
    ]
    cfg = {"entities": {"personal": {"label": "Personal"}, "shop": {"label": "Shop"}, "rental": {"label": "LLC"}}}
    bs = ent.balance_sheets(accounts, ENTITY_OF, {"individual": 60000, "roth": 16000}, broker_in_ledger=False, entities_cfg=cfg)
    assert bs["entities"]["personal"]["net_worth"] == 5000 - 800 + 76000
    assert bs["entities"]["shop"]["net_worth"] == 20000
    assert bs["consolidated"]["net_worth"] == 5000 - 800 + 76000 + 20000
    assert [u["id"] for u in bs["unmapped_accounts"]] == ["zzz"]
    bs2 = ent.balance_sheets(accounts, ENTITY_OF, {"individual": 60000}, broker_in_ledger=True, entities_cfg=cfg)
    assert bs2["entities"]["personal"]["net_worth"] == 4200
