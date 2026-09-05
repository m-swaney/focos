"""Redaction for diagnostics bundles: secrets, credentials in URLs, account numbers, names, addresses, e-mails,
and (optionally) amounts. Applied to every text file that leaves the machine."""
from __future__ import annotations

import re

from .. import settings

SECRET_PATTERNS = [
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9]{16,}"),
    re.compile(r"\bAIza[0-9A-Za-z_\-]{20,}"),
    re.compile(r"\b(?:ghp|gho|ghu|ghs|github_pat)_[A-Za-z0-9_]{16,}"),
    re.compile(r"\bxox[abpr]-[A-Za-z0-9\-]{8,}"),
]
URL_CREDS = re.compile(r"(https?://)[^\s/:@]+:[^\s/@]+@")
EMAIL = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
LONG_DIGITS = re.compile(r"(?<![\w.\-])(\d{4,})(\d{4})(?![\w.\-])")   # 8+ digits: keep last 4
ENV_VALUE = re.compile(r"^([A-Z][A-Z0-9_]*)=(.+)$", re.M)
AMOUNT = re.compile(r"(?<![\w.])\$?\d{1,3}(?:,\d{3})+(?:\.\d+)?|(?<![\w.])\$?\d{4,}(?:\.\d+)?")
STREET = re.compile(r"\b\d{1,6}\s+(?:[A-Z][a-z]+\s){1,4}(?:St|Street|Ave|Avenue|Rd|Road|Dr|Drive|Ct|Court|Ln|Lane|Blvd|Way|Pl|Place|Mnr|Manor)\b\.?", re.I)


def names_to_scrub() -> list[tuple[str, str]]:
    prof = settings.profile_v2()
    out = []
    owner = (prof.get("owner") or {}).get("name")
    if owner:
        out.append((str(owner), "OWNER"))
    for ent_key, ent in (settings.entities_v2().get("entities") or {}).items():
        if ent_key != "personal" and ent.get("label"):
            out.append((str(ent["label"]), f"ENTITY_{ent_key.upper()}"))
    for p in (settings.properties().get("properties") or []):
        if p.get("address"):
            out.append((str(p["address"]), "ADDRESS"))
        if p.get("name"):
            out.append((str(p["name"]), "PROPERTY"))
    return out


def redact(text: str, scrub_amounts: bool = False, extra_names: list[tuple[str, str]] | None = None) -> str:
    for rx in SECRET_PATTERNS:
        text = rx.sub("[SECRET]", text)
    text = URL_CREDS.sub(r"\1[CREDS]@", text)
    text = ENV_VALUE.sub(lambda m: f"{m.group(1)}={'[SET]' if m.group(2).strip() else ''}", text)
    text = EMAIL.sub("[EMAIL]", text)
    text = LONG_DIGITS.sub(lambda m: "#" * len(m.group(1)) + m.group(2), text)
    text = STREET.sub("[ADDRESS]", text)
    for name, tag in (extra_names if extra_names is not None else names_to_scrub()):
        if len(name) >= 3:
            text = re.sub(re.escape(name), f"[{tag}]", text, flags=re.I)
    if scrub_amounts:
        text = AMOUNT.sub("[AMOUNT]", text)
    return text
