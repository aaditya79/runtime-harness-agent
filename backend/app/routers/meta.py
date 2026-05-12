"""Misc info endpoints — model label, team list, health check."""

from typing import List

from fastapi import APIRouter

from app.config import has_anthropic_key, has_openai_key, llm_label
from app.teams import TEAMS, TEAM_LOGOS

router = APIRouter(prefix="/api/meta", tags=["meta"])


@router.get("/health")
def health() -> dict:
    return {
        "ok": True,
        "llm_configured": has_anthropic_key() or has_openai_key(),
        "llm_label": llm_label(),
    }


@router.get("/teams")
def teams() -> List[dict]:
    return [
        {"name": name, "abbr": abbr, "logo": TEAM_LOGOS.get(abbr, "")}
        for name, abbr in TEAMS.items()
    ]
