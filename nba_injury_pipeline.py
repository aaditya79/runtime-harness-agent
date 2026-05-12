"""
Step 2: NBA Injury Data Pipeline
Pulls the official NBA injury report via the `nbainjuries` PyPI package
(maintainer: mxufc29). The package parses the league's PDF report using
tabula-py, so a Java Runtime (JRE/JDK 8+) must be installed on the host.

Output schema (preserved from the previous ESPN scraper so downstream
consumers — Streamlit, agent tools — keep working):
    TEAM, PLAYER_NAME, POSITION, EST_RETURN, STATUS, COMMENT, SCRAPE_DATE

Usage:
    pip install nbainjuries pandas
    # also: install Java JRE/JDK 8+ (e.g. `brew install --cask temurin`)
    python nba_injury_pipeline.py

Output:
    data/injuries.csv - Latest official NBA injury report
"""

import os
from datetime import datetime, timedelta

import pandas as pd

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

# Output schema — must match what the Streamlit app and agent tools read.
INJURY_COLUMNS = [
    "TEAM",
    "PLAYER_NAME",
    "POSITION",
    "EST_RETURN",
    "STATUS",
    "COMMENT",
    "SCRAPE_DATE",
]

# NBA publishes an injury report several times a day. We try the most
# recent expected timestamps in descending order until one is reachable.
# Times are US/Eastern per the league schedule.
REPORT_HOURS_ET = [(20, 30), (17, 30), (14, 30), (11, 30), (8, 30), (5, 30)]


def _candidate_timestamps(now=None, lookback_days=2):
    """Yield (datetime, label) pairs for recent expected report drops."""
    now = now or datetime.now()
    for days_back in range(lookback_days + 1):
        day = now - timedelta(days=days_back)
        for hour, minute in REPORT_HOURS_ET:
            ts = day.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if ts <= now:
                yield ts


def fetch_official_injuries():
    """
    Pull the latest official NBA injury report via `nbainjuries`.
    Returns a DataFrame already mapped to INJURY_COLUMNS.
    """
    print("Fetching official NBA injury report via nbainjuries...")

    try:
        from nbainjuries import injury  # type: ignore
    except ImportError:
        print("  nbainjuries not installed. Run: pip install nbainjuries")
        print("  (also requires Java JRE/JDK 8+ on PATH)")
        return pd.DataFrame(columns=INJURY_COLUMNS)

    last_error = None
    for ts in _candidate_timestamps():
        try:
            raw = injury.get_reportdata(ts, return_df=True)
        except Exception as e:  # noqa: BLE001 — package raises a mix of types
            last_error = e
            continue

        if raw is None or len(raw) == 0:
            continue

        df = _normalize(raw)
        if not df.empty:
            print(
                f"  Pulled {len(df)} entries from report at "
                f"{ts.strftime('%Y-%m-%d %H:%M ET')} "
                f"({df['TEAM'].nunique()} teams)"
            )
            return df

    if last_error is not None:
        print(f"  No reachable report in lookback window. Last error: {last_error}")
    else:
        print("  No reachable report in lookback window.")
    return pd.DataFrame(columns=INJURY_COLUMNS)


def _normalize(raw):
    """
    Map the nbainjuries DataFrame to the legacy ESPN-shaped schema.

    nbainjuries columns: Game Date, Game Time, Matchup, Team, Player Name,
    Current Status, Reason.
    Legacy columns: TEAM, PLAYER_NAME, POSITION, EST_RETURN, STATUS,
    COMMENT, SCRAPE_DATE.

    POSITION and EST_RETURN are not provided by the official report and
    are emitted as empty strings. SCRAPE_DATE uses today.
    """
    df = raw.copy()
    df.columns = [str(c).strip() for c in df.columns]

    def col(name, default=""):
        return df[name] if name in df.columns else default

    out = pd.DataFrame(
        {
            "TEAM": col("Team"),
            "PLAYER_NAME": col("Player Name"),
            "POSITION": "",
            "EST_RETURN": "",
            "STATUS": col("Current Status"),
            "COMMENT": col("Reason"),
            "SCRAPE_DATE": datetime.now().strftime("%Y-%m-%d"),
        },
        columns=INJURY_COLUMNS,
    )

    # Drop rows with no player name — defensive against header artefacts.
    out = out[out["PLAYER_NAME"].astype(str).str.strip() != ""].reset_index(drop=True)
    return out


def main():
    print("=" * 60)
    print("NBA Injury Pipeline - Step 2")
    print("=" * 60)

    injuries = fetch_official_injuries()

    if injuries.empty:
        print("  No data pulled. Writing empty schema so downstream readers don't 500.")
        injuries = pd.DataFrame(columns=INJURY_COLUMNS)

    out_path = f"{DATA_DIR}/injuries.csv"
    injuries.to_csv(out_path, index=False)

    print()
    print(f"Saved to {out_path}")
    print(f"Total records: {len(injuries)}")
    if len(injuries) > 0:
        print(f"Status breakdown: {injuries['STATUS'].value_counts().to_dict()}")
        print(f"Teams: {injuries['TEAM'].nunique()}")
        print()
        print("Sample entries:")
        for _, row in injuries.head(3).iterrows():
            comment = str(row["COMMENT"])[:80]
            print(
                f"  {row['TEAM']} - {row['PLAYER_NAME']} - "
                f"{row['STATUS']} - {comment}..."
            )
    print()
    print("Next: Run step 3 (odds pipeline)")


if __name__ == "__main__":
    main()
