"""
Step 9: Chain-of-Thought Baseline
A single agent that receives ALL gathered evidence at once and reasons
through it in one pass. No tool calling, no iterative gathering.

This is the baseline to compare against the multi-agent debate (Step 8).
The question: does structured multi-agent disagreement outperform a
single generalist thinking carefully with the same data?

Usage:
    export ANTHROPIC_API_KEY="your_key"   (or OPENAI_API_KEY)
    python nba_cot_baseline.py

Requires: steps 1-3 and 5 completed (data/ populated)
"""

import os
import json
from datetime import datetime

from nba_agent import (
    tool_get_team_stats,
    tool_get_head_to_head,
    tool_get_injuries,
    tool_get_odds,
    tool_search_similar_games,
    tool_get_team_sentiment,
    DATA_DIR,
    empty_info_density,
    merge_info_density,
)


# ============================================================
# PRE-GATHER ALL EVIDENCE
# ============================================================

def gather_all_evidence(home_team_abbr, away_team_abbr, home_team_name, away_team_name):
    """
    Gather all available data upfront. No agent decision-making here.
    Just pull everything and hand it to the LLM in one shot.

    Populates `_info_density` with real per-source counters
    (youtube_comments, news_articles, vector_hits) plus the legacy
    aggregate fields kept for backward compatibility.
    """
    print("Gathering all evidence upfront...")
    evidence = {}
    info_density = empty_info_density()

    # (tool_name, args_dict, evidence_key) — declared up front so each call
    # uses the same path for fetching, info-density updates, and storage.
    queries = [
        ("get_team_stats", {"team_abbr": home_team_abbr}, "home_team_stats"),
        ("get_team_stats", {"team_abbr": away_team_abbr}, "away_team_stats"),
        ("get_head_to_head",
         {"team1_abbr": home_team_abbr, "team2_abbr": away_team_abbr},
         "head_to_head"),
        ("get_injuries", {"team_name": home_team_name}, "home_injuries"),
        ("get_injuries", {"team_name": away_team_name}, "away_injuries"),
        ("get_team_sentiment", {"team_abbr": home_team_abbr}, "home_team_sentiment"),
        ("get_team_sentiment", {"team_abbr": away_team_abbr}, "away_team_sentiment"),
        ("get_odds", {"home_team": home_team_name, "away_team": away_team_name}, "odds"),
        ("search_similar_games",
         {"query_text": f"{home_team_abbr} home game recent form",
          "team": home_team_abbr, "n_results": 3},
         "similar_home"),
        ("search_similar_games",
         {"query_text": f"{away_team_abbr} away game recent form",
          "team": away_team_abbr, "n_results": 3},
         "similar_away"),
    ]

    tool_funcs = {
        "get_team_stats": tool_get_team_stats,
        "get_head_to_head": tool_get_head_to_head,
        "get_injuries": tool_get_injuries,
        "get_team_sentiment": tool_get_team_sentiment,
        "get_odds": tool_get_odds,
        "search_similar_games": tool_search_similar_games,
    }

    for tool_name, args, key in queries:
        print(f"  Fetching {key} via {tool_name}...")
        result = tool_funcs[tool_name](**args)
        evidence[key] = result
        merge_info_density(info_density, tool_name, result)

    total_chars = sum(len(str(v)) for v in evidence.values())

    # Real per-source counters replace the previous char-count proxy. The
    # legacy aggregate fields (total_characters, sources_with_data,
    # total_sources_queried) are preserved so the existing CoT prompt and
    # any downstream consumers still see the same shape.
    evidence["_info_density"] = {
        **info_density,
        "total_characters": total_chars,
        "sources_with_data": sum(
            1 for v in evidence.values()
            if v and str(v) != "[]" and "No " not in str(v)[:20]
        ),
        "total_sources_queried": len(queries),
    }

    print(
        f"  Total evidence: {total_chars} characters | "
        f"news_articles={info_density['news_articles']} "
        f"youtube_comments={info_density['youtube_comments']} "
        f"vector_hits={info_density['vector_hits']}"
    )
    return evidence


# ============================================================
# COT PROMPT
# ============================================================

def build_cot_prompt(game_description, evidence):
    """Build a single prompt with all evidence for one-pass reasoning."""

    return f"""You are an NBA betting analyst. You have been given ALL available data about an upcoming game.
Your job is to reason through this evidence step by step and produce a betting report.

GAME: {game_description}

=== HOME TEAM STATS ===
{evidence['home_team_stats']}

=== AWAY TEAM STATS ===
{evidence['away_team_stats']}

=== HEAD-TO-HEAD RECORD ===
{evidence['head_to_head']}

=== HOME TEAM INJURIES ===
{evidence['home_injuries']}

=== AWAY TEAM INJURIES ===
{evidence['away_injuries']}

=== HOME TEAM MEDIA / NEWS SENTIMENT ===
{evidence['home_team_sentiment']}

=== AWAY TEAM MEDIA / NEWS SENTIMENT ===
{evidence['away_team_sentiment']}

=== BETTING ODDS ===
{evidence['odds']}

=== SIMILAR HISTORICAL GAMES (HOME TEAM) ===
{evidence['similar_home']}

=== SIMILAR HISTORICAL GAMES (AWAY TEAM) ===
{evidence['similar_away']}

=== INFORMATION DENSITY ===
{json.dumps(evidence['_info_density'], indent=2)}

INSTRUCTIONS:
Think through this step by step. Consider each piece of evidence, weigh its importance,
and arrive at a prediction. Be explicit about your reasoning chain.

Use media/news sentiment and article coverage as a secondary contextual signal.
Do not let sentiment outweigh hard statistics, injuries, or market information.

If live odds are unavailable, explicitly explain that the selected matchup does not appear in the current upcoming-games odds feed. Say this usually means the selected teams are not actually scheduled to play each other in the current live odds dataset, and tell the user to choose a matchup that exists in the live odds feed to enable value assessment.

Then produce your analysis in this exact JSON format:

FINAL REPORT:
{{
    "game": "TEAM1 vs TEAM2",
    "date": "YYYY-MM-DD",
    "method": "chain_of_thought",
    "prediction": {{
        "home_win_prob": 0.XX,
        "away_win_prob": 0.XX,
        "confidence": "high/medium/low"
    }},
    "market_odds": {{
        "home_implied_prob": 0.XX,
        "away_implied_prob": 0.XX
    }},
    "key_factors": [
        {{"factor": "...", "impact": "favors_home/favors_away/neutral", "importance": "high/medium/low"}}
    ],
    "reasoning": "Your complete step-by-step reasoning chain...",
    "value_assessment": "Where do you see value vs the market? If no live odds are available, explicitly explain that the selected matchup does not appear in the current upcoming-games odds feed and tell the user to choose a matchup that exists in the live odds feed."
}}"""


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
        max_tokens=4096,
        system=system_msg if system_msg else "You are an NBA betting analyst.",
        messages=conv_messages,
    )
    log_anthropic_response("nba_cot_baseline.py", response)
    return response.content[0].text


def call_openai(messages):
    from openai import OpenAI
    from nba_cost_logger import log_openai_response
    client = OpenAI()
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        max_tokens=4096,
    )
    log_openai_response("nba_cot_baseline.py", response)
    return response.choices[0].message.content


# ============================================================
# MAIN
# ============================================================

def run_cot_analysis(home_abbr, away_abbr, home_name, away_name, game_description, llm_call_fn):
    """
    Run the full CoT baseline:
    1. Gather all evidence (no agent decision-making)
    2. Send everything to the LLM in one prompt
    3. Get back a single-pass analysis
    """
    from nba_cost_logger import tally_calls

    evidence = gather_all_evidence(home_abbr, away_abbr, home_name, away_name)
    prompt = build_cot_prompt(game_description, evidence)

    print("\nRunning chain-of-thought analysis (single pass)...")
    messages = [
        {"role": "user", "content": prompt},
    ]

    with tally_calls() as call_records:
        response = llm_call_fn(messages)

    context_tokens = sum(int(r.get("input_tokens", 0) or 0) for r in call_records)
    info_density = dict(evidence["_info_density"])
    info_density["context_tokens"] = context_tokens
    # Keep evidence['_info_density'] in sync so downstream consumers see one
    # canonical view.
    evidence["_info_density"] = info_density

    return {
        "game": game_description,
        "method": "chain_of_thought",
        "evidence": evidence,
        "response": response,
        "llm_calls": 1,
        "info_density": info_density,
    }


def main():
    print("=" * 60)
    print("NBA CoT Baseline - Step 9")
    print("=" * 60)

    if os.environ.get("ANTHROPIC_API_KEY"):
        print("Using Claude (Anthropic) API")
        llm_fn = call_anthropic
    elif os.environ.get("OPENAI_API_KEY"):
        print("Using GPT-4 (OpenAI) API")
        llm_fn = call_openai
    else:
        print("No API key found. Set ANTHROPIC_API_KEY or OPENAI_API_KEY.")
        return

    result = run_cot_analysis(
        home_abbr="BOS",
        away_abbr="LAL",
        home_name="Boston Celtics",
        away_name="Los Angeles Lakers",
        game_description="Los Angeles Lakers vs Boston Celtics, March 30 2026",
        llm_call_fn=llm_fn,
    )

    print()
    print("=" * 60)
    print("COT BASELINE REPORT")
    print("=" * 60)

    response = result["response"]
    if "FINAL REPORT:" in response:
        report_text = response.split("FINAL REPORT:")[-1].strip()
        print(report_text)
    else:
        print(response)

    print()
    print(f"LLM calls: {result['llm_calls']}")
    print(f"Info density: {result['info_density']}")

    log_path = f"{DATA_DIR}/cot_baseline_log.json"
    save_data = {
        "game": result["game"],
        "method": result["method"],
        "response": result["response"],
        "llm_calls": result["llm_calls"],
        "info_density": result["info_density"],
        "timestamp": datetime.now().isoformat(),
    }
    with open(log_path, "w") as f:
        json.dump(save_data, f, indent=2, default=str)
    print(f"Log saved to {log_path}")

    print()
    print("=" * 60)
    print("TO COMPARE WITH MULTI-AGENT DEBATE:")
    print("=" * 60)
    print("Run: python3 nba_multi_agent.py")
    print("Then compare the predictions and reasoning quality")
    print("between cot_baseline_log.json and multi_agent_log.json")


if __name__ == "__main__":
    main()