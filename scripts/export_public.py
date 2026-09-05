"""Export the shareable part of this checkout into a fresh directory with no git history, ready to become the
public repository. Only an explicit allow-list is copied; the household's config, state, reports, data, and
scripts are never included. The private-data scan runs on the result (with the local pattern file when given).

  python scripts/export_public.py C:\\path\\to\\focos-oss [--patterns C:\\path\\to\\leak_patterns] [--init-git]
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ALLOW = [
    "focos", "agent", "installers", "tests", ".github",
    "dashboard/app", "dashboard/components", "dashboard/design", "dashboard/lib", "dashboard/public",
    "dashboard/package.json", "dashboard/package-lock.json", "dashboard/next.config.ts", "dashboard/tsconfig.json",
    "dashboard/postcss.config.mjs", "dashboard/eslint.config.mjs", "dashboard/.gitignore", "dashboard/AGENTS.md", "dashboard/CLAUDE.md",
    "scripts/private_scan.py", "scripts/build_release.py", "scripts/export_public.py",
    "pyproject.toml", "uv.lock", "README.md", "LICENSE", ".env.example",
]
SKIP_PARTS = {"__pycache__", ".pytest_cache", "node_modules", ".next", ".venv", "focos.egg-info"}
GITIGNORE = """# python
.venv/
__pycache__/
*.pyc
*.egg-info/
.pytest_cache/
dist/

# node
node_modules/
dashboard/.next/
dashboard/out/

# secrets and local state (this repo is code only; households keep data in their own folder)
.env
.env.*
!.env.example
/config/
/state/
/reports/
/data/
/sure/
agent/settings.headless.json
agent/mcp.json
agent/system.rendered.md
"""


def copy_tree(src: Path, dst: Path) -> int:
    n = 0
    if src.is_file():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        return 1
    for f in src.rglob("*"):
        if f.is_file() and not (SKIP_PARTS & set(f.relative_to(src).parts)) and f.suffix != ".pyc":
            target = dst / f.relative_to(src)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, target)
            n += 1
    return n


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dest")
    ap.add_argument("--patterns", help="local leak-pattern file for the scan (never copied)")
    ap.add_argument("--init-git", action="store_true", help="git init + first commit in the export")
    ap.add_argument("--force", action="store_true", help="overwrite a non-empty destination")
    args = ap.parse_args()
    dest = Path(args.dest).resolve()
    if dest.exists() and any(dest.iterdir()) and not args.force:
        print(f"{dest} is not empty (use --force)", file=sys.stderr)
        return 2
    if dest.exists() and args.force:
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    total = 0
    for rel in ALLOW:
        src = ROOT / rel
        if not src.exists():
            continue
        total += copy_tree(src, dest / rel)
    (dest / ".gitignore").write_text(GITIGNORE, encoding="utf-8")
    print(f"copied {total} files to {dest}")
    env = {**__import__("os").environ}
    if args.patterns:
        env["FOCOS_PRIVATE_PATTERNS"] = args.patterns
    r = subprocess.run([sys.executable, str(dest / "scripts" / "private_scan.py"), "--all", *(["--no-local"] if not args.patterns else [])] +
                       [str(p) for p in [dest]], cwd=dest, env=env)
    if r.returncode != 0:
        print("private scan found hits; fix them before publishing", file=sys.stderr)
        return 1
    if args.init_git:
        subprocess.run(["git", "init", "-q"], cwd=dest, check=True)
        subprocess.run(["git", "add", "-A"], cwd=dest, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "focos: initial public release"], cwd=dest, check=True)
        print("initialized git with one commit (author = your git config)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
