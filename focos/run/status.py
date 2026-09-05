"""state/status.json: last run per mode, read by the dashboard."""
from __future__ import annotations

from datetime import datetime, timezone

from .. import paths, settings


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _load() -> dict:
    return settings.read_json(paths.STATUS, {}) or {}


def start(mode: str, run_id: str) -> None:
    s = _load()
    s[mode] = {"run_id": run_id, "started": _now(), "finished": None, "ok": None, "stage": "A",
               "error": None, "cost_usd": 0.0, "stages": {}}
    settings.write_json(paths.STATUS, s)


def stage(mode: str, stage_name: str, ok: bool, error: str | None = None, cost_usd: float | None = None,
          extra: dict | None = None) -> None:
    s = _load()
    entry = s.setdefault(mode, {})
    entry["stage"] = stage_name
    entry.setdefault("stages", {})[stage_name] = {"ok": ok, "error": error, "at": _now(), **(extra or {})}
    if cost_usd:
        entry["cost_usd"] = round(float(entry.get("cost_usd") or 0) + float(cost_usd), 4)
    if not ok:
        entry["ok"] = False
        entry["error"] = f"{stage_name}: {error}"
        entry["finished"] = _now()
    settings.write_json(paths.STATUS, s)


def finish(mode: str, ok: bool, error: str | None = None, summary_line: str | None = None,
           report_path: str | None = None, commit: str | None = None) -> None:
    s = _load()
    entry = s.setdefault(mode, {})
    entry.update({"finished": _now(), "ok": ok if entry.get("ok") is not False else False,
                  "error": error or entry.get("error"), "summary_line": summary_line,
                  "report_path": report_path, "commit": commit})
    settings.write_json(paths.STATUS, s)


def get() -> dict:
    return _load()
