from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/doctor")


@router.get("")
def doctor():
    from ...doctor import checks

    return {"checks": [c.model_dump() for c in checks.run_all()]}


@router.post("/fix/{check_id}")
def fix(check_id: str):
    from ...doctor import checks

    return checks.fix(check_id)


@router.post("/diagnostics")
def diagnostics():
    from ...doctor import diagnostics as diag

    return {"path": str(diag.export())}
