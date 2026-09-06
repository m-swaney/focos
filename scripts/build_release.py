"""Assemble the release bundle: focos-<version>.zip (+ .sha256) under dist/.

Contents: focos/ (source), agent/, pyproject.toml, uv.lock, README.md, installers/, scripts/private_scan.py,
and the prebuilt dashboard (.next/standalone, .next/static, public). Platform-independent; the installer
downloads a Node runtime separately. Run `npm run build` in dashboard/ first (CI does).
"""
from __future__ import annotations

import hashlib
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INCLUDE_DIRS = ["focos", "agent", "installers"]
INCLUDE_FILES = ["pyproject.toml", "uv.lock", "README.md", "LICENSE", "scripts/private_scan.py"]
DASH = ["dashboard/.next/standalone", "dashboard/.next/static", "dashboard/public", "dashboard/package.json", "dashboard/next.config.ts"]
SKIP_PARTS = {"__pycache__", ".pytest_cache", "node_modules"}


def version() -> str:
    m = re.search(r'^version\s*=\s*"([^"]+)"', (ROOT / "pyproject.toml").read_text(encoding="utf-8"), re.M)
    return m.group(1) if m else "0.0.0"


def _skip(f: Path) -> bool:
    """Skip caches and the dashboard's development node_modules, but keep the traced node_modules inside
    .next/standalone: the standalone server needs them and the installer never runs npm."""
    parts = set(f.parts)
    if "node_modules" in parts and "standalone" in parts:
        return bool((SKIP_PARTS - {"node_modules"}) & parts)
    return bool(SKIP_PARTS & parts)


def files():
    for d in INCLUDE_DIRS + DASH:
        p = ROOT / d
        if p.is_file():
            yield p
            continue
        if not p.exists():
            if d.startswith("dashboard/.next"):
                print(f"warning: {d} missing (dashboard not built)", file=sys.stderr)
            continue
        for f in p.rglob("*"):
            if f.is_file() and not _skip(f) and f.suffix != ".pyc":
                yield f
    for f in INCLUDE_FILES:
        if (ROOT / f).exists():
            yield ROOT / f


def main() -> int:
    ver = version()
    dist = ROOT / "dist"
    dist.mkdir(exist_ok=True)
    out = dist / f"focos-{ver}.zip"
    n = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for f in files():
            z.write(f, f.relative_to(ROOT).as_posix())
            n += 1
    digest = hashlib.sha256(out.read_bytes()).hexdigest()
    (dist / f"{out.name}.sha256").write_text(f"{digest}  {out.name}\n", encoding="utf-8")
    print(f"{out} ({n} files, {out.stat().st_size / 1e6:.1f} MB) sha256={digest[:12]}…")
    return 0


if __name__ == "__main__":
    sys.exit(main())
