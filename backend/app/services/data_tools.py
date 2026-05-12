"""Thin wrappers around the existing tool functions in nba_agent.py.

Each wrapper parses the JSON the tool returns into native Python objects
so the API can hand back structured JSON instead of pre-serialized strings.
"""

from __future__ import annotations

import json
from typing import Any

import app.config  # noqa: F401 — sets sys.path / cwd so root-level imports work

from nba_agent import (  # type: ignore
    tool_get_team_stats,
    tool_get_head_to_head,
    tool_get_injuries,
    tool_get_odds,
    tool_search_similar_games,
    tool_get_team_sentiment,
)


def _safe_load(raw: str, default: Any) -> Any:
    """Tools return JSON on success and a plain error message on failure."""
    if isinstance(raw, (dict, list)):
        return raw
    if not isinstance(raw, str):
        return default
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return default


def get_team_stats(team_abbr: str) -> dict:
    return _safe_load(tool_get_team_stats(team_abbr), {})


def get_head_to_head(team1_abbr: str, team2_abbr: str) -> dict:
    return _safe_load(tool_get_head_to_head(team1_abbr, team2_abbr), {})


def get_injuries(team_name: str) -> list[dict]:
    raw = tool_get_injuries(team_name)
    parsed = _safe_load(raw, [])
    if not isinstance(parsed, list):
        return []
    cleaned = []
    for inj in parsed:
        if not isinstance(inj, dict):
            continue
        # Drop rows where both player and status are blank/NaN — the
        # Streamlit app does the same trim.
        player = (inj.get("player") or "").strip()
        status = (inj.get("status") or "").strip()
        if not player and not status:
            continue
        cleaned.append({
            "team": inj.get("team", ""),
            "player": player or "Unknown",
            "position": inj.get("position", ""),
            "status": status,
            "est_return": inj.get("est_return", ""),
            "comment": inj.get("comment", ""),
        })
    return cleaned


def get_team_sentiment(team_abbr: str) -> dict:
    return _safe_load(tool_get_team_sentiment(team_abbr), {})


def get_odds(home_team: str | None = None, away_team: str | None = None) -> list[dict]:
    raw = tool_get_odds(home_team=home_team, away_team=away_team)
    parsed = _safe_load(raw, [])
    return parsed if isinstance(parsed, list) else []


def search_similar_games(query_text: str, team: str | None = None, n_results: int = 5) -> list[dict]:
    raw = tool_search_similar_games(query_text=query_text, team=team, n_results=n_results)
    parsed = _safe_load(raw, [])
    return parsed if isinstance(parsed, list) else []
