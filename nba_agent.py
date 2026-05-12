"""
Step 7: NBA Betting Agent
ReAct-style agent that gathers data from multiple tools and produces
a structured pre-game betting report.

This is the core of the project. The agent:
1. Takes an upcoming game (e.g., "LAL vs BOS")
2. Plans which tools to call
3. Gathers data iteratively (odds, stats, injuries, vector store)
4. Reasons through the evidence
5. Produces a structured betting report with win probabilities

Usage:
    export ANTHROPIC_API_KEY="your_key_here"  (or OPENAI_API_KEY)
    python nba_agent.py

Requires: steps 1-3 and 6 to be completed (data/ and chroma_db/ populated)
"""

import ast
import os
import json
import re
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# ============================================================
# TOOL DEFINITIONS - each tool queries a different data source
# ============================================================

DATA_DIR = "data"

# Maximum number of characters retained from a tool observation before truncation.
# Override at runtime via the NBA_MAX_OBSERVATION_CHARS env var.
MAX_TOOL_OBSERVATION_CHARS = int(os.environ.get("NBA_MAX_OBSERVATION_CHARS", "3000"))

_TEAM_ABBR_LOOKUP = None


# ============================================================
# INFO DENSITY HELPERS
# ============================================================
# Per-game counters that quantify how much real information an LLM saw before
# committing to a prediction. We thread these through every reasoning system
# (single agent, multi-agent debate, CoT baseline) so the backtest can compare
# accuracy vs information intake.

def empty_info_density():
    """Initial info-density counters for one game."""
    return {
        "youtube_comments": 0,
        "news_articles": 0,
        "vector_hits": 0,
        "context_tokens": 0,
    }


def count_tool_result_items(tool_name, result_str):
    """
    Map a tool result string back to (youtube_comments, news_articles, vector_hits)
    deltas. Returns a dict with the three count keys; missing keys default to 0.

    The function is best-effort: tool results are JSON in the happy path but
    can be plain error strings, so we never raise.
    """
    delta = {"youtube_comments": 0, "news_articles": 0, "vector_hits": 0}
    if not result_str:
        return delta

    text = str(result_str)
    # Skip error / empty payloads.
    if text.startswith("Error") or text.startswith("No "):
        return delta

    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return delta

    if tool_name == "search_similar_games":
        # Tool returns a JSON list of {game_description, metadata}.
        if isinstance(parsed, list):
            delta["vector_hits"] = len(parsed)
        return delta

    if tool_name == "get_team_sentiment":
        # Tool returns a single dict per team. Extract whichever count keys
        # the underlying CSV exposes. Today that's article_count (news);
        # once YouTube is wired in, COMMENT_COUNT will populate alongside.
        if isinstance(parsed, dict):
            news = parsed.get("article_count") or parsed.get("ARTICLE_COUNT") or 0
            yt = (
                parsed.get("comment_count")
                or parsed.get("COMMENT_COUNT")
                or parsed.get("youtube_comment_count")
                or 0
            )
            try:
                delta["news_articles"] = int(news)
            except (TypeError, ValueError):
                pass
            try:
                delta["youtube_comments"] = int(yt)
            except (TypeError, ValueError):
                pass
        return delta

    return delta


def merge_info_density(target, observation_tool, observation_text):
    """
    Update an info_density dict in place using one tool observation. Returns
    the updated dict for chaining.
    """
    deltas = count_tool_result_items(observation_tool, observation_text)
    for k, v in deltas.items():
        target[k] = target.get(k, 0) + int(v)
    return target


def normalize_season_label(season):
    """Normalize common LLM season strings to NBA API form, e.g. 2024-25."""
    if season is None:
        return None

    s = str(season).strip()
    if re.fullmatch(r"\d{4}-\d{2}", s):
        return s

    match = re.fullmatch(r"(\d{4})[-/](\d{4})", s)
    if match:
        start, end = match.groups()
        return f"{start}-{end[-2:]}"

    match = re.fullmatch(r"(\d{4})[-/](\d{2})", s)
    if match:
        start, end = match.groups()
        return f"{start}-{end}"

    if re.fullmatch(r"\d{4}", s):
        start_year = int(s)
        return f"{start_year}-{str(start_year + 1)[-2:]}"

    return s


def normalize_team_abbreviation(team):
    """Map full names / nicknames / cities to NBA abbreviations when possible."""
    if team is None:
        return None

    raw = str(team).strip()
    if not raw:
        return raw

    upper = raw.upper()
    if re.fullmatch(r"[A-Z]{2,3}", upper):
        return upper

    global _TEAM_ABBR_LOOKUP
    if _TEAM_ABBR_LOOKUP is None:
        lookup = {
            "la clippers": "LAC",
            "l.a. clippers": "LAC",
            "los angeles clippers": "LAC",
            "la lakers": "LAL",
            "l.a. lakers": "LAL",
            "los angeles lakers": "LAL",
            "indianapolis": "IND",
        }
        teams_path = f"{DATA_DIR}/teams.csv"
        if os.path.exists(teams_path):
            try:
                teams = pd.read_csv(teams_path)
                for _, row in teams.iterrows():
                    abbr = str(row.get("abbreviation", "")).upper()
                    if not abbr:
                        continue
                    for col in ("full_name", "nickname"):
                        val = str(row.get(col, "")).strip().lower()
                        if val:
                            lookup[val] = abbr
                    city = str(row.get("city", "")).strip().lower()
                    if city and city != "los angeles":
                        lookup.setdefault(city, abbr)
            except Exception:
                pass
        _TEAM_ABBR_LOOKUP = lookup

    return _TEAM_ABBR_LOOKUP.get(raw.lower(), raw)


def tool_get_team_stats(team_abbr, season=None, as_of_date=None):
    """
    Get recent team stats and form.

    When as_of_date (YYYY-MM-DD string or pandas Timestamp) is provided, only
    games strictly before that date are considered. Default None preserves the
    Streamlit behaviour (no filtering).
    """
    try:
        team_abbr = normalize_team_abbreviation(team_abbr)
        game_logs = pd.read_csv(f"{DATA_DIR}/game_logs.csv")
        game_logs["GAME_DATE"] = pd.to_datetime(game_logs["GAME_DATE"], errors="coerce")

        if as_of_date is not None:
            cutoff = pd.to_datetime(as_of_date, errors="coerce")
            if pd.notna(cutoff):
                game_logs = game_logs[game_logs["GAME_DATE"] < cutoff].copy()

        team_all = game_logs[game_logs["TEAM_ABBREVIATION"] == team_abbr].copy()
        if team_all.empty:
            return f"No data found for {team_abbr}."

        # If no season is passed, choose the season of the most recent available game
        if season is None:
            latest_row = team_all.sort_values("GAME_DATE", ascending=False).iloc[0]
            season = latest_row["SEASON"]
        else:
            season = normalize_season_label(season)

        team_games = (
            team_all[team_all["SEASON"] == season]
            .sort_values("GAME_DATE", ascending=False)
            .copy()
        )

        if team_games.empty:
            return f"No data found for {team_abbr} in {season}."

        last_10 = team_games.head(10)

        wins = int((team_games["WIN"] == 1).sum())
        losses = int((team_games["WIN"] == 0).sum())
        last_10_wins = int((last_10["WIN"] == 1).sum())
        last_10_losses = int((last_10["WIN"] == 0).sum())

        result = {
            "team": team_abbr,
            "season": season,
            "season_record": f"{wins}-{losses}",
            "last_10_record": f"{last_10_wins}-{last_10_losses}",
            "avg_points_last_10": round(last_10["PTS"].mean(), 1),
            "avg_fg_pct_last_10": round(last_10["FG_PCT"].mean(), 3),
            "avg_fg3_pct_last_10": round(last_10["FG3_PCT"].mean(), 3),
            "avg_rebounds_last_10": round(last_10["REB"].mean(), 1),
            "avg_assists_last_10": round(last_10["AST"].mean(), 1),
            "avg_turnovers_last_10": round(last_10["TOV"].mean(), 1),
            "avg_plus_minus_last_10": round(last_10["PLUS_MINUS"].mean(), 1),
            "last_game": {
                "date": str(team_games.iloc[0]["GAME_DATE"])[:10],
                "matchup": team_games.iloc[0]["MATCHUP"],
                "result": "W" if team_games.iloc[0]["WIN"] == 1 else "L",
                "points": int(team_games.iloc[0]["PTS"]),
            },
            "back_to_back_today": int(team_games.iloc[0].get("BACK_TO_BACK", 0)) if len(team_games) > 0 else 0,
        }
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error getting stats for {team_abbr}: {e}"


def tool_get_head_to_head(team1_abbr, team2_abbr, as_of_date=None):
    """
    Get head-to-head record between two teams.

    The H2H CSV is aggregated per season and has no per-game date column. When
    as_of_date is provided, we conservatively drop seasons whose start year is
    >= the as_of_date year so the agent never sees an aggregate that mixes in
    games played after the prediction cutoff. Default None preserves the
    Streamlit behaviour.
    """
    try:
        team1_abbr = normalize_team_abbreviation(team1_abbr)
        team2_abbr = normalize_team_abbreviation(team2_abbr)
        h2h = pd.read_csv(f"{DATA_DIR}/head_to_head.csv")

        if as_of_date is not None:
            cutoff = pd.to_datetime(as_of_date, errors="coerce")
            if pd.notna(cutoff):
                # SEASON column is e.g. "2023-24"; the leading 4 digits are the
                # start year. Keep only seasons that started strictly before
                # the as_of_date's year. This is conservative — it also drops
                # earlier-season games of the in-progress season — but avoids
                # leaking any post-cutoff games via the aggregate row.
                h2h = h2h[
                    pd.to_numeric(h2h["SEASON"].astype(str).str[:4], errors="coerce")
                    < cutoff.year
                ].copy()

        matchup = h2h[
            (h2h["TEAM_ABBREVIATION"] == team1_abbr) &
            (h2h["OPPONENT_ABB"] == team2_abbr)
        ]

        if matchup.empty:
            return f"No H2H data for {team1_abbr} vs {team2_abbr}."

        result = {
            "matchup": f"{team1_abbr} vs {team2_abbr}",
            "seasons": [],
        }
        for _, row in matchup.iterrows():
            result["seasons"].append({
                "season": row["SEASON"],
                "games": int(row["GAMES"]),
                "wins": int(row["WINS"]),
                "losses": int(row["LOSSES"]),
                "win_pct": round(row["WIN_PCT"], 3),
                "avg_points": round(row["AVG_PTS"], 1),
                "avg_plus_minus": round(row["AVG_PLUS_MINUS"], 1),
            })

        total_games = matchup["GAMES"].sum()
        total_wins = matchup["WINS"].sum()
        result["overall"] = {
            "total_games": int(total_games),
            "total_wins": int(total_wins),
            "total_losses": int(total_games - total_wins),
            "overall_win_pct": round(total_wins / total_games, 3) if total_games > 0 else 0,
        }
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error getting H2H: {e}"


def tool_get_injuries(team_name=None, as_of_date=None):
    """
    Get current injury report. Optionally filter by team.

    The injuries CSV is a live snapshot scraped today and carries no
    historical date column. When as_of_date is provided we cannot reconstruct
    that day's injury list, so we return a clear "no historical snapshot"
    message instead of leaking today's injuries into a backtest.
    """
    if as_of_date is not None:
        return (
            f"No historical injury snapshot available for {as_of_date}. "
            "The injuries CSV is a live scrape with no per-day history; "
            "use stats / H2H / vector hits to reason about availability."
        )
    try:
        injuries = pd.read_csv(f"{DATA_DIR}/injuries.csv")
        if injuries.empty:
            return "No injury data available."

        if team_name:
            # Fuzzy match on team name
            team_injuries = injuries[
                injuries["TEAM"].str.contains(team_name, case=False, na=False)
            ]
        else:
            team_injuries = injuries

        if team_injuries.empty:
            return f"No injuries found for {team_name}."

        result = []
        for _, row in team_injuries.iterrows():
            result.append({
                "team": row.get("TEAM", ""),
                "player": row.get("PLAYER_NAME", ""),
                "position": row.get("POSITION", ""),
                "status": row.get("STATUS", ""),
                "est_return": row.get("EST_RETURN", ""),
                "comment": str(row.get("COMMENT", ""))[:200],
            })
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error getting injuries: {e}"

def tool_get_team_sentiment(team_abbr, as_of_date=None):
    """
    Get team-level media/news sentiment from aggregated news coverage.

    The aggregate sentiment CSV typically has no per-row date column. If a
    SCRAPE_DATE / DATE column is present and as_of_date is supplied, we drop
    rows scraped on or after that date. Otherwise as_of_date returns a
    "no historical sentiment snapshot" message — better than silently leaking
    today's sentiment into a past prediction.
    """
    try:
        team_abbr = normalize_team_abbreviation(team_abbr)
        sentiment = pd.read_csv(f"{DATA_DIR}/team_sentiment.csv")

        if as_of_date is not None:
            cutoff = pd.to_datetime(as_of_date, errors="coerce")
            date_col = next(
                (c for c in ("SCRAPE_DATE", "DATE", "GAME_DATE") if c in sentiment.columns),
                None,
            )
            if pd.isna(cutoff):
                pass
            elif date_col is None:
                return (
                    f"No historical sentiment snapshot available for {as_of_date}. "
                    "The team_sentiment CSV has no date column."
                )
            else:
                sentiment = sentiment[
                    pd.to_datetime(sentiment[date_col], errors="coerce") < cutoff
                ].copy()

        team_row = sentiment[sentiment["TEAM"] == team_abbr]

        if team_row.empty:
            return f"No sentiment data found for {team_abbr}."

        row = team_row.iloc[0]
        result = {
            "team": row["TEAM"],
            "article_count": int(row["ARTICLE_COUNT"]),
            "avg_sentiment": round(float(row["AVG_SENTIMENT"]), 3),
            "positive_article_count": int(row["POSITIVE_ARTICLE_COUNT"]),
            "negative_article_count": int(row["NEGATIVE_ARTICLE_COUNT"]),
            "sentiment_label": (
                "positive" if float(row["AVG_SENTIMENT"]) > 0.05
                else "negative" if float(row["AVG_SENTIMENT"]) < -0.05
                else "neutral"
            ),
        }
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error getting sentiment for {team_abbr}: {e}"

def tool_get_odds(home_team=None, away_team=None, as_of_date=None):
    """
    Get current betting odds for upcoming games.

    The odds_live CSV is a snapshot of upcoming-game odds; it cannot represent
    historical lines. When as_of_date is provided we return a clear message
    so the agent knows to skip market-derived reasoning during backtests
    (the backtest script matches the historical line separately).
    """
    if as_of_date is not None:
        return (
            f"No live odds snapshot available for {as_of_date}. "
            "Live odds reflect upcoming games only; historical lines are "
            "matched separately by the backtest harness."
        )
    try:
        odds = pd.read_csv(f"{DATA_DIR}/odds_live.csv")
        if odds.empty:
            return "No live odds data available."

        # Filter to moneyline (h2h) market
        h2h_odds = odds[odds["MARKET"] == "h2h"]

        if home_team:
            h2h_odds = h2h_odds[
                (h2h_odds["HOME_TEAM"].str.contains(home_team, case=False, na=False)) |
                (h2h_odds["AWAY_TEAM"].str.contains(home_team, case=False, na=False))
            ]
        if away_team:
            h2h_odds = h2h_odds[
                (h2h_odds["HOME_TEAM"].str.contains(away_team, case=False, na=False)) |
                (h2h_odds["AWAY_TEAM"].str.contains(away_team, case=False, na=False))
            ]

        if h2h_odds.empty:
            return (
                f"No live odds found for {home_team} vs {away_team}. "
                f"This selected matchup does not appear in the current upcoming-games odds feed, "
                f"so these teams may not actually be scheduled to play each other right now. "
                f"Choose a matchup that exists in the live odds feed to enable value assessment."
            )

        # Group by game and summarize
        games = {}
        for _, row in h2h_odds.iterrows():
            game_id = row["GAME_ID"]
            if game_id not in games:
                games[game_id] = {
                    "home_team": row["HOME_TEAM"],
                    "away_team": row["AWAY_TEAM"],
                    "commence_time": row["COMMENCE_TIME"],
                    "bookmakers": {},
                }
            book = row["BOOKMAKER"]
            if book not in games[game_id]["bookmakers"]:
                games[game_id]["bookmakers"][book] = {}
            games[game_id]["bookmakers"][book][row["OUTCOME_NAME"]] = {
                "price": row["PRICE"],
                "implied_prob": round(row.get("IMPLIED_PROB", 0), 3),
            }

        return json.dumps(list(games.values()), indent=2)
    except Exception as e:
        return f"Error getting odds: {e}"


def tool_search_similar_games(query_text, team=None, n_results=5, as_of_date=None):
    """
    Search the vector store for historically similar games.

    When as_of_date is provided, results whose metadata.game_date is on or
    after the cutoff are dropped post-retrieval. We over-fetch (3x) so we
    still return up to n_results valid hits in most cases.
    """
    try:
        from nba_vector_store import query_similar_games

        where_filter = None
        if team:
            where_filter = {"team": normalize_team_abbreviation(team)}

        # Over-fetch when filtering so we can drop leaked rows and still
        # return n_results historically-valid hits.
        fetch_count = n_results * 3 if as_of_date is not None else n_results
        results = query_similar_games(query_text, n_results=fetch_count, where_filter=where_filter)

        output = []
        cutoff = pd.to_datetime(as_of_date, errors="coerce") if as_of_date is not None else None

        for i in range(len(results["documents"][0])):
            meta = results["metadatas"][0][i]
            if cutoff is not None and pd.notna(cutoff):
                game_date = pd.to_datetime(meta.get("game_date"), errors="coerce")
                if pd.notna(game_date) and game_date >= cutoff:
                    continue
            output.append({
                "game_description": results["documents"][0][i],
                "metadata": meta,
            })
            if len(output) >= n_results:
                break
        return json.dumps(output, indent=2)
    except Exception as e:
        return f"Error searching similar games: {e}"


# ============================================================
# TOOL REGISTRY
# ============================================================

TOOLS = {
    "get_team_stats": {
        "function": tool_get_team_stats,
        "description": "Get a team's recent stats, record, and form. Args: team_abbr (e.g. 'LAL', 'BOS'), season (optional, default '2024-25')",
    },
    "get_head_to_head": {
        "function": tool_get_head_to_head,
        "description": "Get head-to-head record between two teams. Args: team1_abbr, team2_abbr",
    },
    "get_injuries": {
        "function": tool_get_injuries,
        "description": "Get current injury report for a team. Args: team_name (e.g. 'Lakers', 'Celtics')",
    },
    "get_odds": {
        "function": tool_get_odds,
        "description": "Get current betting odds from multiple sportsbooks. Args: home_team, away_team (team city names)",
    },
    "search_similar_games": {
        "function": tool_search_similar_games,
        "description": "Search historical games for similar situations. Args: query_text (natural language), team (optional, team abbreviation), n_results (optional, default 5)",
    },
    "get_team_sentiment": {
    "function": tool_get_team_sentiment,
    "description": "Get recent team-level media/news sentiment. Args: team_abbr (e.g. 'LAL', 'BOS')",
    },
}


# ============================================================
# AGENT LOGIC
# ============================================================

def build_system_prompt():
    """Build the system prompt for the ReAct agent."""
    tool_descriptions = "\n".join([
        f"  - {name}: {info['description']}"
        for name, info in TOOLS.items()
    ])

    return f"""You are an NBA pre-game betting analyst. Your job is to analyze an upcoming NBA game 
and produce a structured betting report.

CRITICAL RULES:
- You MUST call tools to get real data. Do NOT use your own knowledge for any stats, odds, records, or injury info.
- You MUST call at least 4 different tools before producing a FINAL REPORT.
- Every number in your report must come from a tool observation, not from your training data.
- If you produce a FINAL REPORT without calling tools first, it will be rejected.
- Call ONE tool per response. Do not call multiple tools in the same message.
- You SHOULD call get_team_sentiment for both teams before producing the FINAL REPORT.
- If odds are unavailable, you must explicitly explain that the selected matchup does not appear in the current upcoming-games odds feed and tell the user to choose a matchup that actually exists in the live odds feed.

You have access to the following tools:
{tool_descriptions}

Follow the ReAct pattern:
1. THOUGHT: Think about what information you need next
2. ACTION: Call exactly one tool to get that information
3. Wait for the OBSERVATION (the tool result will be provided to you)
4. Repeat steps 1-3 until you have called at least 4 tools and gathered enough data
5. FINAL REPORT: Only after gathering real data, produce the structured betting report

When calling a tool, use this exact format (one tool per message):
ACTION: tool_name(arg1="value1", arg2="value2")

START by calling get_team_stats for the home team. Do NOT skip to the final report.

When you have gathered enough information from tools, produce a FINAL REPORT with this structure:

FINAL REPORT:
{{
    "game": "TEAM1 vs TEAM2",
    "date": "YYYY-MM-DD",
    "market_odds": {{
        "home_team": {{"name": "...", "avg_implied_prob": 0.XX}},
        "away_team": {{"name": "...", "avg_implied_prob": 0.XX}}
    }},
    "agent_prediction": {{
        "home_win_prob": 0.XX,
        "away_win_prob": 0.XX,
        "confidence": "high/medium/low"
    }},
    "key_factors": [
        {{"factor": "...", "impact": "favors_home/favors_away/neutral", "importance": "high/medium/low"}},
    ],
    "reasoning": "Step-by-step reasoning chain...",
        "value_assessment": "Does the agent see value vs the market? Where and why? If no live odds are available, explicitly say that the selected matchup does not appear in the current upcoming-games odds feed and tell the user to choose a real upcoming matchup from the live odds feed."
}}

Be thorough but efficient. Gather stats for both teams, check injuries, look at odds,
check team media/news sentiment, and search for historical precedent. Then reason through it all step by step."""


def parse_action(text):
    """Parse an ACTION line from the agent's response."""
    if "ACTION:" not in text:
        return None, None, None

    action_line = text.split("ACTION:")[-1].strip().split("\n")[0]
    action_line = action_line.strip().strip("`").strip()
    action_line = action_line.lstrip("-• ").strip()
    action_line = action_line.replace("**", "").strip()

    # Parse tool_name(arg1="val1", arg2="val2")
    match = re.search(
        r"\b(get_team_stats|get_head_to_head|get_injuries|get_odds|search_similar_games|get_team_sentiment)\s*\(",
        action_line,
    )
    if not match:
        return None, None, None

    tool_name = match.group(1)
    call_str = action_line[match.start():].strip()
    args_str = call_str.split("(", 1)[1].rsplit(")", 1)[0]

    # Parse keyword arguments
    kwargs = {}
    if args_str.strip():
        try:
            parsed = ast.parse(f"_tool({args_str})", mode="eval").body
            if parsed.args:
                first_arg = ast.literal_eval(parsed.args[0])
                if isinstance(first_arg, dict):
                    kwargs.update(first_arg)
            for keyword in parsed.keywords:
                if keyword.arg is not None:
                    kwargs[keyword.arg] = ast.literal_eval(keyword.value)
        except (SyntaxError, ValueError, TypeError):
            # Fallback for loose LLM formatting. Handles key="value",
            # key='value', and key=value until the next comma.
            pairs = re.findall(r'(\w+)\s*=\s*"([^"]*)"', args_str)
            if not pairs:
                pairs = re.findall(r"(\w+)\s*=\s*'([^']*)'", args_str)
            if not pairs:
                pairs = re.findall(r"(\w+)\s*=\s*([^,\)]+)", args_str)

            for key, val in pairs:
                kwargs[key.strip()] = val.strip().strip('"').strip("'")

    return tool_name, kwargs, action_line


def call_tool(tool_name, kwargs):
    """Execute a tool call and return the result."""
    if tool_name not in TOOLS:
        return f"Unknown tool: {tool_name}. Available tools: {list(TOOLS.keys())}"

    func = TOOLS[tool_name]["function"]
    try:
        result = func(**kwargs)
        return result
    except TypeError as e:
        return f"Error calling {tool_name}: {e}. Check your arguments."
    except Exception as e:
        return f"Error: {e}"


def run_agent(game_description, llm_call_fn, max_steps=12):
    """
    Run the ReAct agent loop.

    Args:
        game_description: e.g. "Los Angeles Lakers vs Boston Celtics, March 30 2026"
        llm_call_fn: function that takes messages list and returns response text
        max_steps: maximum number of tool calls before forcing final report

    Returns:
        dict with the conversation history, final report, and info_density
        counters (youtube_comments, news_articles, vector_hits, context_tokens).
    """
    from nba_cost_logger import tally_calls

    system_prompt = build_system_prompt()

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Analyze this upcoming game and produce a betting report: {game_description}"},
    ]

    conversation_log = []
    info_density = empty_info_density()
    step = 0

    print(f"\nAnalyzing: {game_description}")
    print("=" * 60)

    with tally_calls() as call_records:
        while step < max_steps:
            # Call the LLM
            response_text = llm_call_fn(messages)

            # Log it
            conversation_log.append({
                "step": step + 1,
                "role": "assistant",
                "content": response_text,
            })

            # Check if we have a final report
            if "FINAL REPORT:" in response_text:
                print(f"\nStep {step + 1}: FINAL REPORT generated")
                info_density["context_tokens"] = sum(
                    int(r.get("input_tokens", 0) or 0) for r in call_records
                )
                return {
                    "conversation": conversation_log,
                    "final_response": response_text,
                    "steps": step + 1,
                    "info_density": info_density,
                }

            # Parse and execute action
            tool_name, kwargs, action_line = parse_action(response_text)

            if tool_name:
                print(f"Step {step + 1}: ACTION - {tool_name}({kwargs})")

                # Call the tool
                observation = call_tool(tool_name, kwargs)

                # Update info-density counters BEFORE truncating, so we count
                # full result size (e.g. all vector hits, full sentiment row).
                merge_info_density(info_density, tool_name, observation)

                # Truncate long observations
                if len(observation) > MAX_TOOL_OBSERVATION_CHARS:
                    observation = observation[:MAX_TOOL_OBSERVATION_CHARS] + "\n... (truncated)"

                print(f"  OBSERVATION: {observation[:150]}...")

                # Add to conversation
                messages.append({"role": "assistant", "content": response_text})
                messages.append({"role": "user", "content": f"OBSERVATION: {observation}"})

                conversation_log.append({
                    "step": step + 1,
                    "role": "tool",
                    "tool": tool_name,
                    "args": kwargs,
                    "result": observation[:500],
                })
            else:
                # No action found, add response and ask agent to continue
                messages.append({"role": "assistant", "content": response_text})
                messages.append({"role": "user", "content": "Continue your analysis. Use a tool or produce the FINAL REPORT."})

            step += 1

        # If we hit max steps, ask for final report
        messages.append({"role": "user", "content": "You've gathered enough data. Produce the FINAL REPORT now."})
        response_text = llm_call_fn(messages)
        conversation_log.append({
            "step": step + 1,
            "role": "assistant",
            "content": response_text,
        })

        info_density["context_tokens"] = sum(
            int(r.get("input_tokens", 0) or 0) for r in call_records
        )

    return {
        "conversation": conversation_log,
        "final_response": response_text,
        "steps": step + 1,
        "info_density": info_density,
    }


# ============================================================
# LLM CALL FUNCTIONS (choose one)
# ============================================================

def call_anthropic(messages):
    """Call Claude API."""
    import anthropic
    from nba_cost_logger import log_anthropic_response

    client = anthropic.Anthropic()

    # Convert messages format: separate system from conversation
    system_msg = ""
    conv_messages = []
    for msg in messages:
        if msg["role"] == "system":
            system_msg = msg["content"]
        else:
            conv_messages.append(msg)

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4096,
        system=system_msg,
        messages=conv_messages,
    )
    log_anthropic_response("nba_agent.py", response)
    return response.content[0].text


def call_openai(messages):
    """Call OpenAI API."""
    from openai import OpenAI
    from nba_cost_logger import log_openai_response

    client = OpenAI()
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        max_tokens=4096,
    )
    log_openai_response("nba_agent.py", response)
    return response.choices[0].message.content


def call_mock(messages):
    """Mock LLM for testing without API keys."""
    last_msg = messages[-1]["content"]

    if "Analyze this upcoming game" in last_msg:
        return """THOUGHT: I need to gather information about both teams. Let me start with the home team's stats.

ACTION: get_team_stats(team_abbr="LAL")"""

    elif "OBSERVATION" in last_msg and "get_team_stats" in str(messages[-3].get("content", "")):
        if "LAL" in str(messages[-3].get("content", "")):
            return """THOUGHT: Got Lakers stats. Now let me get the away team's stats.

ACTION: get_team_stats(team_abbr="BOS")"""
        else:
            return """THOUGHT: Got both teams' stats. Let me check the odds.

ACTION: get_odds(home_team="Lakers", away_team="Celtics")"""

    elif "OBSERVATION" in last_msg and "get_odds" in str(messages[-3].get("content", "")):
        return """THOUGHT: Got the odds. Let me check injuries for both teams.

ACTION: get_injuries(team_name="Lakers")"""

    elif "OBSERVATION" in last_msg and "injuries" in str(messages[-3].get("content", "")).lower():
        return """THOUGHT: I have enough information. Let me produce the final report.

FINAL REPORT:
{
    "game": "LAL vs BOS",
    "date": "2026-03-30",
    "market_odds": {
        "home_team": {"name": "Los Angeles Lakers", "avg_implied_prob": 0.45},
        "away_team": {"name": "Boston Celtics", "avg_implied_prob": 0.55}
    },
    "agent_prediction": {
        "home_win_prob": 0.42,
        "away_win_prob": 0.58,
        "confidence": "medium"
    },
    "key_factors": [
        {"factor": "Mock analysis - replace with real LLM", "impact": "neutral", "importance": "high"}
    ],
    "reasoning": "This is a mock response for testing. Use a real LLM API for actual analysis.",
    "value_assessment": "Mock assessment. No real value detected in this test."
}"""

    else:
        return """THOUGHT: Let me continue gathering data.

ACTION: get_team_stats(team_abbr="BOS")"""


# ============================================================
# MAIN
# ============================================================

def main():
    print("=" * 60)
    print("NBA Betting Agent - Step 7")
    print("=" * 60)

    # Choose LLM backend
    if os.environ.get("ANTHROPIC_API_KEY"):
        print("Using Claude (Anthropic) API")
        llm_fn = call_anthropic
    elif os.environ.get("OPENAI_API_KEY"):
        print("Using GPT-4 (OpenAI) API")
        llm_fn = call_openai
    else:
        print("No API key found. Using mock LLM for testing.")
        print("Set ANTHROPIC_API_KEY or OPENAI_API_KEY for real analysis.")
        llm_fn = call_mock

    # Test game
    game = "Los Angeles Lakers vs Boston Celtics, March 30 2026"

    result = run_agent(game, llm_fn)

    # Print final report
    print()
    print("=" * 60)
    print("FINAL REPORT")
    print("=" * 60)

    # Extract the report JSON from the response
    final = result["final_response"]
    if "FINAL REPORT:" in final:
        report_text = final.split("FINAL REPORT:")[-1].strip()
        print(report_text)
    else:
        print(final)

    print()
    print(f"Total agent steps: {result['steps']}")
    print()

    # Save the full conversation log
    log_path = f"{DATA_DIR}/agent_log.json"
    with open(log_path, "w") as f:
        json.dump(result["conversation"], f, indent=2)
    print(f"Conversation log saved to {log_path}")


if __name__ == "__main__":
    main()
