"""Merchant normalization on generic bank-feed strings."""
import pytest

from focos.ledger.merchants import display_name, merchant_key


@pytest.mark.parametrize("payee, description, expected", [
    (None, "STARBUCKS STORE 10023", "STARBUCKS"),
    (None, "ALDI 77166 VERO BEACH", "ALDI"),
    (None, "Netflix.com", "NETFLIX"),
    (None, "SQ *BLUE BOTTLE COFFEE", "BLUE BOTTLE COFFEE"),
    (None, "TST* THE LOCAL TAVERN", "LOCAL TAVERN"),
    (None, "AMZN Mktp US*2K3JF9 Amzn.com/bill WA", "AMAZON"),
    (None, "POS DEBIT PUBLIX SUPER MARKETS #1234 ORLANDO FL", "PUBLIX SUPER MARKETS"),
    (None, "CHECKCARD 0905 SHELL OIL 57444 MIAMI FL", "SHELL OIL"),
    (None, "PAYPAL *ETSY INC", "ETSY"),
    (None, "UBER *TRIP HELP.UBER.COM", "UBER TRIP HELP UBER"),
    (None, "FPL DIRECT DEBIT", "FPL DIRECT DEBIT"),
    (None, "Purchase authorized on 09/01 TARGET T-1234 TAMPA FL", "TARGET T"),
    (None, "", "UNKNOWN"),
    (None, None, "UNKNOWN"),
    (None, "12345", "12345"),
    ("Starbucks", "STARBUCKS STORE 10023 VERO BEACH FL", "STARBUCKS"),
    (None, "APPLE.COM/BILL 866-712-7753 CA", "APPLE"),
])
def test_merchant_key(payee, description, expected):
    assert merchant_key(payee, description) == expected


def test_same_merchant_different_stores_share_a_key():
    a = merchant_key(None, "STARBUCKS STORE 10023 VERO BEACH FL")
    b = merchant_key(None, "STARBUCKS STORE 10488 ORLANDO FL")
    assert a == b == "STARBUCKS"


def test_display_name():
    assert display_name("BLUE BOTTLE COFFEE") == "Blue Bottle Coffee"
    assert display_name("H&M") == "H&M" and display_name("") == "Unknown"
