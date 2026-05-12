import json
import re
from typing import Any

from .models import ValidationCheck, ValidationResult


class Validator:
    PROB_TOLERANCE = 0.02
    STAT_TOLERANCE = 0.15

    def __init__(
        self,
        prob_tolerance: float = PROB_TOLERANCE,
        stat_tolerance: float = STAT_TOLERANCE,
    ):
        self.prob_tolerance = prob_tolerance
        self.stat_tolerance = stat_tolerance

    def validate(self, output: Any, ground_truth: dict | None = None) -> ValidationResult:
        checks = [
            self._check_prob_coherence(output),
            self._check_stat_consistency(output, ground_truth or {}),
        ]
        return ValidationResult(passed=all(c.passed for c in checks), checks=checks)

    # ------------------------------------------------------------------
    # Probability coherence
    # ------------------------------------------------------------------

    def _extract_prediction(self, output: Any) -> dict | None:
        """Pull the final {home_win_prob, away_win_prob} dict from any output shape."""
        if isinstance(output, dict):
            if "final_report" in output:
                return self._parse_probs_from_text(output["final_report"])
            if "home_win_prob" in output and "away_win_prob" in output:
                return output
            if "final_response" in output:
                return self._parse_probs_from_text(output["final_response"])
        if isinstance(output, str):
            return self._parse_probs_from_text(output)
        return None

    def _parse_probs_from_text(self, text: str) -> dict | None:
        """Extract win probabilities from a report string (JSON block or regex fallback)."""
        for marker in ("FINAL REPORT:", "ANALYSIS:"):
            if marker not in text:
                continue
            try:
                blob = text.split(marker)[-1].strip()
                start, end = blob.find("{"), blob.rfind("}") + 1
                if start >= 0 and end > start:
                    data = json.loads(blob[start:end])
                    pred = (
                        data.get("synthesized_prediction")
                        or data.get("agent_prediction")
                        or data.get("prediction")
                    )
                    if pred:
                        return pred
            except (json.JSONDecodeError, ValueError):
                pass
        # Regex fallback for loosely-formatted output
        home = re.search(r'"home_win_prob"\s*:\s*([0-9.]+)', text)
        away = re.search(r'"away_win_prob"\s*:\s*([0-9.]+)', text)
        if home and away:
            return {
                "home_win_prob": float(home.group(1)),
                "away_win_prob": float(away.group(1)),
            }
        return None

    def _check_prob_coherence(self, output: Any) -> ValidationCheck:
        pred = self._extract_prediction(output)
        if pred is None:
            return ValidationCheck(
                name="prob_coherence",
                passed=False,
                detail="Could not extract win probabilities from output.",
            )
        try:
            h = float(pred.get("home_win_prob", 0))
            a = float(pred.get("away_win_prob", 0))
        except (TypeError, ValueError):
            return ValidationCheck(
                name="prob_coherence",
                passed=False,
                detail=f"Non-numeric probability values: {pred}",
            )
        total = h + a
        ok = abs(total - 1.0) <= self.prob_tolerance
        return ValidationCheck(
            name="prob_coherence",
            passed=ok,
            detail=(
                f"home={h:.3f} away={a:.3f} sum={total:.4f} "
                f"(tolerance ±{self.prob_tolerance})"
            ),
        )

    # ------------------------------------------------------------------
    # Stat citation consistency
    # ------------------------------------------------------------------

    def _check_stat_consistency(self, output: Any, ground_truth: dict) -> ValidationCheck:
        if not ground_truth:
            return ValidationCheck(
                name="stat_consistency",
                passed=True,
                detail="No ground truth provided; stat check skipped.",
            )
        text = output if isinstance(output, str) else json.dumps(output, default=str)
        violations = []
        for stat_key, expected in ground_truth.items():
            if not isinstance(expected, (int, float)):
                continue
            pattern = re.compile(
                re.escape(str(stat_key)) + r"[^0-9\-\.]*([0-9]+(?:\.[0-9]+)?)",
                re.IGNORECASE,
            )
            for m in pattern.finditer(text):
                cited = float(m.group(1))
                rel_err = abs(cited - expected) / abs(expected) if expected != 0 else abs(cited)
                if rel_err > self.stat_tolerance:
                    violations.append(
                        f"{stat_key}: expected {expected}, cited {cited:.3f} "
                        f"(err {rel_err:.1%})"
                    )
        if violations:
            return ValidationCheck(
                name="stat_consistency",
                passed=False,
                detail="; ".join(violations),
            )
        return ValidationCheck(
            name="stat_consistency",
            passed=True,
            detail=f"Checked {len(ground_truth)} ground-truth keys; no violations found.",
        )
