"""Redacted diagnostics zip a household can send for support: doctor output, status, config (redacted), recent run
logs (redacted), versions. Never the ledger, snapshots, reports, or .env."""
from __future__ import annotations

import json
import platform
import sys
import zipfile
from datetime import datetime
from pathlib import Path

from .. import paths, settings
from . import checks, redact

INCLUDE_CONFIG = ("focos.yml", "profile.yml", "goals.yml", "accounts.yml", "entities.yml", "transfer_rules.yml",
                  "sandbox_rules.yml", "analytics.yml")


def _versions() -> dict:
    out = {"python": sys.version.split()[0], "platform": platform.platform(), "app": str(paths.APP)}
    for mod in ("focos", "pandas", "numpy", "pydantic", "fastapi", "anthropic", "openai", "dulwich"):
        try:
            m = __import__(mod)
            out[mod] = getattr(m, "__version__", "?")
        except Exception:  # noqa: BLE001
            out[mod] = None
    return out


def export(dest: Path | None = None, scrub_amounts: bool = True, logs_per_mode: int = 3) -> Path:
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = dest or (paths.STATE / f"diagnostics-{ts}.zip")
    dest.parent.mkdir(parents=True, exist_ok=True)
    names = redact.names_to_scrub()

    def r(text: str) -> str:
        return redact.redact(text, scrub_amounts=scrub_amounts, extra_names=names)

    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("doctor.json", r(json.dumps([c.model_dump() for c in checks.run_all()], indent=1)))
        z.writestr("versions.json", json.dumps(_versions(), indent=1))
        if paths.STATUS.exists():
            z.writestr("status.json", r(paths.STATUS.read_text(encoding="utf-8", errors="replace")))
        for name in INCLUDE_CONFIG:
            p = paths.CONFIG / name
            if p.exists():
                z.writestr(f"config/{name}", r(p.read_text(encoding="utf-8", errors="replace")))
        if paths.LOGS.exists():
            for mode in ("daily", "weekly", "monthly"):
                for f in sorted(paths.LOGS.glob(f"*-{mode}-run.log"))[-logs_per_mode:]:
                    z.writestr(f"logs/{f.name}", r(f.read_text(encoding="utf-8", errors="replace")[-200_000:]))
                for f in sorted(paths.LOGS.glob(f"*-{mode}-*.json.err"))[-logs_per_mode:]:
                    z.writestr(f"logs/{f.name}", r(f.read_text(encoding="utf-8", errors="replace")[-50_000:]))
        if paths.LATEST.exists():
            listing = [{"file": f.name, "bytes": f.stat().st_size} for f in sorted(paths.LATEST.glob("*"))]
            z.writestr("derived_files.json", json.dumps(listing, indent=1))
        z.writestr("README.txt", "focos diagnostics bundle. Secrets, credentials, account numbers, names, addresses, e-mails"
                                 + (", and amounts" if scrub_amounts else "") + " were redacted before packing. "
                                 "The ledger database, snapshots, reports, and .env are never included.\n")
    return dest
