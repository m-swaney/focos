"""Merchant normalization: turn "STARBUCKS STORE 10023 VERO BEACH FL" and "Starbucks #10488" into one key so a
category learned once applies to every later transaction from the same merchant. Conservative on purpose: a
collision is fixed with one click in the dashboard, a miss just costs one more label."""
from __future__ import annotations

import re

PREFIXES = re.compile(
    r"^(?:POS\s+(?:DEBIT\s+)?|DEBIT\s+CARD\s+PURCHASE\s+|CHECKCARD\s*\d*\s+|PURCHASE\s+(?:AUTHORIZED\s+ON\s+\d{2}/\d{2}\s+)?|"
    r"RECURRING\s+(?:PAYMENT\s+)?|SQ\s*\*\s*|TST\*\s*|PAYPAL\s*\*\s*|PP\*\s*|GOOGLE\s*\*\s*|IC\*\s*|DD\s*\*\s*|"
    r"ACH\s+(?:DEBIT|WITHDRAWAL|PAYMENT)\s+|ELECTRONIC\s+PAYMENT\s+|ONLINE\s+PAYMENT\s+)",
    re.I)
BRANDS = [(re.compile(r"^(?:AMZN\s*MKTP|AMAZON\.COM|AMAZON\s+MKTPL|AMZN\s+DIGITAL)[^ ]*", re.I), "AMAZON"),
          (re.compile(r"^(?:AMAZON\s+PRIME|PRIME\s+VIDEO)[^ ]*", re.I), "AMAZON PRIME"),
          (re.compile(r"^APPLE\.COM/BILL[^ ]*", re.I), "APPLE"),
          (re.compile(r"^(?:GOOGLE\s*\*|GOOGLE\s+)(YOUTUBE|STORAGE|ONE|FI|PLAY)[^ ]*", re.I), r"GOOGLE \1")]
STATES = {"AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
          "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
          "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY", "DC"}
NOISE = {"INC", "LLC", "LTD", "CO", "CORP", "THE", "WWW", "COM", "NET", "STORE", "ONLINE", "USA", "US", "PAYMENT", "PMT", "PURCHASE"}
MAX_TOKENS = 4


def merchant_key(payee: str | None, description: str | None) -> str:
    s = (payee or "").strip() or (description or "").strip()
    if not s:
        return "UNKNOWN"
    s = s.upper()
    for _ in range(3):
        s2 = PREFIXES.sub("", s).strip()
        if s2 == s:
            break
        s = s2
    for pat, brand in BRANDS:
        if pat.match(s):
            s = pat.sub(brand, s, count=1)
            break
    s = re.sub(r"[^A-Z0-9&' ]+", " ", s)
    tokens = s.split()
    kept: list[str] = []
    for t in tokens:
        digits = sum(c.isdigit() for c in t)
        if t.isdigit() or digits >= 3:
            break  # store numbers, dates, and auth codes come before the city; drop everything from here on
        kept.append(t)
    if not kept and tokens:  # the whole thing was numeric-ish; keep the first token as a last resort
        kept = [tokens[0]]
    while len(kept) > 1 and kept[-1] in STATES:
        kept.pop()
    kept = [t for t in kept if t not in NOISE] or kept
    kept = kept[:MAX_TOKENS]
    return " ".join(kept) or "UNKNOWN"


def display_name(key: str) -> str:
    return " ".join(w.capitalize() if (w.isalpha() and len(w) > 2) else w for w in (key or "").split()) or "Unknown"
