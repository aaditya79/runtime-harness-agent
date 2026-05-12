"""
nba_backtest.py

Historical backtest for MatchOdds AI.

Adds:
- cache by game/method
- retry with exponential backoff
- run metadata for research page

Outputs:
    data/backtest_predictions.csv
    data/backtest_summary.csv
    data/backtest_calibration.csv
    data/backtest_run_metadata.json
    data/backtest_cache/*.json
"""

import contextlib
import os
import json
import math
import time
import random
import argparse
import functools
import pandas as pd
import numpy as np
from dotenv import load_dotenv

load_dotenv()

# Real reasoning entry points. The previous version of this file used local
# static-prompt helpers and never invoked the live agent / tool stack — it was
# essentially a different model from what Streamlit shipped. Wave 2 wires the
# backtest into the same code path as the production app.
from nba_agent import run_agent
from nba_cot_baseline import run_cot_analysis
from nba_multi_agent import run_full_debate

DATA_DIR = "data"
PREDICTIONS_OUT = f"{DATA_DIR}/backtest_predictions.csv"
SUMMARY_OUT = f"{DATA_DIR}/backtest_summary.csv"
CALIBRATION_OUT = f"{DATA_DIR}/backtest_calibration.csv"
RUN_META_OUT = f"{DATA_DIR}/backtest_run_metadata.json"

CACHE_DIR = f"{DATA_DIR}/backtest_cache"
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(CACHE_DIR, exist_ok=True)


# ============================================================
# ABLATION CONFIG
# ============================================================
# Each name maps a single data source on the project to (a) the tool functions
# in nba_agent that should be replaced with a "DISABLED" marker and (b) the
# snapshot keys that should be scrubbed when feeding the static-prompt
# backtest. Wave 2 agents will exercise the tool monkeypatch path; today's
# static-prompt backtest also benefits from the snapshot scrub.
ABLATION_SOURCES = {
    "youtube":      {"tools": ["tool_get_team_sentiment"], "snapshot_keys": []},
    "news":         {"tools": ["tool_get_team_sentiment"], "snapshot_keys": []},
    "odds":         {"tools": ["tool_get_odds"],            "snapshot_keys": []},
    "injuries":     {"tools": ["tool_get_injuries"],        "snapshot_keys": []},
    "vector_store": {"tools": ["tool_search_similar_games"],"snapshot_keys": []},
    "h2h":          {"tools": ["tool_get_head_to_head"],    "snapshot_keys": ["head_to_head"]},
    "stats":        {"tools": ["tool_get_team_stats"],
                     "snapshot_keys": ["home_team_stats", "away_team_stats"]},
}


def _disabled_tool_factory(source_name):
    """Return a tool replacement that emits a stable DISABLED marker."""
    msg = f"DISABLED for ablation: {source_name}"

    def _disabled(*args, **kwargs):
        return msg

    _disabled.__name__ = f"disabled_{source_name}"
    return _disabled


@contextlib.contextmanager
def ablate_source(source_name):
    """
    Disable one data source for the duration of the `with` block.

    Monkeypatches the relevant tool functions on the nba_agent module so the
    multi-agent / single-agent / cot runners that import those tools see the
    DISABLED marker instead of real data. Restores the originals on exit even
    if the body raises.

    Pass source_name=None or "" to no-op (clean baseline run).
    """
    if not source_name:
        yield
        return

    if source_name not in ABLATION_SOURCES:
        raise ValueError(
            f"Unknown ablation source: {source_name!r}. "
            f"Choose one of: {sorted(ABLATION_SOURCES)}"
        )

    import nba_agent
    spec = ABLATION_SOURCES[source_name]
    originals = {}
    try:
        for tool_attr in spec["tools"]:
            if hasattr(nba_agent, tool_attr):
                originals[tool_attr] = getattr(nba_agent, tool_attr)
                setattr(nba_agent, tool_attr, _disabled_tool_factory(source_name))
            # Also patch the entry inside the TOOLS registry so call_tool
            # dispatches to the disabled stub.
        if hasattr(nba_agent, "TOOLS"):
            for short_name, info in nba_agent.TOOLS.items():
                fn_attr = "tool_" + short_name
                if fn_attr in originals:
                    info["function"] = getattr(nba_agent, fn_attr)
        yield
    finally:
        for tool_attr, fn in originals.items():
            setattr(nba_agent, tool_attr, fn)
        if hasattr(nba_agent, "TOOLS"):
            for short_name, info in nba_agent.TOOLS.items():
                fn_attr = "tool_" + short_name
                if fn_attr in originals:
                    info["function"] = originals[fn_attr]


# ============================================================
# AS_OF_DATE TOOL FREEZE
# ============================================================
# The data tools in nba_agent take an optional as_of_date kwarg (added in
# Wave 2). This context manager wraps every tool function so that during a
# backtest run, every call automatically receives as_of_date=<game date> —
# the agent never even sees the parameter. This is the leakage fix: without
# it, an agent backtesting a 2024-12-25 game would happily read 2025 stats.

# Tool functions (module-level) we transparently wrap.
_FREEZABLE_TOOL_ATTRS = (
    "tool_get_team_stats",
    "tool_get_head_to_head",
    "tool_get_injuries",
    "tool_get_odds",
    "tool_get_team_sentiment",
    "tool_search_similar_games",
)


def _make_as_of_date_wrapper(original_fn, as_of_date):
    @functools.wraps(original_fn)
    def wrapped(*args, **kwargs):
        kwargs.setdefault("as_of_date", as_of_date)
        return original_fn(*args, **kwargs)
    return wrapped


@contextlib.contextmanager
def freeze_tool_as_of_date(as_of_date):
    """
    Force every nba_agent data tool to receive as_of_date=<as_of_date>.

    Patches three locations because the dependent modules captured tool
    references at import time:
      * nba_agent module attrs (used by run_agent + nba_agent.TOOLS)
      * nba_agent.TOOLS registry entries
      * nba_multi_agent.AGENTS[*]["tools"] dicts (frozen at import)
      * nba_cot_baseline module-level imports (looked up at call time)

    Originals are always restored, even if the body raises. as_of_date=None
    is a no-op so the Streamlit code path is untouched.
    """
    if as_of_date is None:
        yield
        return

    import nba_agent
    import nba_multi_agent
    import nba_cot_baseline

    originals = {}

    try:
        # Patch nba_agent module-level functions.
        for attr in _FREEZABLE_TOOL_ATTRS:
            if not hasattr(nba_agent, attr):
                continue
            orig = getattr(nba_agent, attr)
            originals[attr] = orig
            setattr(nba_agent, attr, _make_as_of_date_wrapper(orig, as_of_date))

        # Refresh nba_agent.TOOLS registry to point at the wrappers.
        if hasattr(nba_agent, "TOOLS"):
            for short_name, info in nba_agent.TOOLS.items():
                fn_attr = "tool_" + short_name
                if fn_attr in originals:
                    info["function"] = getattr(nba_agent, fn_attr)

        # Refresh nba_multi_agent.AGENTS tool dicts (captured at import time).
        for agent_def in nba_multi_agent.AGENTS.values():
            for short_name in list(agent_def["tools"]):
                fn_attr = "tool_" + short_name
                if fn_attr in originals:
                    agent_def["tools"][short_name] = getattr(nba_agent, fn_attr)

        # Refresh nba_cot_baseline's module-bound names. cot's gather function
        # rebuilds its tool dict on every call by looking these up.
        for attr in _FREEZABLE_TOOL_ATTRS:
            if attr in originals and hasattr(nba_cot_baseline, attr):
                setattr(nba_cot_baseline, attr, getattr(nba_agent, attr))

        yield

    finally:
        # Restore everything in reverse order.
        for attr in _FREEZABLE_TOOL_ATTRS:
            if attr in originals and hasattr(nba_cot_baseline, attr):
                setattr(nba_cot_baseline, attr, originals[attr])

        for agent_def in nba_multi_agent.AGENTS.values():
            for short_name in list(agent_def["tools"]):
                fn_attr = "tool_" + short_name
                if fn_attr in originals:
                    agent_def["tools"][short_name] = originals[fn_attr]

        if hasattr(nba_agent, "TOOLS"):
            for short_name, info in nba_agent.TOOLS.items():
                fn_attr = "tool_" + short_name
                if fn_attr in originals:
                    info["function"] = originals[fn_attr]

        for attr, orig in originals.items():
            setattr(nba_agent, attr, orig)


def scrub_snapshot_for_ablation(snapshot, source_name):
    """
    Return a copy of `snapshot` with the keys belonging to the ablated source
    replaced by the DISABLED marker. The static-prompt backtest builds
    snapshots without going through the tool layer, so the monkeypatch alone
    would not change its outputs; this hook makes ablation visible there too.
    """
    if not source_name:
        return snapshot
    spec = ABLATION_SOURCES.get(source_name)
    if not spec:
        return snapshot

    scrubbed = json.loads(json.dumps(snapshot, default=str))
    marker = f"DISABLED for ablation: {source_name}"
    for key in spec["snapshot_keys"]:
        if key in scrubbed:
            scrubbed[key] = marker
    return scrubbed

DEFAULT_N_GAMES = 30
DEFAULT_MIN_GAMES_HISTORY = 10
DEFAULT_RANDOM_SEED = 42
DEFAULT_SEASON_FILTER = "2025-26"
SLEEP_BETWEEN_CALLS = 0.35

random.seed(DEFAULT_RANDOM_SEED)
np.random.seed(DEFAULT_RANDOM_SEED)


# ============================================================
# LLM BACKENDS
# ============================================================

def call_anthropic(messages):
    import anthropic
    from nba_cost_logger import log_anthropic_response
    client = anthropic.Anthropic()

    system_msg = ""
    conv_messages = []
    for msg in messages:
        if msg["role"] == "system":
            system_msg = msg["content"]
        else:
            conv_messages.append(msg)

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2500,
        system=system_msg if system_msg else "You are an NBA betting analyst.",
        messages=conv_messages,
    )
    log_anthropic_response("nba_backtest.py", response)
    return response.content[0].text


def call_openai(messages):
    from openai import OpenAI
    from nba_cost_logger import log_openai_response
    client = OpenAI()

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        max_tokens=2500,
    )
    log_openai_response("nba_backtest.py", response)
    return response.choices[0].message.content


def get_llm_fn():
    if os.environ.get("ANTHROPIC_API_KEY"):
        return call_anthropic, "Claude"
    if os.environ.get("OPENAI_API_KEY"):
        return call_openai, "GPT-4o"
    raise RuntimeError("No API key found. Set ANTHROPIC_API_KEY or OPENAI_API_KEY.")


# ============================================================
# DATA LOADING
# ============================================================

def load_game_logs():
    df = pd.read_csv(f"{DATA_DIR}/game_logs.csv")
    df["GAME_DATE"] = pd.to_datetime(df["GAME_DATE"], errors="coerce")
    df = df.dropna(subset=["GAME_DATE"]).copy()
    return df


def load_historical_odds():
    path = f"{DATA_DIR}/odds_historical.csv"
    if os.path.exists(path):
        df = pd.read_csv(path)
        return df
    return pd.DataFrame()


def build_unique_games(game_logs):
    rows = []

    for game_id, g in game_logs.groupby("GAME_ID"):
        if len(g) < 2:
            continue

        home_rows = g[g["HOME"] == 1]
        away_rows = g[g["HOME"] == 0]

        if home_rows.empty or away_rows.empty:
            continue

        home = home_rows.iloc[0]
        away = away_rows.iloc[0]

        rows.append({
            "GAME_ID": game_id,
            "GAME_DATE": home["GAME_DATE"],
            "SEASON": home["SEASON"],
            "HOME_TEAM": home["TEAM_ABBREVIATION"],
            "AWAY_TEAM": away["TEAM_ABBREVIATION"],
            "HOME_WIN": int(home["WIN"]),
            "HOME_POINTS": int(home["PTS"]),
            "AWAY_POINTS": int(away["PTS"]),
        })

    return pd.DataFrame(rows).sort_values("GAME_DATE").reset_index(drop=True)


# ============================================================
# HISTORICAL SNAPSHOT BUILDING
# ============================================================

def get_team_history(game_logs, team_abbr, before_date, season=None):
    df = game_logs[
        (game_logs["TEAM_ABBREVIATION"] == team_abbr) &
        (game_logs["GAME_DATE"] < before_date)
    ].copy()

    if season is not None:
        df = df[df["SEASON"] == season].copy()

    return df.sort_values("GAME_DATE", ascending=False).reset_index(drop=True)


def summarize_team_form(team_games, n_recent=10):
    if team_games.empty:
        return None

    recent = team_games.head(n_recent)
    season = str(team_games.iloc[0]["SEASON"])

    wins_total = int((team_games["WIN"] == 1).sum())
    losses_total = int((team_games["WIN"] == 0).sum())
    wins_recent = int((recent["WIN"] == 1).sum())
    losses_recent = int((recent["WIN"] == 0).sum())

    return {
        "season": season,
        "season_record": f"{wins_total}-{losses_total}",
        "last_10_record": f"{wins_recent}-{losses_recent}",
        "avg_points_last_10": round(float(recent["PTS"].mean()), 1),
        "avg_fg_pct_last_10": round(float(recent["FG_PCT"].mean()), 3),
        "avg_fg3_pct_last_10": round(float(recent["FG3_PCT"].mean()), 3),
        "avg_rebounds_last_10": round(float(recent["REB"].mean()), 1),
        "avg_assists_last_10": round(float(recent["AST"].mean()), 1),
        "avg_turnovers_last_10": round(float(recent["TOV"].mean()), 1),
        "avg_plus_minus_last_10": round(float(recent["PLUS_MINUS"].mean()), 1),
        "last_game_date": str(recent.iloc[0]["GAME_DATE"].date()),
        "last_game_matchup": str(recent.iloc[0]["MATCHUP"]),
        "last_game_result": "W" if int(recent.iloc[0]["WIN"]) == 1 else "L",
        "games_available": int(len(team_games)),
    }


def summarize_head_to_head(game_logs, home_team, away_team, before_date, season=None):
    df = game_logs[
        (game_logs["GAME_DATE"] < before_date) &
        (game_logs["TEAM_ABBREVIATION"] == home_team) &
        (game_logs["MATCHUP"].str.contains(away_team, na=False))
    ].copy()

    if season is not None:
        df = df[df["SEASON"] == season].copy()

    if df.empty:
        return {
            "games": 0,
            "home_team_wins": 0,
            "home_team_losses": 0,
            "home_team_win_pct": None,
            "avg_home_points": None,
            "avg_plus_minus": None,
        }

    wins = int((df["WIN"] == 1).sum())
    losses = int((df["WIN"] == 0).sum())

    return {
        "games": int(len(df)),
        "home_team_wins": wins,
        "home_team_losses": losses,
        "home_team_win_pct": round(wins / len(df), 3),
        "avg_home_points": round(float(df["PTS"].mean()), 1),
        "avg_plus_minus": round(float(df["PLUS_MINUS"].mean()), 1),
    }


def build_historical_snapshot(game_logs, game_row, min_games_history):
    game_date = pd.Timestamp(game_row["GAME_DATE"])
    season = str(game_row["SEASON"])
    home_team = str(game_row["HOME_TEAM"])
    away_team = str(game_row["AWAY_TEAM"])

    home_hist = get_team_history(game_logs, home_team, game_date, season=season)
    away_hist = get_team_history(game_logs, away_team, game_date, season=season)

    if len(home_hist) < min_games_history or len(away_hist) < min_games_history:
        return None

    return {
        "game": {
            "game_id": str(game_row["GAME_ID"]),
            "date": str(game_date.date()),
            "season": season,
            "home_team": home_team,
            "away_team": away_team,
        },
        "home_team_stats": summarize_team_form(home_hist),
        "away_team_stats": summarize_team_form(away_hist),
        "head_to_head": summarize_head_to_head(game_logs, home_team, away_team, game_date, season=season),
    }


# ============================================================
# AGENT REPORT PARSING + TEAM NAME LOOKUP
# ============================================================

@functools.lru_cache(maxsize=1)
def _team_name_lookup():
    """abbreviation -> full team name (e.g. 'LAL' -> 'Los Angeles Lakers')."""
    path = f"{DATA_DIR}/teams.csv"
    if not os.path.exists(path):
        return {}
    df = pd.read_csv(path)
    if "abbreviation" not in df.columns or "full_name" not in df.columns:
        return {}
    return {str(r["abbreviation"]): str(r["full_name"]) for _, r in df.iterrows()}


def abbr_to_full_name(abbr):
    """Look up a full team name from abbreviation, with safe fallback."""
    return _team_name_lookup().get(str(abbr), str(abbr))


def _extract_report_json(report_text):
    """
    Extract the JSON block from a free-form LLM response. Handles both
    'FINAL REPORT: { ... }' and bare '{ ... }' shapes.
    """
    if report_text is None:
        return None
    text = str(report_text)
    if "FINAL REPORT:" in text:
        text = text.split("FINAL REPORT:")[-1]
    text = text.strip()
    start = text.find("{")
    end = text.rfind("}") + 1
    if start < 0 or end <= start:
        return None
    candidate = text[start:end]
    try:
        return json.loads(candidate)
    except (json.JSONDecodeError, ValueError):
        return None


def _normalize_agent_report(report_json, method_name):
    """
    Normalize the various agent report shapes into the canonical fields the
    backtest writes to CSV: home_win_prob, away_win_prob, confidence,
    key_factors, reasoning.

    Shapes we accept:
      * single agent (nba_agent.run_agent):
          {"agent_prediction": {"home_win_prob","away_win_prob","confidence"},
           "key_factors": [...], "reasoning": "..."}
      * CoT (nba_cot_baseline.run_cot_analysis):
          {"prediction": {"home_win_prob","away_win_prob","confidence"},
           "key_factors": [...], "reasoning": "..."}
      * multi-agent debate (nba_multi_agent.run_full_debate, moderator):
          {"synthesized_prediction": {"home_win_prob","away_win_prob",
           "confidence"}, "key_factors": [...], "reasoning": "..."}
      * defensively: top-level home_win_prob/away_win_prob.

    Raises ValueError if no probability pair can be recovered.
    """
    if not isinstance(report_json, dict):
        raise ValueError(f"{method_name}: report is not a JSON object")

    pred = (
        report_json.get("synthesized_prediction")
        or report_json.get("agent_prediction")
        or report_json.get("prediction")
        or {}
    )

    home = pred.get("home_win_prob") if isinstance(pred, dict) else None
    away = pred.get("away_win_prob") if isinstance(pred, dict) else None
    if home is None:
        home = report_json.get("home_win_prob")
    if away is None:
        away = report_json.get("away_win_prob")
    if home is None or away is None:
        raise ValueError(f"{method_name}: could not find home/away win probabilities")

    confidence = ""
    if isinstance(pred, dict):
        confidence = pred.get("confidence", "") or ""
    if not confidence:
        confidence = report_json.get("confidence", "") or ""

    return {
        "method": method_name,
        "home_win_prob": float(home),
        "away_win_prob": float(away),
        "confidence": confidence,
        "key_factors": report_json.get("key_factors", []),
        "reasoning": report_json.get("reasoning", ""),
    }


# ============================================================
# CACHE + RETRY
# ============================================================

def get_cache_path(snapshot, method_name, ablation=None):
    game = snapshot["game"]
    suffix = f"_ablate_{ablation}" if ablation else ""
    filename = f"{game['season']}_{game['date']}_{game['away_team']}_at_{game['home_team']}_{method_name}{suffix}.json"
    filename = filename.replace(" ", "_").replace("/", "-")
    return os.path.join(CACHE_DIR, filename)


def load_cached_result(snapshot, method_name, ablation=None):
    path = get_cache_path(snapshot, method_name, ablation=ablation)
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return None


def save_cached_result(snapshot, method_name, parsed, raw, info_density=None, ablation=None):
    path = get_cache_path(snapshot, method_name, ablation=ablation)
    payload = {
        "parsed": parsed,
        "raw": raw,
    }
    if info_density is not None:
        payload["info_density"] = info_density
    if ablation:
        payload["ablation"] = ablation
    with open(path, "w") as f:
        json.dump(payload, f, indent=2)


def run_with_retry(fn, max_retries=4, base_sleep=2.0):
    for attempt in range(max_retries + 1):
        try:
            return fn()
        except Exception as e:
            msg = str(e).lower()
            retryable = (
                "429" in msg
                or "rate limit" in msg
                or "overloaded" in msg
                or "timeout" in msg
                or "temporarily unavailable" in msg
            )

            if attempt == max_retries or not retryable:
                raise

            sleep_time = base_sleep * (2 ** attempt)
            print(f"    retrying after error: {e}")
            print(f"    sleeping {sleep_time:.1f}s before retry...")
            time.sleep(sleep_time)


# ============================================================
# RUNNERS
# ============================================================

def _empty_backtest_info_density():
    """
    Info-density counters for one backtest game. Real values come back from
    the agent runners (each populates an info_density dict with
    youtube_comments / news_articles / vector_hits / context_tokens).
    """
    return {
        "youtube_comments": 0,
        "news_articles": 0,
        "vector_hits": 0,
        "context_tokens": 0,
    }


def _build_game_description(snapshot):
    """
    Build the human-readable game string the live agents expect, matching
    the format Streamlit uses: '<away full name> vs <home full name>, <Mon DD, YYYY>'.
    """
    game = snapshot["game"]
    home_name = abbr_to_full_name(game["home_team"])
    away_name = abbr_to_full_name(game["away_team"])
    game_date = pd.to_datetime(game["date"], errors="coerce")
    if pd.notna(game_date):
        date_str = game_date.strftime("%B %d, %Y")
    else:
        date_str = str(game["date"])
    return f"{away_name} vs {home_name}, {date_str}", home_name, away_name


# Retry cap for cheaper Haiku-class models that occasionally produce a
# response without a parseable JSON block. Each retry is a fresh agent
# call (more API spend) so keep small.
PARSE_RETRY_MAX_ATTEMPTS = 3


def _run_method_with_parse_retry(method_name, runner_body):
    """
    Wrap an agent runner so a missing/malformed JSON report triggers a
    fresh agent call instead of failing the whole game. Retries only on
    parse failures from _normalize_agent_report; other errors propagate
    immediately.
    """
    last_err = None
    for attempt in range(1, PARSE_RETRY_MAX_ATTEMPTS + 1):
        try:
            return runner_body()
        except ValueError as e:
            msg = str(e)
            is_parse_failure = (
                "report is not a JSON object" in msg
                or "no probability pair" in msg
                or "missing key_factors" in msg
                or "could not find home/away win probabilities" in msg
                or "could not find" in msg
            )
            if not is_parse_failure:
                raise
            last_err = e
            if attempt < PARSE_RETRY_MAX_ATTEMPTS:
                print(
                    f"    {method_name}: parse failed "
                    f"(attempt {attempt}/{PARSE_RETRY_MAX_ATTEMPTS}), "
                    f"retrying with a fresh agent run..."
                )
    raise last_err


def run_single_agent_backtest(snapshot, llm_fn):
    """Invoke nba_agent.run_agent under an as_of_date freeze."""
    game_description, _home_name, _away_name = _build_game_description(snapshot)
    as_of_date = snapshot["game"]["date"]

    def _body():
        with freeze_tool_as_of_date(as_of_date):
            result = run_agent(game_description, llm_fn)
        raw = result.get("final_response", "")
        info_density = result.get("info_density") or _empty_backtest_info_density()
        report_json = _extract_report_json(raw)
        parsed = _normalize_agent_report(report_json, method_name="single_agent")
        return parsed, raw, info_density

    return _run_method_with_parse_retry("single_agent", _body)


def run_cot_backtest(snapshot, llm_fn):
    """Invoke nba_cot_baseline.run_cot_analysis under an as_of_date freeze."""
    game_description, home_name, away_name = _build_game_description(snapshot)
    as_of_date = snapshot["game"]["date"]
    home_abbr = snapshot["game"]["home_team"]
    away_abbr = snapshot["game"]["away_team"]

    def _body():
        with freeze_tool_as_of_date(as_of_date):
            result = run_cot_analysis(
                home_abbr=home_abbr,
                away_abbr=away_abbr,
                home_name=home_name,
                away_name=away_name,
                game_description=game_description,
                llm_call_fn=llm_fn,
            )
        raw = result.get("response", "")
        info_density = result.get("info_density") or _empty_backtest_info_density()
        report_json = _extract_report_json(raw)
        parsed = _normalize_agent_report(report_json, method_name="chain_of_thought")
        return parsed, raw, info_density

    return _run_method_with_parse_retry("chain_of_thought", _body)


def run_multi_agent_backtest(snapshot, llm_fn):
    """Invoke nba_multi_agent.run_full_debate under an as_of_date freeze."""
    game_description, _home_name, _away_name = _build_game_description(snapshot)
    as_of_date = snapshot["game"]["date"]

    def _body():
        with freeze_tool_as_of_date(as_of_date):
            result = run_full_debate(game_description, llm_fn)
        raw = result.get("final_report", "")
        info_density = result.get("info_density") or _empty_backtest_info_density()
        report_json = _extract_report_json(raw)
        parsed = _normalize_agent_report(report_json, method_name="multi_agent_debate")
        return parsed, raw, info_density

    return _run_method_with_parse_retry("multi_agent_debate", _body)


# ============================================================
# METRICS
# ============================================================

def safe_clip_prob(p):
    return min(max(float(p), 1e-6), 1 - 1e-6)


def compute_log_loss(y_true, p_home):
    p = safe_clip_prob(p_home)
    return -(y_true * math.log(p) + (1 - y_true) * math.log(1 - p))


def compute_brier(y_true, p_home):
    return (p_home - y_true) ** 2


def compute_precision(tp, fp):
    return tp / (tp + fp) if (tp + fp) > 0 else 0.0


def compute_recall(tp, fn):
    return tp / (tp + fn) if (tp + fn) > 0 else 0.0


def compute_f1(precision, recall):
    return 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0


def expected_calibration_error(g, n_bins=10):
    bins = np.linspace(0, 1, n_bins + 1)
    ece = 0.0
    total = len(g)

    if total == 0:
        return 0.0

    temp = g.copy()
    temp["bin"] = pd.cut(temp["home_win_prob"], bins=bins, include_lowest=True)

    for _, gb in temp.groupby("bin", observed=False):
        if gb.empty:
            continue
        avg_pred = gb["home_win_prob"].mean()
        avg_actual = gb["actual_home_win"].mean()
        ece += (len(gb) / total) * abs(avg_pred - avg_actual)

    return float(ece)


def summarize_metrics(pred_df):
    rows = []

    for method, g in pred_df.groupby("method"):
        tp = int(((g["pred_home_win"] == 1) & (g["actual_home_win"] == 1)).sum())
        fp = int(((g["pred_home_win"] == 1) & (g["actual_home_win"] == 0)).sum())
        tn = int(((g["pred_home_win"] == 0) & (g["actual_home_win"] == 0)).sum())
        fn = int(((g["pred_home_win"] == 0) & (g["actual_home_win"] == 1)).sum())

        precision = compute_precision(tp, fp)
        recall = compute_recall(tp, fn)
        f1 = compute_f1(precision, recall)

        rows.append({
            "method": method,
            "n_games": int(len(g)),
            "accuracy": round(float((g["pred_home_win"] == g["actual_home_win"]).mean()), 4),
            "precision": round(float(precision), 4),
            "recall": round(float(recall), 4),
            "f1": round(float(f1), 4),
            "log_loss": round(float(g["log_loss"].mean()), 4),
            "brier_score": round(float(g["brier_score"].mean()), 4),
            "mae_prob": round(float((g["home_win_prob"] - g["actual_home_win"]).abs().mean()), 4),
            "avg_home_win_prob": round(float(g["home_win_prob"].mean()), 4),
            "avg_confidence": round(float(np.maximum(g["home_win_prob"], g["away_win_prob"]).mean()), 4),
            "avg_gap": round(float((g["home_win_prob"] - g["away_win_prob"]).abs().mean()), 4),
            "ece": round(expected_calibration_error(g, n_bins=5), 4),
            "tp": tp,
            "fp": fp,
            "tn": tn,
            "fn": fn,
        })

    return pd.DataFrame(rows)


def build_calibration_table(pred_df, n_bins=5):
    rows = []

    for method, g in pred_df.groupby("method"):
        temp = g.copy()
        temp["bin"] = pd.cut(temp["home_win_prob"], bins=np.linspace(0, 1, n_bins + 1), include_lowest=True)

        for b, gb in temp.groupby("bin", observed=False):
            if gb.empty:
                continue

            rows.append({
                "method": method,
                "bin": str(b),
                "n_games": int(len(gb)),
                "avg_pred_home_win_prob": round(float(gb["home_win_prob"].mean()), 4),
                "actual_home_win_rate": round(float(gb["actual_home_win"].mean()), 4),
                "abs_gap": round(abs(float(gb["home_win_prob"].mean()) - float(gb["actual_home_win"].mean())), 4),
            })

    return pd.DataFrame(rows)


# ============================================================
# GAME SELECTION
# ============================================================

def select_backtest_games(unique_games, n_games, season_filter):
    games = unique_games.copy()

    if season_filter:
        games = games[games["SEASON"] == season_filter].copy()

    games = games.sort_values("GAME_DATE").reset_index(drop=True)

    if len(games) > n_games:
        idx = np.linspace(0, len(games) - 1, n_games, dtype=int)
        games = games.iloc[idx].copy()

    return games.reset_index(drop=True)


# ============================================================
# HISTORICAL MARKET MATCHING
# ============================================================

def american_to_implied_prob(odds):
    if pd.isna(odds):
        return None
    odds = float(odds)
    if odds > 0:
        return 100.0 / (odds + 100.0)
    return abs(odds) / (abs(odds) + 100.0)


def normalize_team_name(name):
    mapping = {
        "ATL": "Atlanta",
        "BOS": "Boston",
        "BKN": "Brooklyn",
        "CHA": "Charlotte",
        "CHI": "Chicago",
        "CLE": "Cleveland",
        "DAL": "Dallas",
        "DEN": "Denver",
        "DET": "Detroit",
        "GSW": "Golden State",
        "HOU": "Houston",
        "IND": "Indiana",
        "LAC": "L.A. Clippers",
        "LAL": "L.A. Lakers",
        "MEM": "Memphis",
        "MIA": "Miami",
        "MIL": "Milwaukee",
        "MIN": "Minnesota",
        "NOP": "New Orleans",
        "NYK": "New York",
        "OKC": "Oklahoma City",
        "ORL": "Orlando",
        "PHI": "Philadelphia",
        "PHX": "Phoenix",
        "POR": "Portland",
        "SAC": "Sacramento",
        "SAS": "San Antonio",
        "TOR": "Toronto",
        "UTA": "Utah",
        "WAS": "Washington",
    }
    return mapping.get(str(name), str(name))


def match_market_prob(odds_df, game_date, home_team, away_team):
    if odds_df.empty:
        return None

    df = odds_df.copy()
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce").dt.date
    target_date = pd.to_datetime(game_date).date()

    home_team_name = normalize_team_name(home_team)
    away_team_name = normalize_team_name(away_team)

    home_rows = df[
        (df["Date"] == target_date) &
        (df["Location"].astype(str).str.lower() == "home") &
        (df["Team"].astype(str) == home_team_name) &
        (df["OppTeam"].astype(str) == away_team_name)
    ].copy()

    away_rows = df[
        (df["Date"] == target_date) &
        (df["Location"].astype(str).str.lower() == "away") &
        (df["Team"].astype(str) == away_team_name) &
        (df["OppTeam"].astype(str) == home_team_name)
    ].copy()

    if home_rows.empty or away_rows.empty:
        return None

    home_row = home_rows.iloc[0]
    away_row = away_rows.iloc[0]

    home_ml = home_row.get("Average_Line_ML")
    away_ml = away_row.get("Average_Line_ML")

    home_prob = american_to_implied_prob(home_ml)
    away_prob = american_to_implied_prob(away_ml)

    if home_prob is None or away_prob is None:
        return None

    total = home_prob + away_prob
    if total <= 0:
        return None

    return {
        "home_implied_prob": home_prob / total,
        "away_implied_prob": away_prob / total,
    }

# ============================================================
# MAIN
# ============================================================

ALL_METHODS = ["single_agent", "chain_of_thought", "multi_agent_debate"]


def run_backtest(n_games=DEFAULT_N_GAMES, season_filter=DEFAULT_SEASON_FILTER,
                 min_games_history=DEFAULT_MIN_GAMES_HISTORY, disable_source=None,
                 methods=None):
    """
    Run the historical backtest.

    Args:
        n_games: number of games to sample from the season filter.
        season_filter: e.g. "2025-26" or None for all.
        min_games_history: skip games where either team has fewer than this many
            prior games in the same season.
        disable_source: if set, run with that source ablated. The corresponding
            tools in nba_agent emit "DISABLED for ablation: <name>" and the
            relevant snapshot keys are scrubbed. Output goes to
            data/backtest_ablation_<name>.csv (and a matching summary file)
            instead of the default backtest_predictions.csv.
        methods: list of method names to run (default: all three). Pass
            ["chain_of_thought"] to run CoT-only ablations at ~1/10th the cost.
    """
    if methods is None:
        methods = ALL_METHODS
    llm_fn, llm_name = get_llm_fn()

    print("=" * 60)
    print("NBA Historical Backtest" + (f" [ABLATE {disable_source}]" if disable_source else ""))
    print("=" * 60)
    print(f"Using model backend: {llm_name}")

    game_logs = load_game_logs()
    odds_hist = load_historical_odds()
    unique_games = build_unique_games(game_logs)
    test_games = select_backtest_games(unique_games, n_games=n_games, season_filter=season_filter)

    print(f"Candidate games selected: {len(test_games)}")

    rows = []
    skipped = 0
    failed_method_calls = 0

    with ablate_source(disable_source):
        for i, (_, game_row) in enumerate(test_games.iterrows(), start=1):
            raw_snapshot = build_historical_snapshot(game_logs, game_row, min_games_history=min_games_history)
            if raw_snapshot is None:
                skipped += 1
                continue

            snapshot = scrub_snapshot_for_ablation(raw_snapshot, disable_source)

            game_label = f"{snapshot['game']['away_team']} @ {snapshot['game']['home_team']} on {snapshot['game']['date']}"
            actual_home_win = int(game_row["HOME_WIN"])

            # Market odds are the answer key; do NOT ablate them away from the
            # CSV (we still need to compare predictions against the line).
            market_match = match_market_prob(
                odds_hist,
                snapshot["game"]["date"],
                snapshot["game"]["home_team"],
                snapshot["game"]["away_team"],
            )

            market_home_implied_prob = None
            market_away_implied_prob = None
            if market_match:
                market_home_implied_prob = market_match["home_implied_prob"]
                market_away_implied_prob = market_match["away_implied_prob"]

            print()
            print(f"[{i}/{len(test_games)}] {game_label}")

            all_model_runs = [
                ("single_agent", run_single_agent_backtest),
                ("chain_of_thought", run_cot_backtest),
                ("multi_agent_debate", run_multi_agent_backtest),
            ]
            model_runs = [(n, r) for n, r in all_model_runs if n in methods]

            for method_name, runner in model_runs:
                try:
                    cached = load_cached_result(snapshot, method_name, ablation=disable_source)
                    if cached is not None:
                        parsed = cached["parsed"]
                        raw = cached["raw"]
                        info_density = cached.get("info_density") or _empty_backtest_info_density()
                        print(f"  {method_name}: loaded from cache")
                    else:
                        parsed, raw, info_density = run_with_retry(lambda: runner(snapshot, llm_fn))
                        save_cached_result(
                            snapshot, method_name, parsed, raw,
                            info_density=info_density, ablation=disable_source,
                        )

                    home_prob = safe_clip_prob(parsed["home_win_prob"])
                    away_prob = safe_clip_prob(parsed["away_win_prob"])

                    if abs((home_prob + away_prob) - 1.0) > 0.05:
                        total = home_prob + away_prob
                        home_prob = home_prob / total
                        away_prob = away_prob / total

                    pred_home_win = int(home_prob >= away_prob)

                    rows.append({
                        "game_id": game_row["GAME_ID"],
                        "date": snapshot["game"]["date"],
                        "season": snapshot["game"]["season"],
                        "home_team": snapshot["game"]["home_team"],
                        "away_team": snapshot["game"]["away_team"],
                        "method": method_name,
                        "ablation": disable_source or "",
                        "home_win_prob": round(home_prob, 6),
                        "away_win_prob": round(away_prob, 6),
                        "pred_home_win": pred_home_win,
                        "actual_home_win": actual_home_win,
                        "correct": int(pred_home_win == actual_home_win),
                        "log_loss": round(compute_log_loss(actual_home_win, home_prob), 6),
                        "brier_score": round(compute_brier(actual_home_win, home_prob), 6),
                        "confidence": parsed.get("confidence", ""),
                        "key_factors": json.dumps(parsed.get("key_factors", [])),
                        "reasoning": parsed.get("reasoning", ""),
                        "market_home_implied_prob": market_home_implied_prob,
                        "market_away_implied_prob": market_away_implied_prob,
                        "info_density_youtube_comments": int(info_density.get("youtube_comments", 0) or 0),
                        "info_density_news_articles": int(info_density.get("news_articles", 0) or 0),
                        "info_density_vector_hits": int(info_density.get("vector_hits", 0) or 0),
                        "info_density_context_tokens": int(info_density.get("context_tokens", 0) or 0),
                        "raw_response": raw,
                    })

                    print(f"  {method_name}: home={home_prob:.3f}, away={away_prob:.3f}, correct={pred_home_win == actual_home_win}")
                    time.sleep(SLEEP_BETWEEN_CALLS)

                except Exception as e:
                    failed_method_calls += 1
                    print(f"  {method_name}: FAILED -> {e}")

    if not rows:
        raise RuntimeError("No predictions were produced.")

    pred_df = pd.DataFrame(rows)
    summary_df = summarize_metrics(pred_df)
    calibration_df = build_calibration_table(pred_df, n_bins=5)

    if disable_source:
        predictions_out = f"{DATA_DIR}/backtest_ablation_{disable_source}.csv"
        summary_out = f"{DATA_DIR}/backtest_ablation_{disable_source}_summary.csv"
        calibration_out = f"{DATA_DIR}/backtest_ablation_{disable_source}_calibration.csv"
        run_meta_out = f"{DATA_DIR}/backtest_ablation_{disable_source}_metadata.json"
    else:
        predictions_out = PREDICTIONS_OUT
        summary_out = SUMMARY_OUT
        calibration_out = CALIBRATION_OUT
        run_meta_out = RUN_META_OUT

    pred_df.to_csv(predictions_out, index=False)
    summary_df.to_csv(summary_out, index=False)
    calibration_df.to_csv(calibration_out, index=False)

    run_meta = {
        "n_games_requested": int(n_games),
        "season_filter": season_filter,
        "min_games_history": int(min_games_history),
        "ablation": disable_source or "",
        "candidate_games_selected": int(len(test_games)),
        "games_skipped": int(skipped),
        "failed_method_calls": int(failed_method_calls),
        "prediction_rows": int(len(pred_df)),
        "unique_games_completed": int(pred_df["game_id"].nunique()),
        "methods_present": sorted(pred_df["method"].dropna().unique().tolist()),
    }

    with open(run_meta_out, "w") as f:
        json.dump(run_meta, f, indent=2)

    print()
    print("=" * 60)
    print("BACKTEST SUMMARY" + (f" [ABLATE {disable_source}]" if disable_source else ""))
    print("=" * 60)
    print(summary_df.to_string(index=False))
    print()
    print(f"Skipped games: {skipped}")
    print(f"Failed method calls: {failed_method_calls}")
    print(f"Saved predictions to: {predictions_out}")
    print(f"Saved summary to: {summary_out}")
    print(f"Saved calibration to: {calibration_out}")
    print(f"Saved run metadata to: {run_meta_out}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--n-games", type=int, default=DEFAULT_N_GAMES)
    parser.add_argument("--season", type=str, default=DEFAULT_SEASON_FILTER)
    parser.add_argument("--min-games-history", type=int, default=DEFAULT_MIN_GAMES_HISTORY)
    parser.add_argument(
        "--disable-source", type=str, default=None,
        choices=sorted(ABLATION_SOURCES.keys()),
        help="Disable one data source for the run; output goes to data/backtest_ablation_<name>.csv.",
    )
    parser.add_argument(
        "--ablate-all", action="store_true",
        help="Run a baseline + one backtest per source sequentially. Mutually exclusive with --disable-source.",
    )
    parser.add_argument(
        "--methods", type=str, default=None,
        help=(
            "Comma-separated list of methods to run: single_agent, chain_of_thought, "
            "multi_agent_debate. Default: all three. Use --methods chain_of_thought for "
            "cheap CoT-only ablations (~1/10th the cost of a full run)."
        ),
    )
    args = parser.parse_args()

    if args.ablate_all and args.disable_source:
        parser.error("--ablate-all and --disable-source are mutually exclusive.")

    methods = None
    if args.methods:
        methods = [m.strip() for m in args.methods.split(",")]
        invalid = [m for m in methods if m not in ALL_METHODS]
        if invalid:
            parser.error(f"Unknown method(s): {invalid}. Choose from {ALL_METHODS}.")

    if args.ablate_all:
        sources = sorted(ABLATION_SOURCES.keys())
        print(f"=== ABLATE-ALL: running {len(sources)} ablation backtests ===")
        for source in sources:
            print(f"\n\n##### Ablation: {source} #####")
            run_backtest(
                n_games=args.n_games,
                season_filter=args.season,
                min_games_history=args.min_games_history,
                disable_source=source,
                methods=methods,
            )
        return

    run_backtest(
        n_games=args.n_games,
        season_filter=args.season,
        min_games_history=args.min_games_history,
        disable_source=args.disable_source,
        methods=methods,
    )


if __name__ == "__main__":
    main()