"""
Step 4: NBA YouTube Comments Pipeline
Pulls comments from NBA highlight videos for recent games, runs VADER
sentiment analysis, aggregates per-team and per-game.

Replaces the old (mislabeled) Twitter scraper. Reddit's API isn't viable
for our use case and X/Twitter requires a paid API. YouTube Data API v3
is free (10k quota units/day), and per-game highlight videos give a
strong info-density signal: LAL/BOS national-TV games pull thousands of
comments while DET/CHA Tuesday games pull dozens.

Setup:
    pip install google-api-python-client vaderSentiment pandas
    export YOUTUBE_API_KEY=<key from console.cloud.google.com>

Usage:
    python nba_youtube_pipeline.py                  # default: last 3 days, max 5 games
    python nba_youtube_pipeline.py --days 7         # last 7 days
    python nba_youtube_pipeline.py --max-games 10   # cap games scanned
    python nba_youtube_pipeline.py --smoke          # one game, mock if no key

Output:
    data/youtube_team_sentiment.csv   - per-team aggregated sentiment + comment count
    data/youtube_per_game.csv         - per-game comment count + sentiment (info-density)
    data/youtube_cache/{video_id}.json - cached comments (avoid quota burn on re-runs)

Quota notes:
    search.list           = 100 units / call
    commentThreads.list   = 1 unit / call (up to 100 comments)
    Default run touches ~5 games * (1 search + ~3 comment fetches) = ~515 units.
"""

import argparse
import json
import os
from datetime import datetime, timedelta, timezone

import pandas as pd
from dotenv import load_dotenv

load_dotenv()

DATA_DIR = "data"
CACHE_DIR = f"{DATA_DIR}/youtube_cache"
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(CACHE_DIR, exist_ok=True)

# Channels we trust for NBA highlights — restricting search to these
# keeps signal high and quota usage predictable.
TRUSTED_CHANNEL_IDS = {
    "UCWJ2lWNubArHWmf3FIHbfcQ": "NBA",
    "UCiWLfSweyRNmLpgEHekhoAg": "ESPN",
    "UC9-OpMMVoNP5o10_Iyq7Ndw": "Bleacher Report",
    "UCqQh6q1tNNQ5W6mXPbz3Y9Q": "House of Highlights",
}

# Same TEAM_KEYWORDS shape the news pipeline uses, so downstream aggregation
# stays consistent across sources.
TEAM_KEYWORDS = {
    "ATL": ["hawks", "atlanta"],
    "BOS": ["celtics", "boston"],
    "BKN": ["nets", "brooklyn"],
    "CHA": ["hornets", "charlotte"],
    "CHI": ["bulls", "chicago"],
    "CLE": ["cavaliers", "cavs", "cleveland"],
    "DAL": ["mavericks", "mavs", "dallas"],
    "DEN": ["nuggets", "denver"],
    "DET": ["pistons", "detroit"],
    "GSW": ["warriors", "dubs", "golden state"],
    "HOU": ["rockets", "houston"],
    "IND": ["pacers", "indiana"],
    "LAC": ["clippers"],
    "LAL": ["lakers"],
    "MEM": ["grizzlies", "memphis"],
    "MIA": ["heat", "miami"],
    "MIL": ["bucks", "milwaukee"],
    "MIN": ["timberwolves", "wolves", "minnesota"],
    "NOP": ["pelicans", "pels", "new orleans"],
    "NYK": ["knicks", "new york"],
    "OKC": ["thunder", "oklahoma"],
    "ORL": ["magic", "orlando"],
    "PHI": ["sixers", "76ers", "philadelphia"],
    "PHX": ["suns", "phoenix"],
    "POR": ["blazers", "trail blazers", "portland"],
    "SAC": ["kings", "sacramento"],
    "SAS": ["spurs", "san antonio"],
    "TOR": ["raptors", "toronto"],
    "UTA": ["jazz", "utah"],
    "WAS": ["wizards", "washington"],
}

TEAM_FULL_NAMES = {
    "ATL": "Atlanta Hawks", "BOS": "Boston Celtics", "BKN": "Brooklyn Nets",
    "CHA": "Charlotte Hornets", "CHI": "Chicago Bulls", "CLE": "Cleveland Cavaliers",
    "DAL": "Dallas Mavericks", "DEN": "Denver Nuggets", "DET": "Detroit Pistons",
    "GSW": "Golden State Warriors", "HOU": "Houston Rockets", "IND": "Indiana Pacers",
    "LAC": "LA Clippers", "LAL": "Los Angeles Lakers", "MEM": "Memphis Grizzlies",
    "MIA": "Miami Heat", "MIL": "Milwaukee Bucks", "MIN": "Minnesota Timberwolves",
    "NOP": "New Orleans Pelicans", "NYK": "New York Knicks", "OKC": "Oklahoma City Thunder",
    "ORL": "Orlando Magic", "PHI": "Philadelphia 76ers", "PHX": "Phoenix Suns",
    "POR": "Portland Trail Blazers", "SAC": "Sacramento Kings", "SAS": "San Antonio Spurs",
    "TOR": "Toronto Raptors", "UTA": "Utah Jazz", "WAS": "Washington Wizards",
}


def setup_sentiment_analyzer():
    """Initialize VADER sentiment analyzer."""
    try:
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
        return SentimentIntensityAnalyzer()
    except ImportError:
        print("  vaderSentiment not installed. Run: pip install vaderSentiment")
        return None


def setup_youtube_client():
    """Build the YouTube Data API client. Returns None if key/lib missing."""
    api_key = os.environ.get("YOUTUBE_API_KEY")
    if not api_key:
        print("  YOUTUBE_API_KEY not set.")
        print("  Register at https://console.cloud.google.com, enable")
        print("  YouTube Data API v3, create an API key, then export it.")
        return None

    try:
        from googleapiclient.discovery import build
    except ImportError:
        print("  google-api-python-client not installed.")
        print("  Run: pip install google-api-python-client")
        return None

    return build("youtube", "v3", developerKey=api_key, cache_discovery=False)


def detect_teams_in_text(text):
    """Return list of TEAM abbreviations mentioned in text (lowercased match)."""
    if not text:
        return []
    lower = text.lower()
    hits = []
    for abb, kws in TEAM_KEYWORDS.items():
        if any(kw in lower for kw in kws):
            hits.append(abb)
    return hits


def search_highlight_videos(youtube, home_team, away_team, game_date, max_results=3):
    """
    Search YouTube for highlight videos of a specific game.

    home_team / away_team are abbreviations (e.g. 'BOS', 'LAL').
    game_date is a 'YYYY-MM-DD' string. We constrain the search window to
    +/- 2 days around the game so we mostly catch the actual highlight upload.
    """
    home_full = TEAM_FULL_NAMES.get(home_team, home_team)
    away_full = TEAM_FULL_NAMES.get(away_team, away_team)
    query = f"{away_full} vs {home_full} highlights"

    try:
        date_dt = datetime.strptime(game_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        print(f"  Bad game_date {game_date}, skipping search")
        return []

    published_after = (date_dt - timedelta(days=1)).isoformat()
    published_before = (date_dt + timedelta(days=2)).isoformat()

    try:
        response = youtube.search().list(
            q=query,
            part="snippet",
            type="video",
            maxResults=max_results,
            order="relevance",
            publishedAfter=published_after,
            publishedBefore=published_before,
        ).execute()
    except Exception as e:
        print(f"  search.list failed for {away_team}@{home_team} {game_date}: {e}")
        return []

    items = response.get("items", [])
    videos = []
    for item in items:
        snippet = item.get("snippet", {})
        channel_id = snippet.get("channelId")
        # Filter to trusted NBA channels OR titles that strongly look like
        # game highlights (some clips come from secondary uploaders).
        title_lower = snippet.get("title", "").lower()
        is_trusted = channel_id in TRUSTED_CHANNEL_IDS
        looks_like_highlight = (
            "highlights" in title_lower
            and home_full.lower().split()[-1] in title_lower
            and away_full.lower().split()[-1] in title_lower
        )
        if not (is_trusted or looks_like_highlight):
            continue

        videos.append({
            "video_id": item["id"]["videoId"],
            "title": snippet.get("title", ""),
            "channel_id": channel_id,
            "channel_title": snippet.get("channelTitle", ""),
            "published_at": snippet.get("publishedAt", ""),
        })
    return videos


def fetch_comments(youtube, video_id, max_comments=100):
    """
    Fetch top-level comments for a video, with on-disk cache to avoid quota
    burn on re-runs. Returns list of {text, author, like_count, published}.
    """
    cache_path = f"{CACHE_DIR}/{video_id}.json"
    if os.path.exists(cache_path):
        try:
            with open(cache_path) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            # Corrupt cache — re-fetch.
            pass

    try:
        response = youtube.commentThreads().list(
            videoId=video_id,
            part="snippet",
            maxResults=max_comments,
            textFormat="plainText",
            order="relevance",
        ).execute()
    except Exception as e:
        # Common: comments disabled on video. Cache an empty list so we
        # don't keep retrying.
        print(f"    commentThreads failed for {video_id}: {e}")
        with open(cache_path, "w") as f:
            json.dump([], f)
        return []

    comments = []
    for item in response.get("items", []):
        snippet = item.get("snippet", {}).get("topLevelComment", {}).get("snippet", {})
        comments.append({
            "text": snippet.get("textDisplay", ""),
            "author": snippet.get("authorDisplayName", ""),
            "like_count": int(snippet.get("likeCount", 0)),
            "published": snippet.get("publishedAt", ""),
        })

    with open(cache_path, "w") as f:
        json.dump(comments, f)
    return comments


def score_comments(comments, analyzer):
    """Attach VADER compound score to each comment dict."""
    for c in comments:
        if not c.get("text"):
            c["compound"] = 0.0
            continue
        c["compound"] = analyzer.polarity_scores(c["text"])["compound"]
    return comments


def aggregate_per_game(per_video_records):
    """
    Collapse multiple videos per game into one game-level row.
    Input: list of dicts with game_date, home_team, away_team, comments (list).
    """
    by_game = {}
    for rec in per_video_records:
        key = (rec["game_date"], rec["home_team"], rec["away_team"])
        by_game.setdefault(key, []).extend(rec["comments"])

    rows = []
    for (game_date, home, away), comments in by_game.items():
        if comments:
            avg_sent = sum(c["compound"] for c in comments) / len(comments)
        else:
            avg_sent = 0.0
        rows.append({
            "GAME_DATE": game_date,
            "HOME_TEAM": home,
            "AWAY_TEAM": away,
            "COMMENT_COUNT": len(comments),
            "AVG_SENTIMENT": round(avg_sent, 4),
        })
    return pd.DataFrame(rows)


def aggregate_per_team(per_video_records, scrape_date):
    """
    Aggregate to per-team rows. A comment counts for a team if either:
    - The video was about a game involving that team (always-on attribution), OR
    - The comment text mentions the team by keyword (cross-attribution).

    We prefer the game-attribution route as primary, then enrich with mention
    counts so a Lakers fan trash-talking the Celtics in a LAL/BOS clip lands
    sentiment on both.
    """
    rows_by_team = {}

    for rec in per_video_records:
        teams_in_game = {rec["home_team"], rec["away_team"]}
        for c in rec["comments"]:
            mentioned = set(detect_teams_in_text(c.get("text", "")))
            attributed = teams_in_game | mentioned
            for team in attributed:
                rows_by_team.setdefault(team, []).append(c["compound"])

    rows = []
    for team in TEAM_KEYWORDS.keys():
        scores = rows_by_team.get(team, [])
        if scores:
            avg = sum(scores) / len(scores)
            pos = sum(1 for s in scores if s > 0.05)
            neg = sum(1 for s in scores if s < -0.05)
        else:
            avg, pos, neg = 0.0, 0, 0
        rows.append({
            "TEAM": team,
            "AVG_SENTIMENT": round(avg, 4),
            "COMMENT_COUNT": len(scores),
            "POSITIVE_COMMENT_COUNT": pos,
            "NEGATIVE_COMMENT_COUNT": neg,
            "SOURCE": "youtube",
            "SCRAPE_DATE": scrape_date,
        })
    return pd.DataFrame(rows)


def load_recent_games(days):
    """
    Read recent games from data/games_recent.csv if available; otherwise
    return empty list and let caller fall back to a smoke sample.
    """
    games_path = f"{DATA_DIR}/games_recent.csv"
    if not os.path.exists(games_path):
        return []

    try:
        df = pd.read_csv(games_path)
    except Exception as e:
        print(f"  Could not read {games_path}: {e}")
        return []

    if df.empty or "GAME_DATE" not in df.columns:
        return []

    cutoff = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
    df = df[df["GAME_DATE"] >= cutoff]
    # Expect HOME_TEAM_ABBR / AWAY_TEAM_ABBR columns; fall back to common variants.
    home_col = next((c for c in ["HOME_TEAM_ABBR", "HOME_TEAM", "HOME"] if c in df.columns), None)
    away_col = next((c for c in ["AWAY_TEAM_ABBR", "AWAY_TEAM", "AWAY"] if c in df.columns), None)
    if not home_col or not away_col:
        return []

    games = []
    for _, row in df.iterrows():
        games.append({
            "game_date": str(row["GAME_DATE"])[:10],
            "home_team": str(row[home_col]).upper()[:3],
            "away_team": str(row[away_col]).upper()[:3],
        })
    return games


def smoke_sample_games():
    """Single hard-coded matchup so the script runs end-to-end without data deps."""
    yesterday = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")
    return [{"game_date": yesterday, "home_team": "BOS", "away_team": "LAL"}]


def write_empty_outputs(scrape_date):
    """Write empty CSVs with the correct schema so downstream readers don't blow up."""
    pd.DataFrame(columns=[
        "TEAM", "AVG_SENTIMENT", "COMMENT_COUNT",
        "POSITIVE_COMMENT_COUNT", "NEGATIVE_COMMENT_COUNT",
        "SOURCE", "SCRAPE_DATE",
    ]).to_csv(f"{DATA_DIR}/youtube_team_sentiment.csv", index=False)
    pd.DataFrame(columns=[
        "GAME_DATE", "HOME_TEAM", "AWAY_TEAM", "COMMENT_COUNT", "AVG_SENTIMENT",
    ]).to_csv(f"{DATA_DIR}/youtube_per_game.csv", index=False)


def run(days, max_games, smoke):
    print("=" * 60)
    print("NBA YouTube Comments Pipeline - Step 4")
    print("=" * 60)

    scrape_date = datetime.utcnow().strftime("%Y-%m-%d")
    analyzer = setup_sentiment_analyzer()
    youtube = setup_youtube_client()

    if analyzer is None or youtube is None:
        print()
        print("Writing empty outputs with correct schema (missing dependency or API key).")
        write_empty_outputs(scrape_date)
        return

    games = smoke_sample_games() if smoke else load_recent_games(days)
    if not games:
        print(f"  No recent games in data/games_recent.csv (last {days}d).")
        print("  Falling back to a single smoke-test game.")
        games = smoke_sample_games()

    games = games[:max_games]
    print(f"  Scanning {len(games)} game(s)...")

    per_video_records = []
    for g in games:
        print(f"  {g['away_team']} @ {g['home_team']} ({g['game_date']})...")
        videos = search_highlight_videos(
            youtube, g["home_team"], g["away_team"], g["game_date"]
        )
        if not videos:
            print("    no matching videos")
            continue

        for v in videos:
            comments = fetch_comments(youtube, v["video_id"])
            comments = score_comments(comments, analyzer)
            per_video_records.append({
                "game_date": g["game_date"],
                "home_team": g["home_team"],
                "away_team": g["away_team"],
                "video_id": v["video_id"],
                "comments": comments,
            })
            print(f"    {v['video_id']} ({v['channel_title']}): {len(comments)} comments")

    per_game_df = aggregate_per_game(per_video_records)
    per_team_df = aggregate_per_team(per_video_records, scrape_date)

    per_game_df.to_csv(f"{DATA_DIR}/youtube_per_game.csv", index=False)
    per_team_df.to_csv(f"{DATA_DIR}/youtube_team_sentiment.csv", index=False)

    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    total_comments = int(per_team_df["COMMENT_COUNT"].sum()) if not per_team_df.empty else 0
    print(f"Games scanned: {len(games)}")
    print(f"Videos pulled: {len(per_video_records)}")
    print(f"Total comments analyzed: {total_comments}")
    if not per_team_df.empty and total_comments > 0:
        nonzero = per_team_df[per_team_df["COMMENT_COUNT"] > 0]
        if not nonzero.empty:
            top = nonzero.sort_values("COMMENT_COUNT", ascending=False).head(5)
            print("Top teams by comment volume:")
            for _, r in top.iterrows():
                print(f"  {r['TEAM']}: {int(r['COMMENT_COUNT'])} comments, avg sent {r['AVG_SENTIMENT']:+.3f}")
    print()
    print(f"Saved to {DATA_DIR}/youtube_team_sentiment.csv")
    print(f"Saved to {DATA_DIR}/youtube_per_game.csv")


def main():
    parser = argparse.ArgumentParser(description="NBA YouTube comments pipeline")
    parser.add_argument("--days", type=int, default=3,
                        help="Look back N days for recent games (default 3)")
    parser.add_argument("--max-games", type=int, default=5,
                        help="Cap on games scanned per run (quota guard, default 5)")
    parser.add_argument("--smoke", action="store_true",
                        help="Run a single hard-coded game end-to-end")
    args = parser.parse_args()
    run(days=args.days, max_games=args.max_games, smoke=args.smoke)


if __name__ == "__main__":
    main()
