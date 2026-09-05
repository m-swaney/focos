"""Holdings sources: where brokerage positions come from (Robinhood via Claude MCP, SimpleFIN holdings, a CSV,
or nothing). Every source produces the same normalized snapshot dict, so analytics never care."""
from __future__ import annotations

from pathlib import Path

from .. import paths, settings
from .base import HoldingsSource, SourceError, empty_snapshot  # noqa: F401


def snapshot_files() -> list[Path]:
    """Snapshots by date, newest last. The source-neutral folder wins over the legacy robinhood/ folder."""
    files: dict[str, Path] = {}
    for d in (paths.SNAPSHOTS_RH, paths.SNAPSHOTS_HOLDINGS):
        if d.exists():
            files.update({f.name: f for f in d.glob("*.json")})
    return [files[k] for k in sorted(files)]


def latest_two() -> tuple[dict | None, dict | None]:
    files = snapshot_files()
    cur = settings.read_json(files[-1]) if files else None
    prev = settings.read_json(files[-2]) if len(files) > 1 else None
    return cur, prev


def write_snapshot(snap: dict) -> Path:
    p = paths.SNAPSHOTS_HOLDINGS / f"{snap['date']}.json"
    settings.write_json(p, snap)
    return p


def current(name: str | None = None) -> HoldingsSource:
    name = name or (settings.focos().get("holdings") or {}).get("source") or "none"
    if name == "robinhood_mcp":
        from .robinhood_mcp import RobinhoodMCPSource
        return RobinhoodMCPSource()
    if name == "csv":
        from .csv_source import CSVSource
        return CSVSource()
    if name == "simplefin_holdings":
        from .simplefin_holdings import SimpleFINHoldingsSource
        return SimpleFINHoldingsSource()
    from .none_source import NoneSource
    return NoneSource()
