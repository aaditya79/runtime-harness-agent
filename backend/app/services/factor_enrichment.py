"""Factor-card enrichment.

Pure, additive post-processor: takes the parsed report dict produced by the
existing agent prompts and decorates each ``key_factor`` with three optional
fields the React UI uses to render a richer KPI card —

    - ``influence_score``  (int, 0..100)   derived from the importance bucket
    - ``metric_label``     (str)           short label for a quantitative anchor
    - ``metric_value``     (str)           formatted value for that anchor

The agent prompts in ``nba_agent.py`` / ``nba_multi_agent.py`` /
``nba_cot_baseline.py`` are NOT modified. None of the existing consumers
(Streamlit pages, backtest harness) read these new fields, so adding them
is safe — old reports keep flowing through their existing renderers.

Every entry point here is wrapped in ``try/except`` and returns the input
unchanged on any failure, so the analysis pipeline never breaks because of
enrichment.
"""

from __future__ import annotations

import math
import re
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Influence score
# ---------------------------------------------------------------------------

_IMPORTANCE_TO_SCORE = {
    "high": 88,
    "medium": 62,
    "low": 35,
}


def _influence_score(importance: Any) -> int:
    """Map ``high`` / ``medium`` / ``low`` to a 0..100 score."""
    if isinstance(importance, (int, float)) and not math.isnan(float(importance)):
        return max(0, min(100, int(importance)))
    return _IMPORTANCE_TO_SCORE.get(str(importance or "medium").strip().lower(), 60)


# ---------------------------------------------------------------------------
# Category detection
# ---------------------------------------------------------------------------
# Each category is a tuple of (keywords, category_id). The first match wins,
# so order matters — longer / more specific keywords come first.

# A keyword can be a plain substring or a regex pattern (when prefixed with
# ``re:``). Short three-letter tokens like ``ast`` / ``tov`` would falsely
# match longer words (``last``, ``stove``), so they use word boundaries.
# Order matters — the first matching rule wins, so the more specific
# keywords come first. "Net Rating Last 10" must hit ``net_rating`` before
# the generic ``last 10`` rule, etc.
_CATEGORY_RULES: list[tuple[list[str], str]] = [
    (["head-to-head", "head to head", "re:\\bh2h\\b", "historical series"], "h2h"),
    (["net rating", "plus/minus", "plus minus", "+/-", "point differential", "scoring margin"], "net_rating"),
    (["offensive efficiency", "off. rating", "offensive rating", "offensive output", "scoring output"], "offensive_efficiency"),
    (["defensive efficiency", "def. rating", "defensive rating"], "defensive_efficiency"),
    (["shooting efficiency", "field goal", "fg%", "fg pct", "shooting"], "fg_pct"),
    (["three-point", "three point", "3-point", "3pt", "re:\\bfg3\\b"], "three_pct"),
    (["assist rate", "assist gap", "assist", "re:\\bast\\b"], "assists"),
    (["rebound", "re:\\breb\\b"], "rebounds"),
    (["turnover", "re:\\btov\\b"], "turnovers"),
    (["pace"], "pace"),
    (["season record", "season strength", "win pct", "win percentage", "overall record"], "season_record"),
    (["home court", "home advantage", "home venue"], "home_court"),
    (["back-to-back", "back to back", "re:\\bb2b\\b", "rest status", "rest day", "rest advantage", "schedule"], "rest"),
    (["sentiment", "media coverage", "narrative"], "sentiment"),
    (["injuries", "availability", "player health", "absence"], "injuries"),
    (["odds", "market", "implied", "bookmaker"], "market"),
    # Generic catch-all for "last 10 record" / "recent form" without other tokens.
    (["last 10", "recent form", "recent record"], "last_10"),
]


def _kw_match(kw: str, lower: str) -> bool:
    if kw.startswith("re:"):
        return re.search(kw[3:], lower) is not None
    return kw in lower


def _classify(text: str) -> Optional[str]:
    if not text:
        return None
    lower = text.lower()
    for keywords, cat in _CATEGORY_RULES:
        for kw in keywords:
            if _kw_match(kw, lower):
                return cat
    return None


# ---------------------------------------------------------------------------
# Stat helpers
# ---------------------------------------------------------------------------

def _parse_record_pct(record: Any) -> Optional[float]:
    """Convert an "X-Y" string to a win percentage in [0, 1]."""
    if not isinstance(record, str):
        return None
    match = re.match(r"\s*(\d+)\s*[-–]\s*(\d+)\s*", record)
    if not match:
        return None
    wins, losses = int(match.group(1)), int(match.group(2))
    total = wins + losses
    if total == 0:
        return None
    return wins / total


def _safe_num(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(f):
        return None
    return f


# ---------------------------------------------------------------------------
# Per-category metric builders
# ---------------------------------------------------------------------------

def _metric_for(
    category: str,
    impact: str,
    home_stats: dict,
    away_stats: dict,
    h2h: dict,
) -> Optional[tuple[str, str]]:
    """Return ``(label, value)`` for a category, or None if data is missing."""

    def _diff(home_val: Optional[float], away_val: Optional[float]) -> Optional[float]:
        if home_val is None or away_val is None:
            return None
        return home_val - away_val

    if category == "season_record":
        h = _parse_record_pct(home_stats.get("season_record"))
        a = _parse_record_pct(away_stats.get("season_record"))
        diff = _diff(h, a)
        if diff is None:
            return None
        return ("Win % edge", f"{diff * 100:+.1f} pp")

    if category == "last_10":
        h_rec = home_stats.get("last_10_record")
        a_rec = away_stats.get("last_10_record")
        if h_rec and a_rec:
            return ("Last 10", f"{h_rec} vs {a_rec}")

    if category == "net_rating":
        diff = _diff(
            _safe_num(home_stats.get("avg_plus_minus_last_10")),
            _safe_num(away_stats.get("avg_plus_minus_last_10")),
        )
        if diff is not None:
            return ("Net rating Δ", f"{diff:+.1f}")

    if category == "offensive_efficiency":
        diff = _diff(
            _safe_num(home_stats.get("avg_points_last_10")),
            _safe_num(away_stats.get("avg_points_last_10")),
        )
        if diff is not None:
            return ("PPG edge", f"{diff:+.1f}")

    if category == "fg_pct":
        h = _safe_num(home_stats.get("avg_fg_pct_last_10"))
        a = _safe_num(away_stats.get("avg_fg_pct_last_10"))
        diff = _diff(h, a)
        if diff is not None:
            return ("FG% Δ", f"{diff * 100:+.1f}%")

    if category == "three_pct":
        h = _safe_num(home_stats.get("avg_fg3_pct_last_10"))
        a = _safe_num(away_stats.get("avg_fg3_pct_last_10"))
        diff = _diff(h, a)
        if diff is not None:
            return ("3P% Δ", f"{diff * 100:+.1f}%")

    if category == "assists":
        diff = _diff(
            _safe_num(home_stats.get("avg_assists_last_10")),
            _safe_num(away_stats.get("avg_assists_last_10")),
        )
        if diff is not None:
            return ("Assist Δ", f"{diff:+.1f}/g")

    if category == "rebounds":
        diff = _diff(
            _safe_num(home_stats.get("avg_rebounds_last_10")),
            _safe_num(away_stats.get("avg_rebounds_last_10")),
        )
        if diff is not None:
            return ("Rebound Δ", f"{diff:+.1f}/g")

    if category == "turnovers":
        # Lower TO is better — invert sign so positive favors home.
        diff = _diff(
            _safe_num(away_stats.get("avg_turnovers_last_10")),
            _safe_num(home_stats.get("avg_turnovers_last_10")),
        )
        if diff is not None:
            return ("TO advantage", f"{diff:+.1f}/g")

    if category == "h2h":
        overall = (h2h or {}).get("overall") if isinstance(h2h, dict) else None
        if isinstance(overall, dict):
            wins = overall.get("total_wins")
            losses = overall.get("total_losses")
            pct = overall.get("overall_win_pct")
            if isinstance(wins, int) and isinstance(losses, int):
                pct_str = f" ({float(pct) * 100:.0f}%)" if isinstance(pct, (int, float)) else ""
                return ("H2H record", f"{wins}-{losses}{pct_str}")

    if category == "home_court":
        # Static league-wide prior — every analyst uses ~+2.5 to +3.5 pts.
        return ("Home edge", "+3.0 pts")

    if category == "rest":
        h_b2b = _safe_num(home_stats.get("back_to_back_today")) == 1.0
        a_b2b = _safe_num(away_stats.get("back_to_back_today")) == 1.0
        if h_b2b and not a_b2b:
            return ("Rest", "Home on B2B")
        if a_b2b and not h_b2b:
            return ("Rest", "Away on B2B")
        return ("Rest", "Both rested")

    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def enrich_factors(
    factors: list[dict],
    home_stats: Optional[dict] = None,
    away_stats: Optional[dict] = None,
    h2h: Optional[dict] = None,
) -> list[dict]:
    """Return a new list of factors with optional enrichment fields added.

    Original factor dicts are never mutated. If anything goes wrong for a
    given factor the original dict is preserved and we move on.
    """
    if not isinstance(factors, list):
        return factors

    home_stats = home_stats if isinstance(home_stats, dict) else {}
    away_stats = away_stats if isinstance(away_stats, dict) else {}
    h2h = h2h if isinstance(h2h, dict) else {}

    out: list[dict] = []
    for raw in factors:
        if not isinstance(raw, dict):
            out.append(raw)
            continue

        try:
            f = dict(raw)  # shallow copy — never mutate caller's dict
            text = str(f.get("factor", "") or "")
            impact = str(f.get("impact", "") or "")
            f.setdefault("influence_score", _influence_score(f.get("importance")))

            category = _classify(text)
            if category and "metric_value" not in f:
                metric = _metric_for(category, impact, home_stats, away_stats, h2h)
                if metric is not None:
                    f["metric_label"], f["metric_value"] = metric
                    f["category"] = category

            out.append(f)
        except Exception:  # never let one bad factor break the response
            out.append(raw)

    return out


def enrich_report(
    report: Optional[dict],
    home_stats: Optional[dict] = None,
    away_stats: Optional[dict] = None,
    h2h: Optional[dict] = None,
) -> Optional[dict]:
    """Return ``report`` with ``key_factors`` enriched. None-safe."""
    if not isinstance(report, dict):
        return report
    try:
        factors = report.get("key_factors")
        if isinstance(factors, list) and factors:
            enriched = enrich_factors(factors, home_stats, away_stats, h2h)
            new_report = dict(report)
            new_report["key_factors"] = enriched
            return new_report
        return report
    except Exception:
        return report
