"""Analysis endpoints — stream and run the three reasoning systems."""

from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.services.analysis import (
    MODE_RUNNERS,
    run_analysis_blocking,
    stream_analysis,
)
from app.services.llm import get_llm_callable

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


class AnalysisRequest(BaseModel):
    mode: str  # "single_agent" | "multi_agent" | "cot"
    home_team: str
    away_team: str
    home_abbr: str
    away_abbr: str
    game_date: str  # ISO date


def _game_description(req: AnalysisRequest) -> str:
    return f"{req.away_team} vs {req.home_team}, {req.game_date}"


@router.post("/stream")
async def stream(req: AnalysisRequest):
    """Run a single analysis mode and stream stdout lines via SSE."""
    if req.mode not in MODE_RUNNERS:
        raise HTTPException(status_code=400, detail=f"Unknown mode {req.mode}")

    llm_fn, _label = get_llm_callable()
    if llm_fn is None:
        raise HTTPException(status_code=503, detail="No LLM API key configured")

    description = _game_description(req)
    loop = asyncio.get_event_loop()

    async def event_generator() -> AsyncIterator[str]:
        gen = stream_analysis(
            req.mode,
            description,
            req.home_abbr,
            req.away_abbr,
            req.home_team,
            req.away_team,
            llm_fn,
        )
        # Initial heartbeat so the browser opens the connection promptly.
        yield ": connected\n\n"

        while True:
            item = await loop.run_in_executor(None, _next_or_none, gen)
            if item is None:
                break
            payload = json.dumps(item)
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


@router.post("/run")
def run(req: AnalysisRequest) -> dict:
    """Synchronous variant — used by the Compare All flow."""
    if req.mode not in MODE_RUNNERS:
        raise HTTPException(status_code=400, detail=f"Unknown mode {req.mode}")
    llm_fn, _label = get_llm_callable()
    if llm_fn is None:
        raise HTTPException(status_code=503, detail="No LLM API key configured")
    description = _game_description(req)
    return run_analysis_blocking(
        req.mode,
        description,
        req.home_abbr,
        req.away_abbr,
        req.home_team,
        req.away_team,
        llm_fn,
    )
