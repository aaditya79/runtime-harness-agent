from .models import EnforcementAction, TraceRecord, ValidationResult

# Max allowed spread in home_win_prob across debate agents before escalation.
DEBATE_DISAGREEMENT_THRESHOLD = 0.15


class GuardrailEngine:
    def __init__(self, disagreement_threshold: float = DEBATE_DISAGREEMENT_THRESHOLD):
        self.disagreement_threshold = disagreement_threshold

    def evaluate(
        self, validation: ValidationResult, trace: TraceRecord
    ) -> tuple[EnforcementAction, object]:
        """
        Apply validate-trace-enforce rules and return (action, output).

        Priority: BLOCK > ESCALATE > REVISE > PASS
        """
        output = trace.final_output
        failed = {c.name for c in validation.failed_checks()}

        # BLOCK: win probabilities do not sum to ~1
        if "prob_coherence" in failed:
            detail = next(c.detail for c in validation.checks if c.name == "prob_coherence")
            return (
                EnforcementAction.BLOCK,
                f"[BLOCKED] Incoherent win probabilities. {detail}",
            )

        # ESCALATE: debate agents disagree beyond threshold
        spread = self._agent_spread(output)
        if spread > self.disagreement_threshold:
            return (
                EnforcementAction.ESCALATE,
                (
                    f"[ESCALATED] Agent predictions diverge by {spread:.2f} "
                    f"(threshold {self.disagreement_threshold}). Human review required."
                ),
            )

        # REVISE: stat citations inconsistent with ground truth
        if "stat_consistency" in failed:
            detail = next(c.detail for c in validation.checks if c.name == "stat_consistency")
            return (
                EnforcementAction.REVISE,
                f"[REVISED] Stat citation inconsistency: {detail}. Treat output with caution.",
            )

        return (EnforcementAction.PASS, output)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _agent_spread(self, output: object) -> float:
        """Return max − min of home_win_prob across debate agents (0.0 for single-agent output)."""
        if not isinstance(output, dict) or "agent_analyses" not in output:
            return 0.0
        probs = []
        for analysis in output["agent_analyses"].values():
            if not isinstance(analysis, dict):
                continue
            pred = analysis.get("prediction", {})
            try:
                probs.append(float(pred.get("home_win_prob", 0)))
            except (TypeError, ValueError):
                pass
        if len(probs) < 2:
            return 0.0
        return max(probs) - min(probs)
