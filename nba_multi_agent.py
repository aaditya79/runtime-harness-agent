"""
Step 8: Multi-Agent Debate System
Three agents with different analytical perspectives and tool access
debate an NBA game across iterative rounds.

Agents:
  1. Stats Agent - focuses on numbers (scoring, defense, pace, efficiency)
     Tools: get_team_stats, get_head_to_head, search_similar_games (quantitative only)

  2. Matchup Agent - focuses on context (schedule, travel, rest, coaching, sentiment)
     Tools: get_injuries, search_similar_games, get_team_sentiment

  3. Market Agent - starts from the odds and confirms or challenges them
     Tools: get_odds, get_team_stats, get_injuries, search_similar_games, get_team_sentiment

Debate flow:
  Round 1: Each agent independently analyzes and predicts
  Round 2: Each agent sees the others' arguments and responds
  Round 3 (optional): Final positions after seeing rebuttals
  Moderator: Synthesizes into a final report

Usage:
    export ANTHROPIC_API_KEY="your_key"   (or OPENAI_API_KEY)
    python nba_multi_agent.py

Requires: steps 1-3, 5, 6, and 7 to be completed
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
    parse_action,
    DATA_DIR,
    MAX_TOOL_OBSERVATION_CHARS,
    empty_info_density,
    merge_info_density,
)


# ============================================================
# DEBATE CONFIG
# ============================================================
# Per Du et al. "Improving Factuality and Reasoning in Language Models through
# Multiagent Debate" (2023): each agent should see the OTHER agents' full
# reasoning each round, be able to gather more evidence between rounds, and
# the loop should stop once positions converge.

# Hard ceiling on debate rounds. Even if the env var asks for more, we cap.
MAX_DEBATE_ROUNDS = 4

# Default round count when caller does not specify.
DEFAULT_DEBATE_ROUNDS = int(os.environ.get("NBA_DEBATE_ROUNDS", "2"))

# Max additional tool calls an agent may make within a single debate round.
MAX_DEBATE_TOOL_CALLS_PER_ROUND = int(os.environ.get("NBA_DEBATE_TOOL_CALLS_PER_ROUND", "3"))

# Predictions across all agents within this absolute distance trigger early stop.
DEBATE_CONVERGENCE_THRESHOLD = float(os.environ.get("NBA_DEBATE_CONVERGENCE", "0.05"))


AGENTS = {
    "stats_agent": {
        "name": "Stats & Metrics Agent",
        "tools": {
            "get_team_stats": tool_get_team_stats,
            "get_head_to_head": tool_get_head_to_head,
            "search_similar_games": tool_search_similar_games,
        },
        "system_prompt": """You are the Stats & Metrics Agent. You analyze NBA games purely through numbers.

You focus on: scoring averages, defensive rating, pace, field goal percentages,
rebounding, assists, turnovers, plus/minus, and historical statistical patterns.

You have access to these tools ONLY:
  - get_team_stats(team_abbr, season): Get team's recent stats and record
  - get_head_to_head(team1_abbr, team2_abbr): Get H2H record between teams
  - search_similar_games(query_text, team, n_results): Search historical games by stats

RULES:
- You MUST call at least 2 tools before giving your analysis.
- Call ONE tool per response.
- Base every claim on data from tool observations. Do not make up numbers.
- When calling a tool, use: ACTION: tool_name(arg1="value1")

After gathering data, provide your analysis in this format:

ANALYSIS:
{
    "agent": "stats_agent",
    "prediction": {"home_win_prob": 0.XX, "away_win_prob": 0.XX},
    "confidence": "high/medium/low",
    "key_points": ["point 1", "point 2", "point 3"],
    "reasoning": "Your statistical reasoning..."
}

Start by calling get_team_stats for the home team.""",
    },

    "matchup_agent": {
        "name": "Matchup & Context Agent",
        "tools": {
            "get_injuries": tool_get_injuries,
            "search_similar_games": tool_search_similar_games,
            "get_team_sentiment": tool_get_team_sentiment,
        },
        "system_prompt": """You are the Matchup & Context Agent. You analyze NBA games through situational context.

You focus on: injuries and their impact, schedule factors (back-to-backs, rest days,
travel), home/away dynamics, coaching matchups, momentum, team narrative, and media sentiment.

You have access to these tools ONLY:
  - get_injuries(team_name): Get current injury report for a team
  - search_similar_games(query_text, team, n_results): Search for historically similar situations
  - get_team_sentiment(team_abbr): Get recent media/news sentiment and coverage for a team

RULES:
- You MUST call get_injuries for both teams.
- You MUST call get_team_sentiment for both teams before giving your analysis.
- You MUST call at least 3 tools before giving your analysis.
- Call ONE tool per response.
- Base every claim on data from tool observations. Do not make up numbers.
- When calling a tool, use: ACTION: tool_name(arg1="value1")

After gathering data, provide your analysis in this format:

ANALYSIS:
{
    "agent": "matchup_agent",
    "prediction": {"home_win_prob": 0.XX, "away_win_prob": 0.XX},
    "confidence": "high/medium/low",
    "key_points": ["point 1", "point 2", "point 3"],
    "reasoning": "Your contextual reasoning..."
}

Start by calling get_injuries for the home team.""",
    },

    "market_agent": {
        "name": "Market & Odds Agent",
        "tools": {
            "get_odds": tool_get_odds,
            "get_team_stats": tool_get_team_stats,
            "get_injuries": tool_get_injuries,
            "search_similar_games": tool_search_similar_games,
            "get_team_sentiment": tool_get_team_sentiment,
        },
        "system_prompt": """You are the Market & Odds Agent. You start from the bookmaker odds and try to
confirm or challenge them.

You focus on: what the market thinks, where the line has moved, whether the odds
reflect the true probabilities, where there might be value, and whether media sentiment
or coverage intensity suggests the market narrative is overreacting or underreacting.

You have access to these tools:
  - get_odds(home_team, away_team): Get current odds from multiple sportsbooks
  - get_team_stats(team_abbr, season): Get team stats to cross-check market pricing
  - get_injuries(team_name): Check if injuries are properly priced in
  - search_similar_games(query_text, team, n_results): Find historical precedent
  - get_team_sentiment(team_abbr): Get recent media/news sentiment and coverage for a team

RULES:
- You MUST call get_odds first, then at least 2 more tools.
- You SHOULD call get_team_sentiment for both teams before giving your analysis.
- Call ONE tool per response.
- Base every claim on data from tool observations. Do not make up numbers.
- When calling a tool, use: ACTION: tool_name(arg1="value1")

After gathering data, provide your analysis in this format:

ANALYSIS:
{
    "agent": "market_agent",
    "prediction": {"home_win_prob": 0.XX, "away_win_prob": 0.XX},
    "market_implied": {"home_win_prob": 0.XX, "away_win_prob": 0.XX},
    "value_spots": ["any value bets identified"],
    "confidence": "high/medium/low",
    "key_points": ["point 1", "point 2", "point 3"],
    "reasoning": "Your market-based reasoning..."
}

Start by calling get_odds for this game.""",
    },
}


def run_single_agent(agent_key, game_description, llm_call_fn, extra_context="", max_steps=7,
                     info_density=None):
    """
    Run one agent through its independent analysis phase.

    If `info_density` is provided, tool result counts are accumulated into it
    in place. Returns the agent's raw response text.
    """
    agent = AGENTS[agent_key]
    print(f"\n{'='*50}")
    print(f"  {agent['name']}")
    print(f"{'='*50}")

    system_prompt = agent["system_prompt"]
    if extra_context:
        system_prompt += f"\n\nCONTEXT FROM OTHER AGENTS:\n{extra_context}"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Analyze this game: {game_description}"},
    ]

    step = 0
    while step < max_steps:
        response_text = llm_call_fn(messages)

        if "ANALYSIS:" in response_text:
            print(f"  Step {step+1}: ANALYSIS produced")
            return response_text

        tool_name, kwargs, action_line = parse_action(response_text)

        if tool_name:
            if tool_name in agent["tools"]:
                print(f"  Step {step+1}: {tool_name}({kwargs})")
                result = agent["tools"][tool_name](**kwargs)
                if info_density is not None:
                    merge_info_density(info_density, tool_name, result)
                if len(str(result)) > MAX_TOOL_OBSERVATION_CHARS:
                    result = str(result)[:MAX_TOOL_OBSERVATION_CHARS] + "\n... (truncated)"
                print(f"    -> {str(result)[:120]}...")

                messages.append({"role": "assistant", "content": response_text})
                messages.append({"role": "user", "content": f"OBSERVATION: {result}"})
            else:
                messages.append({"role": "assistant", "content": response_text})
                messages.append({
                    "role": "user",
                    "content": f"ERROR: You don't have access to {tool_name}. Your tools are: {list(agent['tools'].keys())}"
                })
                print(f"  Step {step+1}: DENIED {tool_name} (not in this agent's tools)")
        else:
            messages.append({"role": "assistant", "content": response_text})
            messages.append({"role": "user", "content": "Continue. Call a tool or produce your ANALYSIS."})

        step += 1

    messages.append({
        "role": "user",
        "content": "Do not call any more tools. Produce your ANALYSIS now using only the information already gathered."
    })
    response_text = llm_call_fn(messages)
    return response_text


def extract_analysis(response_text):
    if "ANALYSIS:" not in response_text:
        return None
    try:
        json_str = response_text.split("ANALYSIS:")[-1].strip()
        start = json_str.find("{")
        end = json_str.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(json_str[start:end])
    except json.JSONDecodeError:
        pass
    return None


def _format_other_agents_full_reasoning(agent_raw_responses, agent_analyses, exclude_key):
    """
    Build the context block for one agent's debate turn.

    Per Du et al., agents debate against each other's FULL reasoning, not just
    their final probability. We pass the raw response text so the agent can
    react to the actual argument, falling back to the parsed JSON if the raw
    text is unavailable.
    """
    parts = []
    for other_key, raw in agent_raw_responses.items():
        if other_key == exclude_key:
            continue
        other_name = AGENTS[other_key]["name"]
        if raw:
            parts.append(f"=== {other_name} ===\n{raw}")
        else:
            analysis = agent_analyses.get(other_key, {})
            parts.append(f"=== {other_name} (parsed) ===\n{json.dumps(analysis, indent=2)}")
    return "\n\n".join(parts)


def _run_agent_debate_turn(agent_key, game_description, context, llm_call_fn,
                           max_tool_calls=MAX_DEBATE_TOOL_CALLS_PER_ROUND,
                           info_density=None):
    """
    Run a single agent's debate turn with iterative tool use.

    The agent is shown the others' full reasoning and may make up to
    `max_tool_calls` additional tool calls (within its own tool restrictions)
    before producing its updated ANALYSIS. Returns (raw_response_text,
    parsed_analysis_or_none, tool_results_list).
    """
    agent = AGENTS[agent_key]

    debate_prompt = f"""The other agents have shared their full reasoning. Review their arguments
critically. You may agree, disagree, or adjust your prediction.

You may gather additional data with up to {max_tool_calls} more tool calls
to challenge or confirm their claims. Use ACTION: tool_name(arg="value") to
call a tool, then wait for the OBSERVATION before deciding what to do next.
When you have enough information, produce your updated ANALYSIS in the same
JSON format as before.

Other agents' positions:
{context}"""

    messages = [
        {"role": "system", "content": agent["system_prompt"]},
        {"role": "user", "content": f"Game: {game_description}\n\n{debate_prompt}"},
    ]

    tool_results = []
    response_text = ""

    for tool_call_num in range(max_tool_calls + 1):
        response_text = llm_call_fn(messages)

        # If the agent produced its analysis, we are done with this turn.
        if "ANALYSIS:" in response_text:
            break

        tool_name, kwargs, _ = parse_action(response_text)

        if not tool_name:
            # Nudge once for an analysis if no tool / no analysis.
            messages.append({"role": "assistant", "content": response_text})
            messages.append({
                "role": "user",
                "content": "Continue. Either call a tool with ACTION: ... or produce your updated ANALYSIS now."
            })
            continue

        if tool_name not in agent["tools"]:
            messages.append({"role": "assistant", "content": response_text})
            messages.append({
                "role": "user",
                "content": (
                    f"ERROR: You don't have access to {tool_name}. "
                    f"Your tools are: {list(agent['tools'].keys())}. "
                    "Either call an allowed tool or produce your updated ANALYSIS."
                ),
            })
            print(f"    DENIED {tool_name} (not in this agent's tools)")
            continue

        if tool_call_num >= max_tool_calls:
            # We have hit the budget: force final analysis on next turn.
            messages.append({"role": "assistant", "content": response_text})
            messages.append({
                "role": "user",
                "content": "Tool call budget exhausted. Produce your updated ANALYSIS now using the data already gathered."
            })
            continue

        print(f"    Tool call: {tool_name}({kwargs})")
        try:
            result = agent["tools"][tool_name](**kwargs)
        except Exception as e:
            result = f"Error calling {tool_name}: {e}"
        if info_density is not None:
            merge_info_density(info_density, tool_name, result)
        if len(str(result)) > MAX_TOOL_OBSERVATION_CHARS:
            result = str(result)[:MAX_TOOL_OBSERVATION_CHARS] + "\n... (truncated)"

        tool_results.append({"tool": tool_name, "args": kwargs, "result_preview": str(result)[:500]})
        messages.append({"role": "assistant", "content": response_text})
        messages.append({"role": "user", "content": f"OBSERVATION: {result}"})

    analysis = extract_analysis(response_text)
    return response_text, analysis, tool_results


def _check_convergence(agent_analyses, threshold=DEBATE_CONVERGENCE_THRESHOLD):
    """
    Return True iff every agent's home_win_prob is within `threshold` of every
    other agent's home_win_prob. Missing or unparsable predictions disqualify
    convergence (we want to keep debating until we have real numbers).
    """
    probs = []
    for analysis in agent_analyses.values():
        if not isinstance(analysis, dict):
            return False
        pred = analysis.get("prediction", {})
        try:
            probs.append(float(pred.get("home_win_prob")))
        except (TypeError, ValueError):
            return False

    if len(probs) < 2:
        return False
    return (max(probs) - min(probs)) <= threshold


def run_debate_round(game_description, agent_analyses, round_num, llm_call_fn,
                     agent_raw_responses=None,
                     max_tool_calls=MAX_DEBATE_TOOL_CALLS_PER_ROUND,
                     info_density=None):
    """
    Run one debate round. Each agent sees the OTHERS' full reasoning (raw
    text) and may make additional tool calls within its own tool restrictions.

    Returns (updated_analyses, updated_raw_responses, per_agent_tool_results).

    Backward-compat: callers that pass only the legacy positional args still
    get a working updated_analyses dict.
    """
    print(f"\n{'#'*60}")
    print(f"  DEBATE ROUND {round_num}")
    print(f"{'#'*60}")

    if agent_raw_responses is None:
        agent_raw_responses = {}

    updated_analyses = {}
    updated_raw_responses = {}
    per_agent_tool_results = {}

    for agent_key in AGENTS:
        agent = AGENTS[agent_key]
        context = _format_other_agents_full_reasoning(
            agent_raw_responses, agent_analyses, exclude_key=agent_key
        )

        print(f"\n  {agent['name']} responding to debate...")

        raw, analysis, tool_results = _run_agent_debate_turn(
            agent_key, game_description, context, llm_call_fn,
            max_tool_calls=max_tool_calls,
            info_density=info_density,
        )

        updated_raw_responses[agent_key] = raw
        per_agent_tool_results[agent_key] = tool_results

        if analysis:
            updated_analyses[agent_key] = analysis
            pred = analysis.get("prediction", {})
            print(f"    Updated prediction: Home {pred.get('home_win_prob', '?')} | Away {pred.get('away_win_prob', '?')}")
        else:
            updated_analyses[agent_key] = agent_analyses.get(agent_key, {})
            print(f"    Kept previous position (parse failed)")

    return updated_analyses, updated_raw_responses, per_agent_tool_results


def moderate(game_description, agent_analyses, llm_call_fn):
    print(f"\n{'#'*60}")
    print(f"  MODERATOR SYNTHESIS")
    print(f"{'#'*60}")

    analyses_text = ""
    for agent_key, analysis in agent_analyses.items():
        agent_name = AGENTS[agent_key]["name"]
        analyses_text += f"\n{agent_name}:\n{json.dumps(analysis, indent=2)}\n"

    moderator_prompt = f"""You are the Moderator. Three specialized agents have analyzed this NBA game
and debated their positions. Your job is to synthesize their analyses into one final betting report.

Game: {game_description}

Agent Analyses:
{analyses_text}

Consider:
- Where do the agents agree? Those are high-confidence findings.
- Where do they disagree? Weigh each agent's reasoning and data quality.
- The Stats Agent is most reliable for performance metrics.
- The Matchup Agent is most reliable for injury impact and schedule effects.
- The Matchup Agent is also most reliable for media/news sentiment and coverage context.
- The Market Agent is most reliable for understanding what the odds already reflect.

If market odds are unavailable or null, the value_assessment must clearly explain that no live odds were found for the selected matchup in the current upcoming-games odds feed. Say that this usually means the selected teams are not actually scheduled to play each other in the current live odds dataset, and tell the user to choose a matchup that exists in the live odds feed.

Produce the FINAL REPORT in this JSON format:
{{
    "game": "TEAM1 vs TEAM2",
    "date": "YYYY-MM-DD",
    "method": "multi-agent debate",
    "agent_predictions": {{
        "stats_agent": {{"home": X.XX, "away": X.XX}},
        "matchup_agent": {{"home": X.XX, "away": X.XX}},
        "market_agent": {{"home": X.XX, "away": X.XX}}
    }},
    "synthesized_prediction": {{
        "home_win_prob": 0.XX,
        "away_win_prob": 0.XX,
        "confidence": "high/medium/low"
    }},
    "market_odds": {{
        "home_implied_prob": 0.XX,
        "away_implied_prob": 0.XX
    }},
    "key_factors": [
        {{"factor": "...", "impact": "favors_home/favors_away/neutral", "importance": "high/medium/low", "source_agent": "..."}}
    ],
    "areas_of_agreement": ["..."],
    "areas_of_disagreement": ["..."],
    "reasoning": "Step-by-step synthesis...",
    "value_assessment": "Where does the synthesized view differ from the market? If no live odds are available, explicitly say that the selected matchup does not appear in the current upcoming-games odds feed and tell the user to choose a matchup that actually exists in the live odds feed."
}}"""

    messages = [
        {
            "role": "system",
            "content": "You are a moderator synthesizing multiple expert analyses into a final betting report. Use only the data provided by the agents. Do not introduce new information."
        },
        {"role": "user", "content": moderator_prompt},
    ]

    response = llm_call_fn(messages)
    return response


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
        system=system_msg,
        messages=conv_messages,
    )
    log_anthropic_response("nba_multi_agent.py", response)
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
    log_openai_response("nba_multi_agent.py", response)
    return response.choices[0].message.content


def run_full_debate(game_description, llm_call_fn, num_debate_rounds=DEFAULT_DEBATE_ROUNDS):
    from nba_cost_logger import tally_calls
    """
    Run the full multi-agent debate.

    Phase 1: each agent independently analyses with its own tool budget.
    Phase 2: up to `num_debate_rounds` debate rounds (capped at MAX_DEBATE_ROUNDS).
             Each round shows agents the OTHERS' full reasoning and lets them
             call additional tools. We stop early once predictions converge
             (all home_win_prob within DEBATE_CONVERGENCE_THRESHOLD).
    Phase 3: moderator synthesises into a final report.

    Returns (backward-compatible additions only):
        game, agent_analyses, final_report, num_debate_rounds,
        debate_rounds        -> list of per-round snapshots
        converged            -> bool, whether early stop fired
        rounds_executed      -> int, actual rounds run (<= num_debate_rounds)
    """
    print("=" * 60)
    print(f"MULTI-AGENT DEBATE: {game_description}")
    print("=" * 60)

    # Cap aggressively to protect spend.
    num_debate_rounds = max(0, min(int(num_debate_rounds), MAX_DEBATE_ROUNDS))

    print(f"\n{'#'*60}")
    print(f"  PHASE 1: INDEPENDENT ANALYSIS")
    print(f"{'#'*60}")

    info_density = empty_info_density()

    with tally_calls() as call_records:
        agent_analyses = {}
        agent_raw_responses = {}

        for agent_key in AGENTS:
            response = run_single_agent(
                agent_key, game_description, llm_call_fn,
                info_density=info_density,
            )
            agent_raw_responses[agent_key] = response
            analysis = extract_analysis(response)
            if analysis:
                agent_analyses[agent_key] = analysis
                pred = analysis.get("prediction", {})
                print(f"  -> Prediction: Home {pred.get('home_win_prob', '?')} | Away {pred.get('away_win_prob', '?')}")
            else:
                agent_analyses[agent_key] = {"error": "Failed to parse analysis", "raw": response[:500]}
                print(f"  -> Failed to parse analysis")

        debate_rounds_log = [{
            "round": 0,
            "phase": "independent_analysis",
            "agent_analyses": json.loads(json.dumps(agent_analyses, default=str)),
            "tool_calls": {},
        }]

        converged = _check_convergence(agent_analyses)
        rounds_executed = 0

        for round_num in range(1, num_debate_rounds + 1):
            if converged:
                print(f"\n  Convergence reached after round {rounds_executed}; "
                      f"skipping remaining rounds.")
                break

            agent_analyses, agent_raw_responses, round_tool_results = run_debate_round(
                game_description, agent_analyses, round_num, llm_call_fn,
                agent_raw_responses=agent_raw_responses,
                info_density=info_density,
            )
            rounds_executed = round_num
            debate_rounds_log.append({
                "round": round_num,
                "phase": "debate",
                "agent_analyses": json.loads(json.dumps(agent_analyses, default=str)),
                "tool_calls": round_tool_results,
            })
            converged = _check_convergence(agent_analyses)

        final_report = moderate(game_description, agent_analyses, llm_call_fn)

        info_density["context_tokens"] = sum(
            int(r.get("input_tokens", 0) or 0) for r in call_records
        )

    return {
        "game": game_description,
        "agent_analyses": agent_analyses,
        "final_report": final_report,
        "num_debate_rounds": num_debate_rounds,
        "rounds_executed": rounds_executed,
        "converged": converged,
        "debate_rounds": debate_rounds_log,
        "info_density": info_density,
    }


def main():
    print("=" * 60)
    print("NBA Multi-Agent Debate - Step 8")
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

    game = "Los Angeles Lakers vs Boston Celtics, March 30 2026"

    result = run_full_debate(game, llm_fn, num_debate_rounds=2)

    print()
    print("=" * 60)
    print("FINAL SYNTHESIZED REPORT")
    print("=" * 60)
    print(result["final_report"])

    log_path = f"{DATA_DIR}/multi_agent_log.json"
    save_data = {
        "game": result["game"],
        "agent_analyses": result["agent_analyses"],
        "final_report": result["final_report"],
        "num_debate_rounds": result["num_debate_rounds"],
        "rounds_executed": result.get("rounds_executed"),
        "converged": result.get("converged"),
        "debate_rounds": result.get("debate_rounds", []),
        "timestamp": datetime.now().isoformat(),
    }
    with open(log_path, "w") as f:
        json.dump(save_data, f, indent=2, default=str)
    print(f"\nFull debate log saved to {log_path}")

    print()
    print("=" * 60)
    print("AGENT PREDICTION COMPARISON")
    print("=" * 60)
    for agent_key, analysis in result["agent_analyses"].items():
        name = AGENTS[agent_key]["name"]
        pred = analysis.get("prediction", {})
        conf = analysis.get("confidence", "?")
        print(f"  {name}: Home {pred.get('home_win_prob', '?')} | Away {pred.get('away_win_prob', '?')} (confidence: {conf})")


if __name__ == "__main__":
    main()