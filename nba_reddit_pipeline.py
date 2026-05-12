"""
NBA Reddit Sentiment Pipeline (public JSON endpoint, no app required).

Pulls recent posts and top comments from r/nba and per-team subreddits
via Reddit's unauthenticated public JSON endpoint
(https://www.reddit.com/r/<sub>/.json), runs VADER sentiment, and
aggregates per-team comment count + sentiment.

Why public JSON instead of PRAW:
    Creating a Reddit OAuth app via reddit.com/prefs/apps was blocked
    in our environment. The public .json endpoint requires no app and
    no auth, just a polite User-Agent string and rate-limit awareness
    (~60 requests/min/IP).

Limitations vs PRAW:
    - Returns the most recent ~100 posts per subreddit per call
    - No historical search by date (Pushshift is shut down post-2023)
    - So this is a **live-snapshot** signal: useful for the Streamlit
      demo and for current-day games, NOT for historical backtest games

For the historical backtest evaluation, the agent's
tool_get_team_sentiment falls back to news-based sentiment which is
populated by nba_news_pipeline.py (also pre-game timestamped).

Usage:
    pip install requests vaderSentiment pandas
    python nba_reddit_pipeline.py                     # default: top 30 posts each
    python nba_reddit_pipeline.py --posts-per-sub 50  # pull more per sub
    python nba_reddit_pipeline.py --comments-per-post 25  # deeper comment scan
    python nba_reddit_pipeline.py --smoke             # one sub, fewer posts

Output:
    data/reddit_team_sentiment.csv  - per-team aggregated sentiment + comment count
    data/reddit_post_index.csv      - one row per post we considered (debug + audit)
"""

import argparse
import json
import os
import re
import time
from datetime import datetime, timezone

import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv()

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

USER_AGENT = "MatchOdds-AI-research/0.1 (Columbia STAT GR5293; contact: course project)"
REQUEST_TIMEOUT = 20
INTER_REQUEST_SLEEP = 1.2  # ~50 requests/min, safely under Reddit's 60/min limit

TEAM_SUBS = {
    "ATL": "AtlantaHawks",
    "BOS": "bostonceltics",
    "BKN": "GoNets",
    "CHA": "CharlotteHornets",
    "CHI": "chicagobulls",
    "CLE": "clevelandcavs",
    "DAL": "Mavericks",
    "DEN": "denvernuggets",
    "DET": "DetroitPistons",
    "GSW": "warriors",
    "HOU": "rockets",
    "IND": "pacers",
    "LAC": "LAClippers",
    "LAL": "lakers",
    "MEM": "memphisgrizzlies",
    "MIA": "heat",
    "MIL": "MkeBucks",
    "MIN": "timberwolves",
    "NOP": "NOLAPelicans",
    "NYK": "NYKnicks",
    "OKC": "Thunder",
    "ORL": "OrlandoMagic",
    "PHI": "sixers",
    "PHX": "suns",
    "POR": "ripcity",
    "SAC": "kings",
    "SAS": "NBASpurs",
    "TOR": "torontoraptors",
    "UTA": "UtahJazz",
    "WAS": "washingtonwizards",
}

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


def setup_sentiment_analyzer():
    """Initialize VADER. Returns None with a warning if not installed."""
    try:
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
        return SentimentIntensityAnalyzer()
    except ImportError:
        print("  vaderSentiment not installed. Run: pip install vaderSentiment")
        return None


def _get_json(url, retries=3):
    """GET a public Reddit .json URL with polite retry on 429/5xx."""
    for attempt in range(retries):
        try:
            resp = requests.get(
                url,
                headers={"User-Agent": USER_AGENT},
                timeout=REQUEST_TIMEOUT,
            )
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code in (429, 500, 502, 503, 504):
                wait = 2 ** attempt
                print(f"    {resp.status_code} from Reddit, sleeping {wait}s and retrying...")
                time.sleep(wait)
                continue
            print(f"    Reddit returned HTTP {resp.status_code} for {url}")
            return None
        except requests.RequestException as e:
            print(f"    request failed for {url}: {e}")
            time.sleep(2 ** attempt)
    return None


def detect_teams(text):
    """Return TEAM abbreviations mentioned in text (lowercased keyword match)."""
    if not text:
        return []
    lower = text.lower()
    hits = []
    for abb, kws in TEAM_KEYWORDS.items():
        if any(kw in lower for kw in kws):
            hits.append(abb)
    return hits


def fetch_subreddit_posts(subreddit, posts_per_sub=30, listing="hot"):
    """
    Pull recent posts from a subreddit via the public JSON endpoint.
    Returns a list of {id, title, selftext, created_utc, permalink, num_comments, score}.
    """
    url = f"https://www.reddit.com/r/{subreddit}/{listing}/.json?limit={posts_per_sub}"
    data = _get_json(url)
    if not data:
        return []
    children = data.get("data", {}).get("children", [])
    posts = []
    for child in children:
        d = child.get("data", {})
        if d.get("stickied"):
            continue  # skip sticky meta-posts
        posts.append({
            "id": d.get("id"),
            "subreddit": subreddit,
            "title": d.get("title", "") or "",
            "selftext": d.get("selftext", "") or "",
            "created_utc": d.get("created_utc"),
            "permalink": d.get("permalink", ""),
            "num_comments": int(d.get("num_comments", 0) or 0),
            "score": int(d.get("score", 0) or 0),
        })
    time.sleep(INTER_REQUEST_SLEEP)
    return posts


def fetch_top_comments(permalink, max_comments=15):
    """
    Pull top-level comments for a post. Permalink looks like /r/sub/comments/<id>/<slug>/.
    """
    if not permalink:
        return []
    url = f"https://www.reddit.com{permalink}.json?limit={max_comments}&depth=1"
    data = _get_json(url)
    if not data or not isinstance(data, list) or len(data) < 2:
        return []
    listings = data[1].get("data", {}).get("children", [])
    comments = []
    for c in listings:
        if c.get("kind") != "t1":
            continue
        d = c.get("data", {})
        body = d.get("body", "")
        if not body or body in ("[deleted]", "[removed]"):
            continue
        comments.append({
            "body": body,
            "score": int(d.get("score", 0) or 0),
            "created_utc": d.get("created_utc"),
        })
    time.sleep(INTER_REQUEST_SLEEP)
    return comments[:max_comments]


def aggregate_team_sentiment(posts_with_comments, analyzer):
    """
    Score every (title + selftext + each comment body) once, attribute the
    score to whichever teams the text mentions, and aggregate per team.
    """
    rows = {abb: {
        "TEAM": abb,
        "AVG_SENTIMENT": 0.0,
        "COMMENT_COUNT": 0,
        "POSITIVE_COMMENT_COUNT": 0,
        "NEGATIVE_COMMENT_COUNT": 0,
        "POST_COUNT": 0,
        "SOURCE": "reddit",
        "SCRAPE_DATE": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "_compound_sum": 0.0,
        "_compound_n": 0,
    } for abb in TEAM_KEYWORDS}

    for post in posts_with_comments:
        post_text = f"{post['title']} {post['selftext']}"
        teams_in_post = set(detect_teams(post_text))

        # Score the post itself once if we have an analyzer
        if analyzer is not None and teams_in_post:
            sc = analyzer.polarity_scores(post_text)
            for abb in teams_in_post:
                rows[abb]["_compound_sum"] += sc["compound"]
                rows[abb]["_compound_n"] += 1
                rows[abb]["POST_COUNT"] += 1

        # Score comments individually, attributing to team(s) mentioned in
        # the comment body OR the post if the comment body is too short to
        # mention a team explicitly (common on team-sub posts).
        for comment in post.get("comments", []):
            body = comment["body"]
            teams_in_comment = set(detect_teams(body)) or teams_in_post
            if not teams_in_comment:
                continue

            if analyzer is not None:
                sc = analyzer.polarity_scores(body)
                compound = sc["compound"]
            else:
                compound = 0.0

            for abb in teams_in_comment:
                rows[abb]["_compound_sum"] += compound
                rows[abb]["_compound_n"] += 1
                rows[abb]["COMMENT_COUNT"] += 1
                if compound >= 0.05:
                    rows[abb]["POSITIVE_COMMENT_COUNT"] += 1
                elif compound <= -0.05:
                    rows[abb]["NEGATIVE_COMMENT_COUNT"] += 1

    out = []
    for abb, row in rows.items():
        n = row["_compound_n"]
        row["AVG_SENTIMENT"] = round(row["_compound_sum"] / n, 4) if n else 0.0
        del row["_compound_sum"]
        del row["_compound_n"]
        out.append(row)
    return pd.DataFrame(out)


def build_post_index(posts_with_comments):
    rows = []
    for p in posts_with_comments:
        rows.append({
            "post_id": p["id"],
            "subreddit": p["subreddit"],
            "title": p["title"][:200],
            "created_utc": p["created_utc"],
            "num_comments_on_reddit": p["num_comments"],
            "num_comments_pulled": len(p.get("comments", [])),
            "score": p["score"],
            "permalink": p["permalink"],
        })
    return pd.DataFrame(rows)


def main():
    parser = argparse.ArgumentParser(description="Reddit sentiment pipeline (public JSON)")
    parser.add_argument("--posts-per-sub", type=int, default=30,
                        help="how many recent posts to pull per subreddit (default 30)")
    parser.add_argument("--comments-per-post", type=int, default=15,
                        help="how many top-level comments per post (default 15)")
    parser.add_argument("--smoke", action="store_true",
                        help="quick smoke: r/nba only, 5 posts, 5 comments each")
    parser.add_argument("--include-rnba", action="store_true", default=True,
                        help="include r/nba in addition to per-team subs (default true)")
    args = parser.parse_args()

    print("=" * 60)
    print("NBA Reddit Pipeline (public JSON, no app required)")
    print("=" * 60)

    if args.smoke:
        subs = [("RNBA", "nba")]
        posts_per_sub = 5
        comments_per_post = 5
    else:
        subs = [(abb, sub) for abb, sub in TEAM_SUBS.items()]
        if args.include_rnba:
            subs = [("RNBA", "nba")] + subs
        posts_per_sub = args.posts_per_sub
        comments_per_post = args.comments_per_post

    analyzer = setup_sentiment_analyzer()

    posts_with_comments = []
    for label, subreddit in subs:
        print(f"\n  r/{subreddit} ({label})...")
        posts = fetch_subreddit_posts(subreddit, posts_per_sub=posts_per_sub)
        print(f"    pulled {len(posts)} posts")
        for post in posts:
            post["comments"] = fetch_top_comments(post["permalink"], max_comments=comments_per_post)
        posts_with_comments.extend(posts)
        print(f"    aggregated {sum(len(p.get('comments', [])) for p in posts)} comments")

    print("\n" + "=" * 60)
    print("AGGREGATING TEAM SENTIMENT")
    print("=" * 60)

    df_team = aggregate_team_sentiment(posts_with_comments, analyzer)
    df_team_path = f"{DATA_DIR}/reddit_team_sentiment.csv"
    df_team.to_csv(df_team_path, index=False)
    print(f"\nSaved {len(df_team)} team rows to {df_team_path}")

    df_index = build_post_index(posts_with_comments)
    df_index_path = f"{DATA_DIR}/reddit_post_index.csv"
    df_index.to_csv(df_index_path, index=False)
    print(f"Saved {len(df_index)} post-index rows to {df_index_path}")

    total_posts = len(posts_with_comments)
    total_comments = sum(len(p.get("comments", [])) for p in posts_with_comments)
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Subreddits scanned: {len(subs)}")
    print(f"Posts considered:   {total_posts}")
    print(f"Comments analyzed:  {total_comments}")
    if not df_team.empty:
        nonzero = df_team[df_team["COMMENT_COUNT"] > 0]
        if len(nonzero) > 0:
            top = nonzero.sort_values("COMMENT_COUNT", ascending=False).head(5)
            print("\nTop 5 teams by Reddit comment volume:")
            for _, row in top.iterrows():
                print(f"  {row['TEAM']}: {int(row['COMMENT_COUNT'])} comments, sentiment {row['AVG_SENTIMENT']:+.3f}")


if __name__ == "__main__":
    main()
