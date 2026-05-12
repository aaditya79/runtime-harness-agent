"""Pipeline trigger + status endpoints."""

from fastapi import APIRouter, HTTPException

from app.services import pipelines as pl

router = APIRouter(prefix="/api/pipelines", tags=["pipelines"])


@router.get("/status")
def status_all() -> dict:
    """All pipelines, indexed by name."""
    return pl.get_status()


@router.get("/status/{name}")
def status_one(name: str) -> dict:
    res = pl.get_status(name)
    if isinstance(res, dict) and res.get("error"):
        raise HTTPException(status_code=404, detail=res["error"])
    return res


@router.post("/{name}")
def start(name: str) -> dict:
    """Kick off a pipeline. Idempotent — running calls return the live job."""
    if name not in pl.PIPELINES:
        raise HTTPException(status_code=404, detail=f"Unknown pipeline: {name}")
    return pl.start_pipeline(name)


# Back-compat alias for the original odds endpoint.
@router.post("/odds-legacy")
def odds_legacy() -> dict:
    """Back-compat: same as POST /api/pipelines/odds."""
    return pl.start_pipeline("odds")
