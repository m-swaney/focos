"""state/inbox.jsonl: notes the owner leaves for their chief of staff from the dashboard or `focos note`.

Each note is one JSON object per line. Lifecycle: pending (written by the owner) -> consumed (a brief run read it)
-> applied (an update cited it) | answered (a reply cited it). A consumed note is shown to the model again for a
few more runs; after that the dashboard flags it as not addressed. `dismissed` is owner-only. Resolved notes older
than RETENTION_DAYS move to state/inbox.archive.jsonl.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

from . import paths

STATUSES = ("pending", "consumed", "applied", "answered", "dismissed")
RESOLVED = ("applied", "answered", "dismissed")
MAX_SHOWINGS = 4          # first run + three more before the dashboard says "not addressed"
RETENTION_DAYS = 90


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _read(path=None) -> list[dict]:
    p = path or paths.INBOX
    if not p.exists():
        return []
    rows = []
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and row.get("id"):
            rows.append(row)
    return rows


def _write(rows: list[dict]) -> None:
    paths.INBOX.parent.mkdir(parents=True, exist_ok=True)
    paths.INBOX.write_text("".join(json.dumps(r, default=str) + "\n" for r in rows), encoding="utf-8")


def add(text: str, about: dict | None = None, source: str = "cli") -> dict:
    text = (text or "").strip()
    if not text:
        raise ValueError("a note needs some text")
    note = {"id": f"n_{uuid.uuid4().hex[:8]}", "ts": _now(), "source": source, "text": text[:4000],
            "about": _about(about), "status": "pending", "consumed_run": None, "consumed_count": 0,
            "resolved_ts": None, "resolution": None}
    paths.INBOX.parent.mkdir(parents=True, exist_ok=True)
    with paths.INBOX.open("a", encoding="utf-8") as f:
        f.write(json.dumps(note, default=str) + "\n")
    return note


def _about(about: dict | None) -> dict | None:
    if not isinstance(about, dict) or not about.get("type"):
        return None
    out = {"type": str(about["type"])[:32]}
    if about.get("id") is not None:
        out["id"] = str(about["id"])[:120]
    return out


def all_notes() -> list[dict]:
    return _read()


def pending() -> list[dict]:
    return [r for r in _read() if r.get("status") == "pending"]


def recent(n: int = 20) -> list[dict]:
    return _read()[-n:]


def get(note_id: str) -> dict | None:
    return next((r for r in _read() if r["id"] == note_id), None)


def consume(run_id: str) -> list[dict]:
    """Mark pending notes as consumed by this run and return what the model should see: those, plus notes an
    earlier run consumed without applying or answering (shown up to MAX_SHOWINGS times in total)."""
    rows = _read()
    show: list[dict] = []
    changed = False
    for r in rows:
        if r.get("status") == "pending":
            r.update(status="consumed", consumed_run=run_id, consumed_count=1)
            show.append(r)
            changed = True
        elif r.get("status") == "consumed" and int(r.get("consumed_count") or 0) < MAX_SHOWINGS:
            r["consumed_count"] = int(r.get("consumed_count") or 0) + 1
            r["consumed_run"] = run_id
            show.append(r)
            changed = True
    if changed:
        _write(rows)
    return show


def resolve(note_id: str, status: str, resolution: str | None = None) -> dict | None:
    if status not in RESOLVED:
        raise ValueError(f"status must be one of {RESOLVED}")
    rows = _read()
    hit = None
    for r in rows:
        if r["id"] == note_id:
            r.update(status=status, resolved_ts=_now(), resolution=(resolution or "")[:1000] or None)
            hit = r
    if hit:
        _write(rows)
    return hit


def dismiss(note_id: str) -> dict | None:
    return resolve(note_id, "dismissed", "dismissed by the owner")


def unaddressed() -> list[dict]:
    """Consumed notes the model neither applied nor answered after MAX_SHOWINGS runs."""
    return [r for r in _read() if r.get("status") == "consumed" and int(r.get("consumed_count") or 0) >= MAX_SHOWINGS]


def compact(days: int = RETENTION_DAYS) -> int:
    """Move resolved notes older than `days` to state/inbox.archive.jsonl. Returns how many moved."""
    rows = _read()
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    keep, archive = [], []
    for r in rows:
        ts = r.get("resolved_ts") or r.get("ts")
        try:
            when = datetime.fromisoformat(str(ts))
            if when.tzinfo is None:
                when = when.astimezone()
        except (TypeError, ValueError):
            when = None
        if r.get("status") in RESOLVED and when is not None and when < cutoff:
            archive.append(r)
        else:
            keep.append(r)
    if archive:
        arc = paths.INBOX.with_name("inbox.archive.jsonl")
        with arc.open("a", encoding="utf-8") as f:
            for r in archive:
                f.write(json.dumps(r, default=str) + "\n")
        _write(keep)
    return len(archive)
