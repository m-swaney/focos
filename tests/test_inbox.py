"""state/inbox.jsonl lifecycle: pending -> consumed (shown a few runs) -> applied/answered/dismissed; compaction."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from focos import inbox, paths


def test_add_consume_resolve(initialized_home: Path):
    n = inbox.add("The withholding is fixed.", about={"type": "tax_agenda", "id": "fix_withholding"}, source="dashboard")
    assert n["id"].startswith("n_") and n["status"] == "pending" and n["about"] == {"type": "tax_agenda", "id": "fix_withholding"}
    assert [r["id"] for r in inbox.pending()] == [n["id"]]
    shown = inbox.consume("daily-2026-09-08-1")
    assert [r["id"] for r in shown] == [n["id"]] and shown[0]["status"] == "consumed" and shown[0]["consumed_count"] == 1
    assert inbox.pending() == []
    assert inbox.resolve(n["id"], "applied", "tax_agenda fix_withholding: status open -> done")["status"] == "applied"
    saved = inbox.get(n["id"])
    assert saved["status"] == "applied" and saved["resolved_ts"] and "done" in saved["resolution"]
    assert inbox.consume("daily-2026-09-09-1") == []  # resolved notes are not shown again


def test_unanswered_note_resurfaces_then_flags(initialized_home: Path):
    n = inbox.add("hello?")
    runs = [inbox.consume(f"run-{i}") for i in range(6)]
    assert [len(r) for r in runs] == [1, 1, 1, 1, 0, 0]
    assert inbox.get(n["id"])["consumed_count"] == inbox.MAX_SHOWINGS
    assert [r["id"] for r in inbox.unaddressed()] == [n["id"]]
    inbox.dismiss(n["id"])
    assert inbox.unaddressed() == [] and inbox.get(n["id"])["status"] == "dismissed"


def test_empty_note_rejected(initialized_home: Path):
    try:
        inbox.add("   ")
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError")
    assert not paths.INBOX.exists()


def test_bad_lines_are_skipped(initialized_home: Path):
    paths.INBOX.parent.mkdir(parents=True, exist_ok=True)
    paths.INBOX.write_text("not json\n" + json.dumps({"id": "n_1", "status": "pending", "text": "x", "ts": "2026-01-01T00:00:00"}) + "\n")
    assert [r["id"] for r in inbox.pending()] == ["n_1"]


def test_compact_archives_old_resolved(initialized_home: Path):
    old = inbox.add("old")
    new = inbox.add("new")
    inbox.resolve(old["id"], "answered", "ok")
    inbox.resolve(new["id"], "answered", "ok")
    rows = inbox.all_notes()
    for r in rows:
        if r["id"] == old["id"]:
            r["resolved_ts"] = (datetime.now(timezone.utc) - timedelta(days=120)).isoformat()
    inbox._write(rows)
    assert inbox.compact(days=90) == 1
    assert [r["id"] for r in inbox.all_notes()] == [new["id"]]
    arc = paths.INBOX.with_name("inbox.archive.jsonl").read_text().splitlines()
    assert len(arc) == 1 and json.loads(arc[0])["id"] == old["id"]
