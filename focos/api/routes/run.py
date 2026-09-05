"""Start a run in a background thread and poll its log; one run at a time."""
from __future__ import annotations

import threading
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ... import paths
from ...orchestrator import run as orch
from ...run import status as run_status

router = APIRouter(prefix="/run")
_RUNS: dict[str, dict] = {}
_LOCK = threading.Lock()


class Start(BaseModel):
    mode: str = "daily"
    skip_a: bool = False
    skip_b: bool = False
    skip_c: bool = False
    no_git: bool = False


def _worker(run_id: str, opts: orch.RunOptions) -> None:
    rec = _RUNS[run_id]
    try:
        res = orch.run(opts)
        rec.update({"ok": res.ok, "stages": res.stages, "commit": res.commit, "log_file": res.log_file, "run_id": res.run_id})
    except Exception as e:  # noqa: BLE001
        rec.update({"ok": False, "error": f"{type(e).__name__}: {str(e)[:300]}"})
    finally:
        rec["finished"] = datetime.now().astimezone().isoformat(timespec="seconds")


@router.post("")
def start(body: Start):
    if body.mode not in ("daily", "weekly", "monthly"):
        raise HTTPException(400, "mode must be daily, weekly, or monthly")
    with _LOCK:
        if any(r.get("finished") is None for r in _RUNS.values()):
            raise HTTPException(409, "a run is already in progress")
        run_id = f"api-{body.mode}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        _RUNS[run_id] = {"id": run_id, "mode": body.mode, "started": datetime.now().astimezone().isoformat(timespec="seconds"),
                         "finished": None}
    opts = orch.RunOptions(mode=body.mode, skip_a=body.skip_a, skip_b=body.skip_b, skip_c=body.skip_c, no_git=body.no_git)
    threading.Thread(target=_worker, args=(run_id, opts), name=run_id, daemon=True).start()
    return {"id": run_id, "started": _RUNS[run_id]["started"]}


def _tail(path: str | None, lines: int = 60) -> list[str]:
    if not path or not Path(path).exists():
        return []
    return Path(path).read_text(encoding="utf-8", errors="replace").splitlines()[-lines:]


@router.get("/latest")
def latest():
    return {"status": run_status.get(), "runs": sorted(_RUNS.values(), key=lambda r: r["started"])[-5:]}


@router.get("/{run_id}")
def get(run_id: str):
    rec = _RUNS.get(run_id)
    if rec is None:
        raise HTTPException(404, "unknown run")
    log_file = rec.get("log_file")
    if not log_file:
        cands = sorted(paths.LOGS.glob(f"*-{rec['mode']}-run.log")) if paths.LOGS.exists() else []
        log_file = str(cands[-1]) if cands else None
    return {**rec, "log": _tail(log_file), "status": run_status.get().get(rec["mode"])}
