"""Commit the data dir after a run using dulwich (no git binary required). Honors .gitignore."""
from __future__ import annotations

from pathlib import Path

from dulwich import porcelain
from dulwich.ignore import IgnoreFilterManager
from dulwich.repo import NotGitRepository, Repo

DEFAULT_PATHS = ("state", "reports", "config")
FALLBACK_AUTHOR = "focos <focos@localhost>"


def open_repo(home: Path) -> Repo | None:
    try:
        return Repo(str(home))
    except NotGitRepository:
        return None


def ensure_repo(home: Path) -> Repo:
    repo = open_repo(home)
    if repo is None:
        repo = porcelain.init(str(home))
    return repo


def _author(repo: Repo, name: str | None, email: str | None) -> bytes:
    if name and email:
        return f"{name} <{email}>".encode()
    try:
        cfg = repo.get_config_stack()
        n = cfg.get((b"user",), b"name").decode()
        e = cfg.get((b"user",), b"email").decode()
        return f"{n} <{e}>".encode()
    except KeyError:
        return FALLBACK_AUTHOR.encode()


def _candidate_files(home: Path, subpaths: tuple[str, ...], ignore: IgnoreFilterManager) -> set[str]:
    out: set[str] = set()
    for sub in subpaths:
        base = home / sub
        if base.is_file():
            rel = base.relative_to(home).as_posix()
            if not ignore.is_ignored(rel):
                out.add(rel)
            continue
        if not base.is_dir():
            continue
        for f in base.rglob("*"):
            if not f.is_file() or ".git" in f.parts:
                continue
            rel = f.relative_to(home).as_posix()
            if ignore.is_ignored(rel) or ignore.is_ignored(rel.rsplit("/", 1)[0] + "/"):
                continue
            out.add(rel)
    return out


def commit_run(home: Path, message: str, subpaths: tuple[str, ...] = DEFAULT_PATHS, author_name: str | None = None,
               author_email: str | None = None, push: bool = False) -> str | None:
    """Stage changes (adds, edits, deletes) under subpaths and commit. Returns the short sha, or None when
    nothing changed."""
    repo = open_repo(home)
    if repo is None:
        return None
    ignore = IgnoreFilterManager.from_repo(repo)
    files = _candidate_files(home, subpaths, ignore)
    index = repo.open_index()
    prefixes = tuple(s.rstrip("/") + "/" for s in subpaths)
    tracked = {p.decode("utf-8") for p in index if p.decode("utf-8").startswith(prefixes) or p.decode("utf-8") in subpaths}
    existing = sorted(f for f in files | tracked if (home / f).is_file())
    missing = sorted(t for t in tracked if not (home / t).is_file())
    if not existing and not missing:
        return None
    if existing:
        porcelain.add(repo, [str(home / f) for f in existing])  # absolute: dulwich resolves relative paths against cwd
    if missing:
        porcelain.remove(repo, missing, cached=True)
    index = repo.open_index()
    new_tree = index.commit(repo.object_store)
    try:
        head_tree = repo[repo.head()].tree
    except KeyError:
        head_tree = None
    if head_tree == new_tree:
        return None
    author = _author(repo, author_name, author_email)
    sha = porcelain.commit(repo, message=message.encode("utf-8"), author=author, committer=author)
    if push:
        try:
            porcelain.push(repo, "origin")
        except Exception:  # no remote, no network: the local commit is what matters
            pass
    return sha.decode()[:7]


def status_summary(home: Path) -> dict:
    repo = open_repo(home)
    if repo is None:
        return {"repo": False}
    try:
        head = repo.head().decode()[:7]
    except KeyError:
        head = None
    st = porcelain.status(repo, untracked_files="no")
    return {"repo": True, "head": head, "staged": {k: [p.decode() for p in v] for k, v in st.staged.items()},
            "unstaged": [p.decode() if isinstance(p, bytes) else p for p in st.unstaged]}
