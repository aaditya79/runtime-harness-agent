"""Research / backtest endpoints."""

import asyncio
import json
from typing import AsyncIterator, List

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.services import backtest as bt

router = APIRouter(prefix="/api/backtest", tags=["backtest"])


@router.get("/summary")
def summary() -> dict:
    return {
        "summary": bt.load_summary(),
        "metadata": bt.load_metadata(),
    }


@router.get("/predictions")
def predictions() -> List[dict]:
    return bt.load_predictions()


@router.get("/calibration")
def calibration() -> List[dict]:
    return bt.load_calibration()


@router.get("/ablations")
def ablations() -> List[dict]:
    return bt.load_ablations()


class RunRequest(BaseModel):
    n_games: int = 25
    season: str = "2025-26"
    min_history: int = 10


@router.post("/run")
def run(req: RunRequest) -> dict:
    """Kick off a backtest in the background.

    Idempotent: a second call while a job is running returns the running
    job's snapshot without spawning a duplicate. The script's own
    per-(game, method) cache under ``data/backtest_cache/`` keeps repeats
    cheap.
    """
    if req.n_games < 1 or req.n_games > 500:
        raise HTTPException(status_code=400, detail="n_games out of range")
    return bt.start_backtest(req.n_games, req.season, req.min_history)


@router.get("/status")
def status() -> dict:
    """Poll the current backtest job. Returns the same shape as ``/run``'s
    ``status`` payload — useful when SSE is not available.
    """
    return bt.get_job_status()


@router.get("/stream")
async def stream():
    """Live stream of the running backtest's stdout via SSE.

    On connect: emits a ``snapshot`` event with whatever is already in the
    ring buffer, then live-streams ``line`` events until the job ends with
    a final ``done`` event. If no job is running, emits ``snapshot`` +
    ``done`` and closes.
    """
    loop = asyncio.get_event_loop()

    async def event_generator() -> AsyncIterator[str]:
        gen = bt.stream_lines()
        # Initial heartbeat keeps the browser EventSource happy.
        yield ": connected\n\n"
        while True:
            evt = await loop.run_in_executor(None, _next_or_none, gen)
            if evt is None:
                break
            payload = json.dumps(evt)
            yield f"data: {payload}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


def _next_or_none(gen):
    try:
        return next(gen)
    except StopIteration:
        return None


@router.get("/simulate")
def simulate(
    method: str = "All",
    edge_threshold: float = Query(0.05, ge=0.0, le=0.5),
    side_filter: str = "Both",
    min_confidence: float = Query(0.5, ge=0.0, le=1.0),
) -> dict:
    return bt.simulate_roi(
        method=method,
        edge_threshold=edge_threshold,
        side_filter=side_filter,
        min_confidence=min_confidence,
    )
