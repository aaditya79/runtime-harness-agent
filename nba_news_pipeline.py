"""
Step 5: NBA News Pipeline + Sentiment
Pulls NBA news from multiple sources, tags teams, runs sentiment analysis,
and saves results.

Usage:
    pip install requests beautifulsoup4 feedparser pandas vaderSentiment
    python nba_news_pipeline.py

Output:
    data/news_articles.csv - Recent NBA news articles with sentiment scores
    data/team_sentiment.csv - Aggregated team-level news sentiment
"""

import os
import re
import requests
import pandas as pd
from datetime import datetime

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

TEAM_KEYWORDS = {
    "ATL": ["hawks", "atlanta hawks", "trae young"],
    "BOS": ["celtics", "boston celtics", "jayson tatum", "jaylen brown"],
    "BKN": ["nets", "brooklyn nets"],
    "CHA": ["hornets", "charlotte hornets", "lamelo ball"],
    "CHI": ["bulls", "chicago bulls"],
    "CLE": ["cavaliers", "cavs", "cleveland", "donovan mitchell"],
    "DAL": ["mavericks", "mavs", "dallas", "luka doncic"],
    "DEN": ["nuggets", "denver nuggets", "nikola jokic"],
    "DET": ["pistons", "detroit pistons"],
    "GSW": ["warriors", "golden state", "stephen curry", "steph curry"],
    "HOU": ["rockets", "houston rockets"],
    "IND": ["pacers", "indiana pacers", "tyrese haliburton"],
    "LAC": ["clippers", "la clippers"],
    "LAL": ["lakers", "los angeles lakers", "lebron james", "anthony davis"],
    "MEM": ["grizzlies", "memphis grizzlies", "ja morant"],
    "MIA": ["heat", "miami heat", "jimmy butler"],
    "MIL": ["bucks", "milwaukee bucks", "giannis"],
    "MIN": ["timberwolves", "wolves", "minnesota", "anthony edwards"],
    "NOP": ["pelicans", "new orleans pelicans", "zion williamson"],
    "NYK": ["knicks", "new york knicks", "jalen brunson"],
    "OKC": ["thunder", "oklahoma city", "shai gilgeous-alexander", "sga"],
    "ORL": ["magic", "orlando magic", "paolo banchero"],
    "PHI": ["76ers", "sixers", "philadelphia", "joel embiid"],
    "PHX": ["suns", "phoenix suns", "kevin durant", "devin booker"],
    "POR": ["trail blazers", "blazers", "portland"],
    "SAC": ["kings", "sacramento kings"],
    "SAS": ["spurs", "san antonio spurs", "victor wembanyama", "wemby"],
    "TOR": ["raptors", "toronto raptors"],
    "UTA": ["jazz", "utah jazz"],
    "WAS": ["wizards", "washington wizards"],
}


def setup_sentiment_analyzer():
    """Initialize VADER sentiment analyzer."""
    try:
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
        return SentimentIntensityAnalyzer()
    except ImportError:
        print("  vaderSentiment not installed. Run: pip install vaderSentiment")
        return None


def try_rss_feeds():
    """Try multiple RSS feed URLs and return whatever works."""
    print("Trying RSS feeds...")

    feeds = [
        ("ESPN_NBA", "https://www.espn.com/espn/rss/nba/news"),
        ("ESPN_NBA_2", "https://www.espn.com/blog/feed?blog=nba"),
        ("CBS_NBA", "https://www.cbssports.com/rss/headlines/nba/"),
        ("NBC_NBA", "https://www.nbcsports.com/nba/rss"),
    ]

    articles = []
    try:
        import feedparser
        for name, url in feeds:
            try:
                feed = feedparser.parse(url)
                count_before = len(articles)
                for entry in feed.entries[:20]:
                    summary = getattr(entry, "summary", getattr(entry, "description", ""))
                    summary = re.sub(r"<[^>]+>", "", summary)[:500]
                    articles.append({
                        "SOURCE": name,
                        "TITLE": entry.get("title", ""),
                        "SUMMARY": summary,
                        "LINK": entry.get("link", ""),
                        "PUBLISHED": getattr(entry, "published", ""),
                    })
                print(f"  {name}: +{len(articles) - count_before} articles")
            except Exception as e:
                print(f"  {name}: failed ({e})")
    except ImportError:
        print("  feedparser not installed")

    return articles


def scrape_espn_nba_news():
    """Scrape NBA headlines directly from ESPN's NBA page."""
    print("Scraping ESPN NBA page...")

    try:
        from bs4 import BeautifulSoup

        response = requests.get("https://www.espn.com/nba/", headers=HEADERS, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        articles = []
        for link in soup.find_all("a", href=True):
            href = link.get("href", "")
            text = link.get_text(strip=True)

            if ("/story/" in href or "/blog/" in href or "/insider/" in href) and len(text) > 20:
                full_url = href if href.startswith("http") else f"https://www.espn.com{href}"
                articles.append({
                    "SOURCE": "ESPN_SCRAPE",
                    "TITLE": text[:200],
                    "SUMMARY": "",
                    "LINK": full_url,
                    "PUBLISHED": datetime.now().strftime("%Y-%m-%d"),
                })

        seen = set()
        unique = []
        for a in articles:
            if a["TITLE"] not in seen:
                seen.add(a["TITLE"])
                unique.append(a)

        print(f"  Found {len(unique)} headlines from ESPN")
        return unique

    except Exception as e:
        print(f"  ESPN scrape failed: {e}")
        return []


def scrape_nba_com_news():
    """Scrape headlines from NBA.com."""
    print("Scraping NBA.com news...")

    try:
        from bs4 import BeautifulSoup

        response = requests.get("https://www.nba.com/news", headers=HEADERS, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        articles = []
        for link in soup.find_all("a", href=True):
            href = link.get("href", "")
            text = link.get_text(strip=True)

            if "/news/" in href and len(text) > 20 and len(text) < 300:
                full_url = href if href.startswith("http") else f"https://www.nba.com{href}"
                articles.append({
                    "SOURCE": "NBA_COM",
                    "TITLE": text[:200],
                    "SUMMARY": "",
                    "LINK": full_url,
                    "PUBLISHED": datetime.now().strftime("%Y-%m-%d"),
                })

        seen = set()
        unique = []
        for a in articles:
            if a["TITLE"] not in seen:
                seen.add(a["TITLE"])
                unique.append(a)

        print(f"  Found {len(unique)} headlines from NBA.com")
        return unique

    except Exception as e:
        print(f"  NBA.com scrape failed: {e}")
        return []


def tag_teams(df):
    """Tag each article with mentioned NBA teams."""
    print("Tagging articles with team mentions...")

    def find_teams(text):
        text_lower = str(text).lower()
        mentioned = []
        for team_abb, keywords in TEAM_KEYWORDS.items():
            for keyword in keywords:
                if keyword in text_lower:
                    mentioned.append(team_abb)
                    break
        return ",".join(mentioned) if mentioned else "GENERAL"

    df["TEAMS_MENTIONED"] = (df["TITLE"].fillna("") + " " + df["SUMMARY"].fillna("")).apply(find_teams)
    return df


def add_sentiment(df, analyzer):
    """Add VADER sentiment scores using title + summary."""
    print("Running sentiment analysis on articles...")

    def score_text(row):
        text = f"{row.get('TITLE', '')} {row.get('SUMMARY', '')}".strip()
        if not text:
            return pd.Series({
                "SENTIMENT_POS": 0.0,
                "SENTIMENT_NEG": 0.0,
                "SENTIMENT_NEU": 1.0,
                "SENTIMENT_COMPOUND": 0.0,
            })
        scores = analyzer.polarity_scores(text)
        return pd.Series({
            "SENTIMENT_POS": scores["pos"],
            "SENTIMENT_NEG": scores["neg"],
            "SENTIMENT_NEU": scores["neu"],
            "SENTIMENT_COMPOUND": scores["compound"],
        })

    sentiment_df = df.apply(score_text, axis=1)
    return pd.concat([df, sentiment_df], axis=1)


def build_team_sentiment(df):
    """Aggregate article-level sentiment to team-level sentiment."""
    team_rows = []

    for team in TEAM_KEYWORDS.keys():
        team_df = df[df["TEAMS_MENTIONED"].fillna("").apply(lambda x: team in str(x).split(","))]

        if len(team_df) == 0:
            team_rows.append({
                "TEAM": team,
                "ARTICLE_COUNT": 0,
                "AVG_SENTIMENT": 0.0,
                "POSITIVE_ARTICLE_COUNT": 0,
                "NEGATIVE_ARTICLE_COUNT": 0,
            })
        else:
            team_rows.append({
                "TEAM": team,
                "ARTICLE_COUNT": len(team_df),
                "AVG_SENTIMENT": team_df["SENTIMENT_COMPOUND"].mean(),
                "POSITIVE_ARTICLE_COUNT": (team_df["SENTIMENT_COMPOUND"] > 0.05).sum(),
                "NEGATIVE_ARTICLE_COUNT": (team_df["SENTIMENT_COMPOUND"] < -0.05).sum(),
            })

    return pd.DataFrame(team_rows)


def main():
    print("=" * 60)
    print("NBA News Pipeline - Step 5")
    print("=" * 60)

    analyzer = setup_sentiment_analyzer()
    all_articles = []

    rss_articles = try_rss_feeds()
    all_articles.extend(rss_articles)

    espn_articles = scrape_espn_nba_news()
    all_articles.extend(espn_articles)

    nba_articles = scrape_nba_com_news()
    all_articles.extend(nba_articles)

    if not all_articles:
        print("\nNo articles from any source. Creating empty schema.")
        df = pd.DataFrame(columns=[
            "SOURCE", "TITLE", "SUMMARY", "LINK", "PUBLISHED",
            "TEAMS_MENTIONED", "SENTIMENT_POS", "SENTIMENT_NEG",
            "SENTIMENT_NEU", "SENTIMENT_COMPOUND"
        ])
        team_sentiment_df = pd.DataFrame(columns=[
            "TEAM", "ARTICLE_COUNT", "AVG_SENTIMENT",
            "POSITIVE_ARTICLE_COUNT", "NEGATIVE_ARTICLE_COUNT"
        ])
    else:
        df = pd.DataFrame(all_articles)
        df = df.drop_duplicates(subset=["TITLE"]).reset_index(drop=True)
        df = tag_teams(df)

        if analyzer is not None:
            df = add_sentiment(df, analyzer)
        else:
            df["SENTIMENT_POS"] = 0.0
            df["SENTIMENT_NEG"] = 0.0
            df["SENTIMENT_NEU"] = 1.0
            df["SENTIMENT_COMPOUND"] = 0.0

        team_sentiment_df = build_team_sentiment(df)

    df.to_csv(f"{DATA_DIR}/news_articles.csv", index=False)
    team_sentiment_df.to_csv(f"{DATA_DIR}/team_sentiment.csv", index=False)

    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Total unique articles: {len(df)}")

    if len(df) > 0:
        print(f"Sources: {df['SOURCE'].value_counts().to_dict()}")

        team_counts = {}
        for teams in df["TEAMS_MENTIONED"]:
            for t in str(teams).split(","):
                if t:
                    team_counts[t] = team_counts.get(t, 0) + 1

        top_teams = sorted(team_counts.items(), key=lambda x: -x[1])[:10]
        print(f"Most mentioned teams: {dict(top_teams)}")
        print(f"Average compound sentiment: {df['SENTIMENT_COMPOUND'].mean():.3f}")

        print()
        print("Sample headlines:")
        for _, row in df.head(5).iterrows():
            print(f"  [{row['SOURCE']}] {row['TITLE'][:80]} | sentiment={row['SENTIMENT_COMPOUND']:.3f}")

        print()
        print("Top team sentiment rows:")
        print(team_sentiment_df.sort_values("ARTICLE_COUNT", ascending=False).head(10).to_string(index=False))

    print()
    print(f"Saved to {DATA_DIR}/news_articles.csv")
    print(f"Saved to {DATA_DIR}/team_sentiment.csv")


if __name__ == "__main__":
    main()