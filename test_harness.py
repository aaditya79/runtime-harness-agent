#!/usr/bin/env python3
"""
test_harness.py
===============
Runtime harness demo for the QFAI Trustworthy-LLM research prototype.

Demonstrates the validate-trace-enforce layer on a completed 2024-25 NBA game.

  Game  : Boston Celtics (home) vs Atlanta Hawks (away)
  Date  : 2024-11-12
  Result: Atlanta Hawks won  (actual_home_win = 0 in backtest log)
  Source: data/sample/backtest_predictions_sample.csv, game_id 22400001

Three checks are run:

  1. Live harness run using scripted (no-API-key) debate agents → expect PASS
  2. Injected output with incoherent probabilities (0.85 + 0.65 = 1.50)  → expect BLOCK
  3. Injected output with a fabricated stat citation                      → expect REVISE

A final tally confirms all three enforcement rules fired as expected.
"""

import json
import sys
import textwrap

from harness import (
    EnforcementAction,
    GuardrailEngine,
    Tracer,
    Validator,
    run_with_harness,
)


# ──────────────────────────────────────────────────────────────────────────────
# Scripted mock LLM  (no API key required)
#
# Each agent has a fixed sequence of tool calls followed by a pre-written
# ANALYSIS block.  The moderator returns a pre-written FINAL REPORT.
# Numbers are grounded in the backtest CSV for this game:
#   BOS avg_pts_last_10 ≈ 119.0, net_rating ≈ +9.3
#   ATL avg_pts_last_10 ≈ 115.7, net_rating ≈ -6.5
#   BOS season record 9-2 vs ATL 4-7 at time of game
# ──────────────────────────────────────────────────────────────────────────────

_STATS_ANALYSIS = """\
ANALYSIS:
{
    "agent": "stats_agent",
    "prediction": {"home_win_prob": 0.72, "away_win_prob": 0.28},
    "confidence": "high",
    "key_points": [
        "BOS season record 9-2 vs ATL 4-7 (5-game gap)",
        "BOS net rating +9.3 vs ATL -6.5 over last 10 games (16-pt swing)",
        "BOS averages 119.0 PPG vs ATL 115.7 PPG; BOS FG% 46.8 vs ATL 44.1"
    ],
    "reasoning": "Boston holds a decisive statistical edge across every major metric. Home court amplifies this advantage. Atlanta is on a back-to-back having lost to Chicago on Nov 9, introducing fatigue risk."
}"""

_MATCHUP_ANALYSIS = """\
ANALYSIS:
{
    "agent": "matchup_agent",
    "prediction": {"home_win_prob": 0.70, "away_win_prob": 0.30},
    "confidence": "medium",
    "key_points": [
        "ATL on back-to-back road trip; played CHI 3 days prior",
        "Bogdanovic (15+ PPG) questionable; De'Andre Hunter listed out",
        "BOS rested with 2 days off; no injury concerns reported"
    ],
    "reasoning": "Atlanta's injury situation and back-to-back fatigue meaningfully reduce their win probability. Boston's home court and full roster create a sizable situational edge."
}"""

_MARKET_ANALYSIS = """\
ANALYSIS:
{
    "agent": "market_agent",
    "prediction": {"home_win_prob": 0.71, "away_win_prob": 0.29},
    "market_implied": {"home_win_prob": 0.68, "away_win_prob": 0.32},
    "value_spots": ["Slight value on BOS moneyline if market is slow to price ATL injuries"],
    "confidence": "medium",
    "key_points": [
        "Market lines not available for this historical game",
        "Statistical edge aligns with consensus models placing BOS at ~68-72%",
        "ATL injury news may not have been fully priced at open"
    ],
    "reasoning": "Based on comparable matchups in the vector store, Boston's home edge and ATL's depleted roster suggest the model probability of 0.71 is consistent with rational market pricing."
}"""

_FINAL_REPORT = """\
FINAL REPORT:
{
    "game": "BOS vs ATL",
    "date": "2024-11-12",
    "method": "multi-agent debate",
    "agent_predictions": {
        "stats_agent":   {"home": 0.72, "away": 0.28},
        "matchup_agent": {"home": 0.70, "away": 0.30},
        "market_agent":  {"home": 0.71, "away": 0.29}
    },
    "synthesized_prediction": {
        "home_win_prob": 0.71,
        "away_win_prob": 0.29,
        "confidence": "high"
    },
    "market_odds": {
        "home_implied_prob": 0.68,
        "away_implied_prob": 0.32
    },
    "key_factors": [
        {"factor": "BOS season record 9-2 vs ATL 4-7",             "impact": "favors_home", "importance": "high",   "source_agent": "stats_agent"},
        {"factor": "BOS net rating +9.3 vs ATL -6.5",              "impact": "favors_home", "importance": "high",   "source_agent": "stats_agent"},
        {"factor": "ATL back-to-back road fatigue",                 "impact": "favors_home", "importance": "high",   "source_agent": "matchup_agent"},
        {"factor": "ATL key injuries (Bogdanovic / Hunter)",        "impact": "favors_home", "importance": "medium", "source_agent": "matchup_agent"},
        {"factor": "Market implies BOS at ~68%; model at 71%",      "impact": "favors_home", "importance": "low",    "source_agent": "market_agent"}
    ],
    "areas_of_agreement": [
        "All three agents predict BOS win probability between 70-72%",
        "ATL back-to-back fatigue is a consistent concern across all agents"
    ],
    "areas_of_disagreement": [
        "Market agent notes ATL injury news may not have been fully priced at open"
    ],
    "reasoning": "Strong consensus across stats, context, and market lenses. Boston's home court, superior record, and Atlanta's travel fatigue create a compelling case for the Celtics.",
    "value_assessment": "Marginal value on BOS moneyline if the market opened before ATL injury news was confirmed."
}"""


def mock_debate_llm(messages: list) -> str:
    """
    Scripted LLM for the three debate agents and moderator.

    Advances each agent through its tool-call sequence by counting
    OBSERVATION messages already in the conversation. The moderator
    returns its FINAL REPORT immediately.
    """
    system_content = next(
        (m["content"] for m in messages if m.get("role") == "system"), ""
    )

    # Count prior tool observations to know which step we are on.
    obs_count = sum(
        1 for m in messages
        if m.get("role") == "user"
        and str(m.get("content", "")).startswith("OBSERVATION:")
    )

    # ── Moderator ────────────────────────────────────────────────────────────
    if "Moderator" in system_content or "moderator" in system_content.lower():
        return _FINAL_REPORT

    # ── Stats & Metrics Agent ────────────────────────────────────────────────
    if "Stats & Metrics Agent" in system_content:
        if obs_count == 0:
            return 'ACTION: get_team_stats(team_abbr="BOS")'
        if obs_count == 1:
            return 'ACTION: get_head_to_head(team1_abbr="BOS", team2_abbr="ATL")'
        return _STATS_ANALYSIS

    # ── Matchup & Context Agent ───────────────────────────────────────────────
    if "Matchup & Context Agent" in system_content:
        if obs_count == 0:
            return 'ACTION: get_injuries(team_name="Boston")'
        if obs_count == 1:
            return 'ACTION: get_injuries(team_name="Atlanta")'
        if obs_count == 2:
            return 'ACTION: get_team_sentiment(team_abbr="BOS")'
        return _MATCHUP_ANALYSIS

    # ── Market & Odds Agent ───────────────────────────────────────────────────
    if "Market & Odds Agent" in system_content:
        if obs_count == 0:
            return 'ACTION: get_odds(home_team="Boston", away_team="Atlanta")'
        if obs_count == 1:
            return 'ACTION: get_team_stats(team_abbr="ATL")'
        if obs_count == 2:
            return 'ACTION: get_injuries(team_name="Boston")'
        return _MARKET_ANALYSIS

    # Fallback (should not be reached in a normal debate run)
    return 'ACTION: get_team_stats(team_abbr="BOS")'


# ──────────────────────────────────────────────────────────────────────────────
# Formatting helpers
# ──────────────────────────────────────────────────────────────────────────────

def _tick(passed: bool) -> str:
    return "✓" if passed else "✗"


def _wrap(text: str, width: int = 72, indent: str = "    ") -> str:
    return textwrap.fill(text, width=width, initial_indent=indent,
                         subsequent_indent=indent)


def _section(title: str) -> None:
    print(f"\n{'─' * 64}")
    print(f"  {title}")
    print(f"{'─' * 64}")


def _print_harness_result(result, label: str, expected: EnforcementAction) -> bool:
    action_str = result.action.value.upper()
    ok = result.action == expected

    print(f"\n  Enforcement Action : {action_str}")
    print(f"  Trace Hash         : {result.trace_hash[:20]}...")

    print("\n  Validation checks:")
    for check in result.validation.checks:
        status = _tick(check.passed)
        print(f"    {status}  {check.name:<22} {check.detail}")

    print("\n  Agent states logged:")
    for state_log in result.trace.agent_states:
        pred = state_log.state.get("prediction", {})
        conf = state_log.state.get("confidence", "—")
        h = pred.get("home_win_prob", "?")
        a = pred.get("away_win_prob", "?")
        print(f"    {state_log.agent_id:<18} "
              f"home_win_prob={h}  away_win_prob={a}  confidence={conf}")

    expected_str = expected.value.upper()
    verdict = "✓  CORRECT" if ok else f"✗  WRONG (expected {expected_str})"
    print(f"\n  Result: {action_str} — {verdict}")
    return ok


# ──────────────────────────────────────────────────────────────────────────────
# Test 1: live harness run
# ──────────────────────────────────────────────────────────────────────────────

def test_live_run() -> bool:
    _section("TEST 1 / 3   Live harness run  (multi-agent debate, no API key)")
    print()
    print("  Game   : Boston Celtics (home) vs Atlanta Hawks")
    print("  Date   : 2024-11-12  |  Season: 2024-25")
    print("  Actual : Atlanta Hawks won  (actual_home_win = 0)")
    print()
    print("  Running scripted three-agent debate + moderator synthesis...")
    print("  (Agent tool calls use local CSV data; errors are expected when")
    print("   CSVs are absent — the harness layer operates on top of them.)")

    # Suppress the verbose debate console output so the harness section is
    # readable.  Real runs with a live API can remove this redirect.
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        result = run_with_harness(
            game_description="Boston Celtics vs Atlanta Hawks, November 12 2024",
            llm_call_fn=mock_debate_llm,
            ground_truth=None,
            num_debate_rounds=2,
            mode="debate",
        )

    return _print_harness_result(result, label="live run", expected=EnforcementAction.PASS)


# ──────────────────────────────────────────────────────────────────────────────
# Test 2: BLOCK — incoherent probabilities
# ──────────────────────────────────────────────────────────────────────────────

def test_block_injection() -> bool:
    _section("TEST 2 / 3   BLOCK injection  (probabilities sum to 1.50)")

    incoherent_output = {
        "final_report": json.dumps({
            "synthesized_prediction": {
                "home_win_prob": 0.85,
                "away_win_prob": 0.65,
            },
            "reasoning": "Probabilities were not normalised — this output is corrupt.",
        }),
        "agent_analyses": {
            "stats_agent": {"prediction": {"home_win_prob": 0.85, "away_win_prob": 0.65}},
        },
    }

    print()
    print("  Injecting output with home_win_prob=0.85 and away_win_prob=0.65")
    print("  (0.85 + 0.65 = 1.50 — clearly incoherent)")

    tracer = Tracer()
    trace = tracer.finalize(incoherent_output)

    validator = Validator()
    validation = validator.validate(incoherent_output)

    guardrail = GuardrailEngine()
    action, message = guardrail.evaluate(validation, trace)

    ok = action == EnforcementAction.BLOCK
    print(f"\n  Enforcement Action : {action.value.upper()}")
    print(f"  Guardrail message  : {message[:80]}...")
    prob_check = next(c for c in validation.checks if c.name == "prob_coherence")
    print(f"\n  prob_coherence check: {_tick(prob_check.passed)}  {prob_check.detail}")
    verdict = "✓  CORRECT" if ok else "✗  WRONG (expected BLOCK)"
    print(f"\n  Result: {action.value.upper()} — {verdict}")
    return ok


# ──────────────────────────────────────────────────────────────────────────────
# Test 3: REVISE — stat citation inconsistency
# ──────────────────────────────────────────────────────────────────────────────

def test_revise_injection() -> bool:
    _section("TEST 3 / 3   REVISE injection  (stat citation inconsistency)")

    # Ground truth from the backtest CSV / tool results for this game.
    ground_truth = {
        "BOS_avg_points_last_10": 119.0,   # Boston averaged 119.0 PPG
    }

    # The injected reasoning cites 92.5 — a 22 % deviation from 119.0.
    # This is above the Validator's 15 % tolerance, so stat_consistency fails.
    bad_stat_output = {
        "final_report": (
            "FINAL REPORT:\n"
            + json.dumps({
                "synthesized_prediction": {
                    "home_win_prob": 0.71,
                    "away_win_prob": 0.29,
                },
                "reasoning": (
                    "Boston's offense has been underwhelming; "
                    "BOS_avg_points_last_10 was 92.5 points per game, "
                    "well below their historical baseline."
                ),
            })
        ),
        # Single agent so no inter-agent spread; guardrail will not escalate.
        "agent_analyses": {
            "stats_agent": {"prediction": {"home_win_prob": 0.71, "away_win_prob": 0.29}},
        },
    }

    cited_value = 92.5
    rel_err = abs(cited_value - ground_truth["BOS_avg_points_last_10"]) / ground_truth["BOS_avg_points_last_10"]

    print()
    print(f"  Ground truth : BOS_avg_points_last_10 = {ground_truth['BOS_avg_points_last_10']}")
    print(f"  Cited value  : {cited_value}  (deviation {rel_err:.0%}, threshold 15 %)")
    print()
    print("  Probabilities sum to 1.0 so BLOCK does not fire.")
    print("  Agents agree so ESCALATE does not fire.")
    print("  Stat inconsistency should trigger REVISE.")

    tracer = Tracer()
    trace = tracer.finalize(bad_stat_output)

    validator = Validator()
    validation = validator.validate(bad_stat_output, ground_truth)

    guardrail = GuardrailEngine()
    action, message = guardrail.evaluate(validation, trace)

    ok = action == EnforcementAction.REVISE
    print(f"\n  Enforcement Action : {action.value.upper()}")
    print(f"  Guardrail message  : {message[:80]}...")
    stat_check = next(c for c in validation.checks if c.name == "stat_consistency")
    print(f"\n  stat_consistency check: {_tick(stat_check.passed)}  {stat_check.detail[:80]}")
    verdict = "✓  CORRECT" if ok else "✗  WRONG (expected REVISE)"
    print(f"\n  Result: {action.value.upper()} — {verdict}")
    return ok


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def main() -> None:
    print()
    print("=" * 64)
    print("  QFAI RUNTIME HARNESS DEMO")
    print("  Validate-Trace-Enforce layer  |  MatchOdds AI substrate")
    print("=" * 64)
    print()
    print("  Framework : Columbia Quantum FinAI Lab")
    print("  Game      : BOS vs ATL  |  2024-11-12  |  Season 2024-25")
    print("  Source    : data/sample/backtest_predictions_sample.csv")
    print()
    print("  Enforcement rules under test:")
    print("    BLOCK    — win probabilities do not sum to ≈1")
    print("    REVISE   — stat citation deviates from ground truth by > 15 %")
    print("    PASS     — all checks clear (expected on the live debate run)")

    results = {
        "PASS  (live run)": test_live_run(),
        "BLOCK (prob injection)": test_block_injection(),
        "REVISE (stat injection)": test_revise_injection(),
    }

    passed = sum(results.values())
    total = len(results)

    print()
    print("=" * 64)
    print("  SUMMARY")
    print("=" * 64)
    print()
    for label, ok in results.items():
        print(f"    {_tick(ok)}  {label}")
    print()
    print(f"  {passed}/{total} enforcement rules triggered correctly")
    print()

    if passed < total:
        sys.exit(1)


if __name__ == "__main__":
    main()
