"""
Step 3: NBA Odds Data Pipeline
Pulls betting odds from The Odds API (live) and Kaggle (historical).

Setup:
    1. Get a free API key from https://the-odds-api.com
    2. Set it as an environment variable: export ODDS_API_KEY="your_key_here"
    3. Download historical odds CSV from Kaggle:
       https://www.kaggle.com/datasets/erichqiu/nba-odds-and-scores
       Place it in data/kaggle_odds.csv (optional, for historical evaluation)

Usage:
    pip install requests pandas
    python nba_odds_pipeline.py

Output:
    data/odds_live.csv       - Current odds for upcoming games
    data/odds_historical.csv - Historical odds for evaluation (from Kaggle or API)
"""

import os
import json
import requests
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

# The Odds API config
ODDS_API_KEY = os.environ.get("ODDS_API_KEY", "")
ODDS_API_BASE = "https://api.the-odds-api.com/v4"
SPORT = "basketball_nba"


def pull_live_odds():
    """
    Pull current odds for upcoming NBA games from The Odds API.
    Uses 1 credit per call (moneyline, one region).
    """
    print("Pulling live odds from The Odds API...")

    if not ODDS_API_KEY:
        print("  No API key found. Set ODDS_API_KEY environment variable.")
        print("  Get a free key at https://the-odds-api.com")
        print("  Skipping live odds.")
        return pd.DataFrame()

    try:
        url = f"{ODDS_API_BASE}/sports/{SPORT}/odds"
        params = {
            "apiKey": ODDS_API_KEY,
            "regions": "us",
            "markets": "h2h,spreads,totals",
            "oddsFormat": "american",
        }

        response = requests.get(url, params=params, timeout=30)

        if response.status_code == 200:
            data = response.json()
            remaining = response.headers.get("x-requests-remaining", "?")
            used = response.headers.get("x-requests-used", "?")
            print(f"  API credits used: {used}, remaining: {remaining}")

            if not data:
                print("  No upcoming games found (NBA might be off-season).")
                return pd.DataFrame()

            # Flatten the nested JSON into rows
            rows = []
            for game in data:
                game_info = {
                    "GAME_ID": game["id"],
                    "SPORT": game["sport_key"],
                    "COMMENCE_TIME": game["commence_time"],
                    "HOME_TEAM": game["home_team"],
                    "AWAY_TEAM": game["away_team"],
                }

                for bookmaker in game.get("bookmakers", []):
                    for market in bookmaker.get("markets", []):
                        for outcome in market.get("outcomes", []):
                            row = {
                                **game_info,
                                "BOOKMAKER": bookmaker["key"],
                                "MARKET": market["key"],
                                "OUTCOME_NAME": outcome["name"],
                                "PRICE": outcome.get("price"),
                                "POINT": outcome.get("point"),
                                "LAST_UPDATE": bookmaker.get("last_update"),
                            }
                            rows.append(row)

            df = pd.DataFrame(rows)
            print(f"  Pulled odds for {len(data)} upcoming games ({len(rows)} odds entries)")
            return df

        elif response.status_code == 401:
            print("  Invalid API key. Check your ODDS_API_KEY.")
            return pd.DataFrame()
        elif response.status_code == 429:
            print("  Rate limited. Wait and try again.")
            return pd.DataFrame()
        else:
            print(f"  API error: {response.status_code}")
            return pd.DataFrame()

    except Exception as e:
        print(f"  Error: {e}")
        return pd.DataFrame()


# ============================================================
# KAGGLE HISTORICAL ODDS
# ============================================================

# Chosen dataset: https://www.kaggle.com/datasets/erichqiu/nba-odds-and-scores
# Pranav downloads it manually (Kaggle requires auth) and drops the
# extracted CSV at data/kaggle_odds.csv.
#
# The dataset ships in long format: one row per (team, game) with columns
# Date, Team, OppTeam, Location ("Home"/"Away"), Average_Line_Spread, and
# game-result fields. Some redistributions of the same dataset add
# Average_Line_ML (moneyline) — when present we use it directly; when
# absent we derive an approximate moneyline from the spread so the
# backtest still has a baseline market probability.

KAGGLE_INPUT_PATH = f"{DATA_DIR}/kaggle_odds.csv"
HISTORICAL_OUTPUT_PATH = f"{DATA_DIR}/odds_historical.csv"

# nba_backtest.match_market_prob() reads these exact columns; do not rename.
BACKTEST_REQUIRED_COLS = ["Date", "Location", "Team", "OppTeam", "Average_Line_ML"]


def _spread_to_moneyline(spread):
    """
    Approximate American moneyline from a closing point spread.
    Standard heuristic used by sportsbook calculators: roughly
    -110 at pick'em, scaling to -550 at -7 and +450 at +7. Good
    enough for a backtest baseline; replace with actual ML when
    available.
    """
    try:
        s = float(spread)
    except (TypeError, ValueError):
        return None
    # Piecewise mapping from spread to ML, fit to typical NBA close lines.
    # Negative spread = favorite (negative ML), positive = underdog.
    table = [
        (-15, -2500), (-10, -800), (-7, -340), (-5, -220),
        (-3, -160), (-2, -135), (-1, -115), (0, -110),
        (1, -105), (2, 115), (3, 140), (5, 200),
        (7, 320), (10, 750), (15, 2400),
    ]
    # Linear interp between the two nearest anchor points.
    if s <= table[0][0]:
        return table[0][1]
    if s >= table[-1][0]:
        return table[-1][1]
    for (s_lo, ml_lo), (s_hi, ml_hi) in zip(table, table[1:]):
        if s_lo <= s <= s_hi:
            if s_hi == s_lo:
                return ml_lo
            frac = (s - s_lo) / (s_hi - s_lo)
            return ml_lo + frac * (ml_hi - ml_lo)
    return None


def _normalize_kaggle_frame(raw):
    """
    Map common Kaggle NBA odds layouts to the long-format schema
    nba_backtest.py expects.

    Returns a DataFrame with at minimum:
        Date, Location, Team, OppTeam, Average_Line_ML
    plus convenience columns:
        GAME_DATE, HOME_TEAM, AWAY_TEAM, HOME_IMPLIED_PROB,
        AWAY_IMPLIED_PROB
    """
    df = raw.copy()
    df.columns = [str(c).strip() for c in df.columns]

    # ----- Long format (erichqiu schema) -----
    if {"Date", "Team", "OppTeam", "Location"}.issubset(df.columns):
        if "Average_Line_ML" not in df.columns:
            spread_col = next(
                (c for c in ["Average_Line_Spread", "Spread", "Line"] if c in df.columns),
                None,
            )
            if spread_col is None:
                raise ValueError(
                    "Kaggle CSV is missing both Average_Line_ML and a spread column; "
                    "cannot derive moneyline."
                )
            df["Average_Line_ML"] = df[spread_col].apply(_spread_to_moneyline)
        long_df = df

    # ----- Wide format: one row per game with home/away columns -----
    elif {"home_team", "away_team", "date"}.issubset({c.lower() for c in df.columns}):
        # Normalize column case for the keys we care about.
        rename = {c: c.lower() for c in df.columns}
        df = df.rename(columns=rename)
        ml_home_col = next(
            (c for c in ["ml_home", "moneyline_home", "home_ml", "home_moneyline"]
             if c in df.columns),
            None,
        )
        ml_away_col = next(
            (c for c in ["ml_away", "moneyline_away", "away_ml", "away_moneyline"]
             if c in df.columns),
            None,
        )
        if ml_home_col is None or ml_away_col is None:
            spread_col = next(
                (c for c in ["spread", "spread_home", "home_spread"] if c in df.columns),
                None,
            )
            if spread_col is None:
                raise ValueError(
                    "Wide-format Kaggle CSV is missing moneyline and spread columns; "
                    "cannot derive a market price."
                )
            df["__ml_home"] = df[spread_col].apply(_spread_to_moneyline)
            df["__ml_away"] = df[spread_col].apply(
                lambda s: _spread_to_moneyline(-float(s)) if pd.notna(s) else None
            )
            ml_home_col, ml_away_col = "__ml_home", "__ml_away"

        home = pd.DataFrame({
            "Date": df["date"],
            "Location": "Home",
            "Team": df["home_team"],
            "OppTeam": df["away_team"],
            "Average_Line_ML": df[ml_home_col],
        })
        away = pd.DataFrame({
            "Date": df["date"],
            "Location": "Away",
            "Team": df["away_team"],
            "OppTeam": df["home_team"],
            "Average_Line_ML": df[ml_away_col],
        })
        long_df = pd.concat([home, away], ignore_index=True)

    else:
        raise ValueError(
            f"Unrecognized Kaggle CSV schema. Columns: {list(df.columns)[:10]}..."
        )

    # Clean date and drop rows without a market price.
    long_df["Date"] = pd.to_datetime(long_df["Date"], errors="coerce")
    long_df = long_df.dropna(subset=["Date", "Average_Line_ML"]).copy()
    long_df["Average_Line_ML"] = pd.to_numeric(
        long_df["Average_Line_ML"], errors="coerce"
    )
    long_df = long_df.dropna(subset=["Average_Line_ML"]).copy()

    # Convenience columns expected by some downstream consumers.
    long_df["GAME_DATE"] = long_df["Date"].dt.strftime("%Y-%m-%d")
    is_home = long_df["Location"].astype(str).str.lower() == "home"
    long_df["HOME_TEAM"] = long_df["Team"].where(is_home, long_df["OppTeam"])
    long_df["AWAY_TEAM"] = long_df["OppTeam"].where(is_home, long_df["Team"])
    long_df["IMPLIED_PROB"] = long_df["Average_Line_ML"].apply(
        compute_implied_probability
    )

    # Derive vig-free home/away implied probabilities by pivoting.
    pivot = long_df.pivot_table(
        index=["Date", "HOME_TEAM", "AWAY_TEAM"],
        columns="Location",
        values="IMPLIED_PROB",
        aggfunc="first",
    )
    pivot.columns = [str(c).lower() for c in pivot.columns]
    if "home" in pivot.columns and "away" in pivot.columns:
        total = pivot["home"] + pivot["away"]
        pivot["HOME_IMPLIED_PROB"] = (pivot["home"] / total).where(total > 0)
        pivot["AWAY_IMPLIED_PROB"] = (pivot["away"] / total).where(total > 0)
        pivot = pivot.reset_index()[
            ["Date", "HOME_TEAM", "AWAY_TEAM", "HOME_IMPLIED_PROB", "AWAY_IMPLIED_PROB"]
        ]
        long_df = long_df.merge(pivot, on=["Date", "HOME_TEAM", "AWAY_TEAM"], how="left")

    return long_df.reset_index(drop=True)


def load_kaggle_historical_odds():
    """
    Load historical odds from the chosen Kaggle dataset and normalize to the
    schema consumed by nba_backtest.match_market_prob().

    Source: https://www.kaggle.com/datasets/erichqiu/nba-odds-and-scores
    Manual step: download the CSV and place it at data/kaggle_odds.csv.

    Returns the normalized long-format DataFrame and writes it to
    data/odds_historical.csv as a side effect when called from main().
    """
    print("Loading historical odds from Kaggle...")

    if not os.path.exists(KAGGLE_INPUT_PATH):
        print(f"  No file found at {KAGGLE_INPUT_PATH}")
        print("  To get historical odds for evaluation:")
        print("    1. Go to https://www.kaggle.com/datasets/erichqiu/nba-odds-and-scores")
        print("    2. Download the CSV")
        print(f"    3. Save it as {KAGGLE_INPUT_PATH}")
        print("  Skipping historical odds for now.")
        return pd.DataFrame()

    raw = pd.read_csv(KAGGLE_INPUT_PATH)
    print(f"  Read {len(raw)} raw rows, {len(raw.columns)} columns from {KAGGLE_INPUT_PATH}")

    try:
        df = _normalize_kaggle_frame(raw)
    except ValueError as e:
        print(f"  Failed to normalize: {e}")
        return pd.DataFrame()

    missing = [c for c in BACKTEST_REQUIRED_COLS if c not in df.columns]
    if missing:
        print(f"  Normalized frame is missing required columns: {missing}")
        return pd.DataFrame()

    print(
        f"  Normalized to {len(df)} rows "
        f"({df['HOME_TEAM'].nunique()} unique home teams, "
        f"{df['Date'].dt.year.nunique()} seasons)"
    )
    return df


def compute_implied_probability(american_odds):
    """Convert American odds to implied probability."""
    try:
        odds = float(american_odds)
        if odds > 0:
            return 100 / (odds + 100)
        else:
            return abs(odds) / (abs(odds) + 100)
    except (ValueError, TypeError):
        return None


def enrich_odds_data(df):
    """Add implied probabilities and identify best odds across bookmakers."""
    if df.empty:
        return df

    print("Enriching odds data with implied probabilities...")

    # Add implied probability
    if "PRICE" in df.columns:
        df["IMPLIED_PROB"] = df["PRICE"].apply(compute_implied_probability)

    # For moneyline (h2h), find best odds per team per game
    h2h = df[df["MARKET"] == "h2h"].copy() if "MARKET" in df.columns else df.copy()
    if not h2h.empty and "GAME_ID" in h2h.columns:
        best_odds = (
            h2h.groupby(["GAME_ID", "OUTCOME_NAME"])
            .agg(
                BEST_PRICE=("PRICE", "max"),
                WORST_PRICE=("PRICE", "min"),
                NUM_BOOKMAKERS=("BOOKMAKER", "nunique"),
            )
            .reset_index()
        )
        best_odds.to_csv(f"{DATA_DIR}/odds_best_lines.csv", index=False)
        print(f"  Saved best lines to {DATA_DIR}/odds_best_lines.csv")

    return df


def main():
    print("=" * 60)
    print("NBA Odds Pipeline - Step 3")
    print("=" * 60)
    
    live_path = f"{DATA_DIR}/odds_live.csv"
    if os.path.exists(live_path):
        os.remove(live_path)

    # 1. Pull live odds (for demo)
    live_odds = pull_live_odds()
    if not live_odds.empty:
        live_odds = enrich_odds_data(live_odds)
        live_odds.to_csv(f"{DATA_DIR}/odds_live.csv", index=False)
        print(f"Saved live odds to {DATA_DIR}/odds_live.csv")
    print()

    # 2. Load historical odds (for evaluation)
    historical = load_kaggle_historical_odds()
    if not historical.empty:
        historical.to_csv(f"{DATA_DIR}/odds_historical.csv", index=False)
        print(f"Saved historical odds to {DATA_DIR}/odds_historical.csv")
    print()

    # Summary
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Live odds entries: {len(live_odds)}")
    print(f"Historical odds entries: {len(historical)}")
    if not live_odds.empty:
        print(f"Upcoming games: {live_odds['GAME_ID'].nunique() if 'GAME_ID' in live_odds.columns else 'N/A'}")
        print(f"Bookmakers: {live_odds['BOOKMAKER'].nunique() if 'BOOKMAKER' in live_odds.columns else 'N/A'}")
    print()
    print("Next: Run step 4 (Reddit sentiment pipeline)")


if __name__ == "__main__":
    main()
