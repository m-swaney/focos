"""Scan tracked files for secrets and personal data before anything leaves this machine.

Two layers:
  1. Generic detectors: API keys, tokens, private keys, credentials in URLs, e-mail addresses, long digit
     runs (account numbers), and SimpleFIN access URLs.
  2. Local patterns: one regex per line in the file named by FOCOS_PRIVATE_PATTERNS (default:
     <repo>/.git/leak_patterns). That file holds the household's own names, addresses, masks, and ids and
     is never committed; the public repo ships this script without it.

Usage:
  python scripts/private_scan.py            # code and docs that will be published
  python scripts/private_scan.py --all      # every tracked file (expect hits on a private data dir)
  python scripts/private_scan.py --staged   # what `git commit` would add (use as a pre-commit hook)
Exit 1 when anything matches.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

CODE_SCOPE = ("focos", "agent", "dashboard", "tests", "scripts", "installers", "pyproject.toml", "README.md",
              "CLAUDE.md", ".env.example", ".gitignore")
SKIP_SUFFIXES = {".png", ".jpg", ".jpeg", ".ico", ".svg", ".pkl", ".pyc", ".lock", ".woff", ".woff2", ".ttf", ".otf",
                 ".zip", ".sqlite", ".pdf"}
SKIP_NAMES = {"package-lock.json", "uv.lock", "private_scan.py"}

GENERIC = [
    ("anthropic key", re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}")),
    ("openai-style key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9]{20,}")),
    ("google api key", re.compile(r"\bAIza[0-9A-Za-z_\-]{30,}")),
    ("github token", re.compile(r"\b(?:ghp|gho|ghu|ghs|github_pat)_[A-Za-z0-9_]{20,}")),
    ("slack token", re.compile(r"\bxox[abpr]-[A-Za-z0-9\-]{10,}")),
    ("private key block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("credentials in url", re.compile(r"https?://[^\s/:@]+:[^\s/@]+@[^\s]+")),
    ("simplefin access url", re.compile(r"https?://[^\s/@]+@[^\s/]*simplefin\.org/simplefin[^\s]*")),
    ("e-mail address", re.compile(r"\b[A-Za-z0-9._%+\-]+@(?!example\.com|localhost|users\.noreply\.github\.com)[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")),
    ("uuid (ledger/sure account id)", re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b")),
    ("9+ digit run (account number?)", re.compile(r"(?<![\w.\-])\d{9,}(?![\w.\-])")),
]
ALLOW_LINE = re.compile(r"private-scan:\s*allow", re.I)
UNIX_TS = re.compile(r"^(1[5-9]|20)\d{8}$")            # 10-digit unix seconds, 2017-2033: a timestamp, not an account
PLACEHOLDER_CREDS = re.compile(r"://(u|user|alice|test|x|demo):(p|pw|pass|secret|password|y|demo)@", re.I)


def _false_positive(label: str, match: str, line: str) -> bool:
    if label.startswith("9+ digit") and UNIX_TS.match(match):
        return True
    if label in ("credentials in url", "simplefin access url", "e-mail address") and PLACEHOLDER_CREDS.search(line):
        return True
    return False


def tracked_files(staged: bool) -> list[str]:
    cmd = ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"] if staged else ["git", "ls-files"]
    out = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout
    return [l.strip() for l in out.splitlines() if l.strip()]


def in_scope(path: str, scope: tuple[str, ...] | None) -> bool:
    p = Path(path)
    if p.suffix.lower() in SKIP_SUFFIXES or p.name in SKIP_NAMES:
        return False
    if scope is None:
        return True
    return any(path == s or path.startswith(s.rstrip("/") + "/") for s in scope)


def load_local_patterns(explicit: str | None) -> list[tuple[str, re.Pattern]]:
    cand = explicit or os.environ.get("FOCOS_PRIVATE_PATTERNS")
    if not cand:
        try:
            gd = subprocess.run(["git", "rev-parse", "--git-common-dir"], capture_output=True, text=True, check=True).stdout.strip()
            cand = str(Path(gd) / "leak_patterns")
        except subprocess.CalledProcessError:
            return []
    p = Path(cand)
    if not p.exists():
        return []
    pats = []
    for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if line and not line.startswith("#"):
            try:
                pats.append((f"local pattern #{i}", re.compile(line, re.I)))
            except re.error:
                pass
    return pats


def scan_file(path: str, patterns: list[tuple[str, re.Pattern]]) -> list[tuple[str, int, str, str]]:
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except (OSError, UnicodeError):
        return []
    hits = []
    for n, line in enumerate(text.splitlines(), 1):
        if ALLOW_LINE.search(line):
            continue
        for label, rx in patterns:
            m = rx.search(line)
            if m and not _false_positive(label, m.group(0), line):
                shown = m.group(0)
                masked = shown[:4] + "..." + shown[-2:] if len(shown) > 10 else shown
                hits.append((path, n, label, masked))
    return hits


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--all", action="store_true", help="scan every tracked file, not just the code scope")
    ap.add_argument("--staged", action="store_true", help="scan staged changes only")
    ap.add_argument("--patterns", help="local patterns file (default: FOCOS_PRIVATE_PATTERNS or .git/leak_patterns)")
    ap.add_argument("--no-local", action="store_true", help="skip the local patterns file")
    ap.add_argument("paths", nargs="*", help="explicit files/dirs to scan instead of git-tracked files")
    args = ap.parse_args(argv)

    patterns = list(GENERIC) + ([] if args.no_local else load_local_patterns(args.patterns))
    if args.paths:
        files = []
        for p in args.paths:
            pp = Path(p)
            files += [str(f) for f in (pp.rglob("*") if pp.is_dir() else [pp]) if f.is_file()]
        scope = None
    else:
        files = tracked_files(args.staged)
        scope = None if (args.all or args.staged) else CODE_SCOPE
    hits = []
    for f in files:
        if in_scope(f, scope):
            hits.extend(scan_file(f, patterns))
    local_n = len(patterns) - len(GENERIC)
    print(f"private-scan: {len(files)} files, {len(GENERIC)} generic + {local_n} local patterns")
    if not hits:
        print("private-scan: clean")
        return 0
    for path, n, label, masked in hits:
        print(f"{path}:{n}: {label}: {masked}".encode("ascii", "backslashreplace").decode("ascii"))
    print(f"private-scan: {len(hits)} hit(s)")
    return 1


if __name__ == "__main__":
    sys.exit(main())
