"""Upcoming games loader, market odds comparison, and similar game search.

Reads ``data/odds_live.csv`` to surface today's slate the way the Streamlit
app does. Falls back to an empty list when the odds pipeline has not been
run.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

import app.config  # noqa: F401 — path bootstrap
from app.config import DATA_DIR
from app.teams import map_to_abbr


ODDS_CSV = DATA_DIR / "odds_live.csv"


def load_upcoming_games() -> list[dict]:
    if not ODDS_CSV.exists():
        return []

    try:
        df = pd.read_csv(ODDS_CSV)
        if df.empty:
            return []

        df = df[df["MARKET"] == "h2h"].copy()
        df["COMMENCE_TIME"] = pd.to_datetime(df["COMMENCE_TIME"], utc=True, errors="coerce")
        df = df.dropna(subset=["COMMENCE_TIME"])
        df["LOCAL_COMMENCE_TIME"] = df["COMMENCE_TIME"].dt.tz_convert("America/New_York")

        now_local = pd.Timestamp.now(tz="America/New_York")
        df = df[df["LOCAL_COMMENCE_TIME"] >= (now_local - pd.Timedelta(hours=3))].copy()

        if df.empty:
            return []

        games = (
            df[["GAME_ID", "HOME_TEAM", "AWAY_TEAM", "LOCAL_COMMENCE_TIME"]]
            .drop_duplicates()
            .sort_values("LOCAL_COMMENCE_TIME")
        )

        out: list[dict] = []
        for _, row in games.iterrows():
            commence = row["LOCAL_COMMENCE_TIME"]
            home = row["HOME_TEAM"]
            away = row["AWAY_TEAM"]
            home_abbr = map_to_abbr(home)
            away_abbr = map_to_abbr(away)
            out.append({
                "game_id": row["GAME_ID"],
                "home_team": home,
                "away_team": away,
                "home_abbr": home_abbr,
                "away_abbr": away_abbr,
                "commence_time": commence.isoformat(),
                "commence_time_label": commence.strftime("%b %d %I:%M %p ET"),
                "label": f"{away} @ {home} ({commence.strftime('%b %d %I:%M %p ET')})",
            })
        return out
    except Exception:
        return []


def _american_to_prob(odds_val: Any) -> float | None:
    try:
        o = float(odds_val)
    except (TypeError, ValueError):
        return None
    if o > 0:
        return 100.0 / (o + 100.0)
    return abs(o) / (abs(o) + 100.0)


def market_consensus(home_team: str, away_team: str) -> dict | None:
    """Return averaged market probabilities across sampled bookmakers."""
    if not ODDS_CSV.exists():
        return None
    try:
        df = pd.read_csv(ODDS_CSV)
        df = df[df["MARKET"] == "h2h"].copy()
    except Exception:
        return None

    home_keyword = home_team.split()[-1].lower()
    rows = df[df["HOME_TEAM"].str.lower().str.contains(home_keyword, na=False)]
    if rows.empty:
        return None

    home_probs: list[float] = []
    away_probs: list[float] = []
    bookmakers: set[str] = set()

    for _, row in rows.iterrows():
        h = _american_to_prob(row.get("HOME_ODDS") or row.get("PRICE"))
        a = _american_to_prob(row.get("AWAY_ODDS"))
        if h is None or a is None:
            continue
        total = h + a
        if total <= 0:
            continue
        home_probs.append(h / total)
        away_probs.append(a / total)
        if row.get("BOOKMAKER"):
            bookmakers.add(str(row["BOOKMAKER"]))

    if not home_probs:
        return None

    return {
        "market_home_prob": sum(home_probs) / len(home_probs),
        "market_away_prob": sum(away_probs) / len(away_probs),
        "books_sampled": len(home_probs),
        "bookmakers": sorted(bookmakers),
    }


def similar_games_for_matchup(home_abbr: str, away_abbr: str) -> list[dict]:
    """Combine top-N similar games for both teams for the matchup view."""
    from app.services.data_tools import search_similar_games

    home_hits = search_similar_games(
        query_text=f"{home_abbr} home game recent form matchup",
        team=home_abbr, n_results=3,
    )
    away_hits = search_similar_games(
        query_text=f"{away_abbr} away game recent form matchup",
        team=away_abbr, n_results=2,
    )

    seen = set()
    combined: list[dict] = []
    for hit in (home_hits + away_hits):
        if not isinstance(hit, dict):
            continue
        key = (hit.get("game_description") or "")[:60]
        if key in seen:
            continue
        seen.add(key)
        combined.append(hit)
    return combined[:5]
