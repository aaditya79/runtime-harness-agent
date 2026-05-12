"""Game / matchup endpoints."""

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query

from app.services import data_tools
from app.services.games import (
    load_upcoming_games,
    market_consensus,
    similar_games_for_matchup,
)
from app.teams import TEAM_LOGOS, map_to_abbr

router = APIRouter(prefix="/api/games", tags=["games"])


@router.get("/upcoming")
def upcoming() -> List[dict]:
    return load_upcoming_games()


@router.get("/team-stats")
def team_stats(team: str = Query(..., description="Team abbreviation, e.g. LAL")) -> dict:
    abbr = team if len(team) <= 3 else (map_to_abbr(team) or team)
    if not abbr:
        raise HTTPException(status_code=400, detail="Unknown team")
    return data_tools.get_team_stats(abbr)


@router.get("/injuries")
def injuries(team: str) -> List[dict]:
    return data_tools.get_injuries(team)


@router.get("/sentiment")
def sentiment(team: str) -> dict:
    abbr = team if len(team) <= 3 else (map_to_abbr(team) or team)
    return data_tools.get_team_sentiment(abbr)


@router.get("/head-to-head")
def head_to_head(home: str, away: str) -> dict:
    home_abbr = home if len(home) <= 3 else (map_to_abbr(home) or home)
    away_abbr = away if len(away) <= 3 else (map_to_abbr(away) or away)
    return data_tools.get_head_to_head(home_abbr, away_abbr)


@router.get("/odds")
def odds(home: Optional[str] = None, away: Optional[str] = None) -> List[dict]:
    return data_tools.get_odds(home_team=home, away_team=away)


@router.get("/market-consensus")
def consensus(home: str, away: str) -> dict:
    """Average market probabilities for the home/away side across bookmakers."""
    result = market_consensus(home, away)
    if result is None:
        return {"available": False}
    return {"available": True, **result}


@router.get("/similar")
def similar(
    home_abbr: str,
    away_abbr: str,
) -> List[dict]:
    return similar_games_for_matchup(home_abbr, away_abbr)


@router.get("/matchup")
def matchup(home: str, away: str) -> dict:
    """Bundle the snapshot the React UI needs in one round trip."""
    home_abbr = home if len(home) <= 3 else (map_to_abbr(home) or home)
    away_abbr = away if len(away) <= 3 else (map_to_abbr(away) or away)
    if not home_abbr or not away_abbr:
        raise HTTPException(status_code=400, detail="Unknown team(s)")

    return {
        "home_abbr": home_abbr,
        "away_abbr": away_abbr,
        "home_logo": TEAM_LOGOS.get(home_abbr, ""),
        "away_logo": TEAM_LOGOS.get(away_abbr, ""),
        "home_stats": data_tools.get_team_stats(home_abbr),
        "away_stats": data_tools.get_team_stats(away_abbr),
        "home_injuries": data_tools.get_injuries(home),
        "away_injuries": data_tools.get_injuries(away),
        "home_sentiment": data_tools.get_team_sentiment(home_abbr),
        "away_sentiment": data_tools.get_team_sentiment(away_abbr),
    }
