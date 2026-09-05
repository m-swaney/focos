from pathlib import Path

from dulwich import porcelain
from dulwich.repo import Repo

from focos.orchestrator import git_ops


def _repo(tmp_path: Path) -> Path:
    home = tmp_path / "h"
    home.mkdir()
    porcelain.init(str(home))
    (home / ".gitignore").write_text(".env\nstate/raw/\nstate/logs/\n")
    (home / "state" / "raw").mkdir(parents=True)
    (home / "state" / "logs").mkdir(parents=True)
    (home / "reports").mkdir()
    (home / "config").mkdir()
    return home


def test_commit_respects_gitignore_and_detects_no_change(tmp_path: Path):
    home = _repo(tmp_path)
    (home / ".env").write_text("SECRET=1")
    (home / "state" / "raw" / "dump.json").write_text("{\"account_number\": \"1\"}")
    (home / "state" / "logs" / "x.log").write_text("log")
    (home / "state" / "status.json").write_text("{}")
    (home / "reports" / "a.md").write_text("# a")
    (home / "config" / "profile.yml").write_text("version: 2\n")
    (home / "notes.txt").write_text("outside the committed paths")
    sha = git_ops.commit_run(home, "run: test", author_name="Tester", author_email="t@example.com")
    assert sha and len(sha) == 7
    repo = Repo(str(home))
    tree = repo[repo[repo.head()].tree]
    top = {name.decode() for name, _, _ in tree.iteritems()}
    assert top == {"state", "reports", "config"}
    state_tree = repo[tree[b"state"][1]]
    assert {n.decode() for n, _, _ in state_tree.iteritems()} == {"status.json"}  # raw/ and logs/ ignored
    assert repo[repo.head()].author == b"Tester <t@example.com>"
    assert git_ops.commit_run(home, "run: again", author_name="Tester", author_email="t@example.com") is None


def test_commit_stages_deletions_and_edits(tmp_path: Path):
    home = _repo(tmp_path)
    (home / "reports" / "a.md").write_text("v1")
    (home / "reports" / "b.md").write_text("v1")
    assert git_ops.commit_run(home, "one", author_name="T", author_email="t@example.com")
    (home / "reports" / "a.md").write_text("v2")
    (home / "reports" / "b.md").unlink()
    sha = git_ops.commit_run(home, "two", author_name="T", author_email="t@example.com")
    assert sha
    repo = Repo(str(home))
    reports = repo[repo[repo[repo.head()].tree][b"reports"][1]]
    assert {n.decode() for n, _, _ in reports.iteritems()} == {"a.md"}


def test_no_repo_returns_none(tmp_path: Path):
    assert git_ops.commit_run(tmp_path, "x") is None
    assert git_ops.status_summary(tmp_path) == {"repo": False}


def test_author_falls_back_to_repo_config(tmp_path: Path):
    home = _repo(tmp_path)
    repo = Repo(str(home))
    cfg = repo.get_config()
    cfg.set((b"user",), b"name", b"Owner")
    cfg.set((b"user",), b"email", b"owner@example.com")
    cfg.write_to_path()
    (home / "reports" / "a.md").write_text("x")
    git_ops.commit_run(home, "cfg")
    assert Repo(str(home))[Repo(str(home)).head()].author == b"Owner <owner@example.com>"
