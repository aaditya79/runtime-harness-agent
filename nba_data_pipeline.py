"""
Step 1: NBA Data Pipeline
Pulls historical game data from nba_api, structures it, and saves to CSV files.
These CSVs will later feed into the ChromaDB vector store (Step 6) and the agent tools (Step 7).

Usage:
    python nba_data_pipeline.py

Output files:
    data/game_logs.csv        - Every game with box score stats and metadata
    data/team_stats.csv       - Season-level team stats (offensive/defensive rating, pace, etc.)
    data/standings.csv        - Current and historical standings
    data/head_to_head.csv     - Head-to-head records between all team pairs
"""

import os
import time
import pandas as pd
from datetime import datetime
from nba_api.stats.endpoints import (
    leaguegamefinder,
    teamestimatedmetrics,
    leaguestandings,
    teamgamelog,
)
from nba_api.stats.static import teams

# ============================================================
# CONFIG
# ============================================================

def get_current_nba_season():
    """
    Return the current NBA season string.
    Examples:
      Apr 2026 -> '2025-26'
      Nov 2026 -> '2026-27'
    """
    now = datetime.now()
    if now.month >= 10:
        start_year = now.year
    else:
        start_year = now.year - 1
    end_year_short = str(start_year + 1)[-2:]
    return f"{start_year}-{end_year_short}"


def get_recent_nba_seasons(n_seasons=4):
    """
    Return the most recent n NBA seasons ending with the current season.
    Example in Apr 2026:
      ['2022-23', '2023-24', '2024-25', '2025-26']
    """
    current_season = get_current_nba_season()
    start_year = int(current_season.split("-")[0])

    seasons = []
    for y in range(start_year - (n_seasons - 1), start_year + 1):
        seasons.append(f"{y}-{str(y + 1)[-2:]}")
    return seasons


USE_FIXED_SEASONS = True

if USE_FIXED_SEASONS:
    SEASONS = [
        "2017-18",
        "2018-19",
        "2019-20",
        "2020-21",
        "2021-22",
        "2022-23",
        "2023-24",
        "2024-25",
        "2025-26",
    ]
else:
    SEASONS = get_recent_nba_seasons(4)
    
DATA_DIR = "data"
SLEEP_BETWEEN_CALLS = 0.6  # nba.com rate limiting - be polite

os.makedirs(DATA_DIR, exist_ok=True)


def get_all_teams():
    """Get all 30 NBA teams with IDs and abbreviations."""
    all_teams = teams.get_teams()
    return pd.DataFrame(all_teams)


def pull_game_logs(seasons):
    """
    Pull game-level data for all teams across multiple seasons.
    Each row = one team's performance in one game.
    Two rows per game (one per team).
    """
    print("Pulling game logs...")
    all_games = []

    # Pull regular season + playoffs separately and tag each row so
    # downstream consumers can filter or weight playoff games (the most
    # informative precedent for betting models).
    season_types = ["Regular Season", "Playoffs"]

    for season in seasons:
        print(f"  Season: {season}")
        for season_type in season_types:
            try:
                finder = leaguegamefinder.LeagueGameFinder(
                    season_nullable=season,
                    league_id_nullable="00",  # NBA
                    season_type_nullable=season_type,
                )
                games = finder.get_data_frames()[0]
                if games.empty:
                    continue
                games["SEASON"] = season
                games["SEASON_TYPE"] = season_type
                all_games.append(games)
                time.sleep(SLEEP_BETWEEN_CALLS)
            except Exception as e:
                print(f"    Error pulling {season} ({season_type}): {e}")
                time.sleep(2)

    if not all_games:
        print("No game data pulled. Check your connection.")
        return pd.DataFrame()

    df = pd.concat(all_games, ignore_index=True)

    # Add useful metadata columns
    df["GAME_DATE"] = pd.to_datetime(df["GAME_DATE"])
    df["HOME"] = df["MATCHUP"].str.contains("vs.").astype(int)
    df["WIN"] = (df["WL"] == "W").astype(int)

    # Sort by date
    df = df.sort_values("GAME_DATE").reset_index(drop=True)

    print(f"  Total game rows: {len(df)} ({len(df)//2} games)")
    return df


def add_schedule_context(df):
    """
    Add back-to-back flags and rest days for each team.
    This is key metadata for the vector store.
    """
    print("Adding schedule context (B2B, rest days)...")
    df = df.sort_values(["TEAM_ID", "GAME_DATE"]).reset_index(drop=True)

    # Calculate days since last game per team
    df["PREV_GAME_DATE"] = df.groupby("TEAM_ID")["GAME_DATE"].shift(1)
    df["REST_DAYS"] = (df["GAME_DATE"] - df["PREV_GAME_DATE"]).dt.days
    df["BACK_TO_BACK"] = (df["REST_DAYS"] == 1).astype(int)

    # Rolling form: win percentage over last 10 games, isolated per season
    # so end-of-season form does not bleed into the next season's opener
    # (different roster, different team).
    df = df.sort_values(["TEAM_ID", "SEASON", "GAME_DATE"]).reset_index(drop=True)
    df["ROLLING_WIN_PCT"] = (
        df.groupby(["TEAM_ID", "SEASON"])["WIN"]
        .transform(lambda x: x.rolling(10, min_periods=1).mean())
    )

    df = df.drop(columns=["PREV_GAME_DATE"])
    return df


def pull_team_advanced_stats(seasons):
    """
    Pull team-level advanced stats (offensive rating, defensive rating, pace, etc.)
    per season.
    """
    print("Pulling team advanced stats...")
    all_stats = []

    for season in seasons:
        print(f"  Season: {season}")
        try:
            metrics = teamestimatedmetrics.TeamEstimatedMetrics(season=season)
            stats = metrics.get_data_frames()[0]
            stats["SEASON"] = season
            all_stats.append(stats)
            time.sleep(SLEEP_BETWEEN_CALLS)
        except Exception as e:
            print(f"    Error pulling {season}: {e}")
            time.sleep(2)

    if not all_stats:
        return pd.DataFrame()

    df = pd.concat(all_stats, ignore_index=True)
    print(f"  Total team-season rows: {len(df)}")
    return df


def pull_standings(seasons):
    """Pull standings for each season."""
    print("Pulling standings...")
    all_standings = []

    for season in seasons:
        print(f"  Season: {season}")
        try:
            standings = leaguestandings.LeagueStandings(season=season)
            s = standings.get_data_frames()[0]
            s["SEASON"] = season
            all_standings.append(s)
            time.sleep(SLEEP_BETWEEN_CALLS)
        except Exception as e:
            print(f"    Error pulling {season}: {e}")
            time.sleep(2)

    if not all_standings:
        return pd.DataFrame()

    df = pd.concat(all_standings, ignore_index=True)
    print(f"  Total standings rows: {len(df)}")
    return df


def build_head_to_head(game_logs):
    """
    Build head-to-head records between all team pairs.
    For each pair, calculate wins, losses, and average point differential.
    """
    print("Building head-to-head records...")

    # Parse opponent from MATCHUP string
    def extract_opponent(row):
        matchup = row["MATCHUP"]
        if "vs." in matchup:
            return matchup.split("vs. ")[1].strip()
        elif "@" in matchup:
            return matchup.split("@ ")[1].strip()
        return None

    df = game_logs.copy()
    df["OPPONENT_ABB"] = df.apply(extract_opponent, axis=1)

    # Aggregate H2H stats
    h2h = (
        df.groupby(["TEAM_ABBREVIATION", "OPPONENT_ABB", "SEASON"])
        .agg(
            GAMES=("GAME_ID", "count"),
            WINS=("WIN", "sum"),
            AVG_PTS=("PTS", "mean"),
            AVG_PLUS_MINUS=("PLUS_MINUS", "mean"),
        )
        .reset_index()
    )
    h2h["LOSSES"] = h2h["GAMES"] - h2h["WINS"]
    h2h["WIN_PCT"] = h2h["WINS"] / h2h["GAMES"]

    print(f"  Total H2H records: {len(h2h)}")
    return h2h


def main():
    print("=" * 60)
    print("NBA Data Pipeline - Step 1")
    print("=" * 60)
    print(f"Pulling data for seasons: {SEASONS}")
    print()

    # 1. Get team info
    team_info = get_all_teams()
    team_info.to_csv(f"{DATA_DIR}/teams.csv", index=False)
    print(f"Saved {len(team_info)} teams to {DATA_DIR}/teams.csv")
    print()

    # 2. Pull game logs
    game_logs = pull_game_logs(SEASONS)
    if game_logs.empty:
        print("Failed to pull game logs. Exiting.")
        return

    # 3. Add schedule context
    game_logs = add_schedule_context(game_logs)
    game_logs.to_csv(f"{DATA_DIR}/game_logs.csv", index=False)
    print(f"Saved game logs to {DATA_DIR}/game_logs.csv")
    print()

    # 4. Pull team advanced stats
    team_stats = pull_team_advanced_stats(SEASONS)
    if not team_stats.empty:
        team_stats.to_csv(f"{DATA_DIR}/team_stats.csv", index=False)
        print(f"Saved team stats to {DATA_DIR}/team_stats.csv")
    print()

    # 5. Pull standings
    standings = pull_standings(SEASONS)
    if not standings.empty:
        standings.to_csv(f"{DATA_DIR}/standings.csv", index=False)
        print(f"Saved standings to {DATA_DIR}/standings.csv")
    print()

    # 6. Build H2H records
    h2h = build_head_to_head(game_logs)
    h2h.to_csv(f"{DATA_DIR}/head_to_head.csv", index=False)
    print(f"Saved H2H records to {DATA_DIR}/head_to_head.csv")
    print()

    # Summary
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Seasons covered: {SEASONS}")
    print(f"Total games: {len(game_logs) // 2}")
    print(f"Teams: {game_logs['TEAM_ABBREVIATION'].nunique()}")
    print(f"Date range: {game_logs['GAME_DATE'].min().date()} to {game_logs['GAME_DATE'].max().date()}")
    print()
    print(f"Files saved to {DATA_DIR}/:")
    for f in os.listdir(DATA_DIR):
        size = os.path.getsize(f"{DATA_DIR}/{f}") / 1024
        print(f"  {f}: {size:.1f} KB")
    print()
    print("Next step: Run step 2 (nbainjuries) to pull injury data.")


if __name__ == "__main__":
    main()