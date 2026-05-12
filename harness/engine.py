from typing import Callable

from .models import HarnessResult, ToolCallLog
from .tracer import Tracer
from .validator import Validator
from .guardrail import GuardrailEngine


def run_with_harness(
    game_description: str,
    llm_call_fn: Callable,
    ground_truth: dict | None = None,
    num_debate_rounds: int = 2,
    mode: str = "debate",
) -> HarnessResult:
    """
    Run the NBA prediction system wrapped in validate-trace-enforce layers.

    Args:
        game_description:  e.g. "Los Angeles Lakers vs Boston Celtics, March 30 2026"
        llm_call_fn:       LLM callable (e.g. call_anthropic from nba_multi_agent)
        ground_truth:      Optional {stat_key: expected_value} for stat citation checks.
                           Example: {"LAL_avg_points_last_10": 115.2}
        num_debate_rounds: Debate rounds passed to run_full_debate (multi-agent mode only)
        mode:              "debate" (multi-agent) or "single" (single ReAct agent)

    Returns:
        HarnessResult with validation, trace, enforcement action, and final output.
    """
    tracer = Tracer()
    validator = Validator()
    guardrail = GuardrailEngine()

    # ------------------------------------------------------------------
    # 1. Run the underlying agent system, tracing the whole call as one entry
    # ------------------------------------------------------------------
    tool_label = "run_debate" if mode == "debate" else "run_agent"
    with tracer.trace_tool(tool_label, {"game": game_description, "rounds": num_debate_rounds}) as rec:
        if mode == "debate":
            from nba_multi_agent import run_full_debate
            result = run_full_debate(game_description, llm_call_fn, num_debate_rounds)
        else:
            from nba_agent import run_agent
            result = run_agent(game_description, llm_call_fn)
        rec["output"] = result

    # ------------------------------------------------------------------
    # 2. Reconstruct per-tool logs from the debate rounds structure.
    #    run_full_debate captures tool calls for each debate round but not
    #    for the independent analysis phase — we log what's available.
    # ------------------------------------------------------------------
    if mode == "debate":
        for round_entry in result.get("debate_rounds", []):
            for agent_key, tool_list in round_entry.get("tool_calls", {}).items():
                for t in (tool_list or []):
                    tracer.tool_calls.append(ToolCallLog(
                        tool=t.get("tool", "unknown"),
                        inputs=t.get("args", {}),
                        output=t.get("result_preview", ""),
                        latency_ms=0.0,
                    ))

    # ------------------------------------------------------------------
    # 3. Log agent states
    # ------------------------------------------------------------------
    if mode == "debate":
        for agent_key, analysis in result.get("agent_analyses", {}).items():
            tracer.log_agent_state(agent_key, analysis if isinstance(analysis, dict) else {})
    else:
        tracer.log_agent_state(
            "react_agent",
            {"steps": result.get("steps"), "info_density": result.get("info_density", {})},
        )

    # ------------------------------------------------------------------
    # 4. Finalize trace → validate → enforce
    # ------------------------------------------------------------------
    trace = tracer.finalize(result)
    validation = validator.validate(result, ground_truth)
    action, enforced_output = guardrail.evaluate(validation, trace)

    return HarnessResult(
        validation=validation,
        trace=trace,
        action=action,
        final_output=enforced_output,
    )
