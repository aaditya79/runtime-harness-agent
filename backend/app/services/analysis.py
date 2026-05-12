"""Run the three reasoning systems and stream their stdout traces.

The Streamlit app captures the agents' ``print()`` output via
``contextlib.redirect_stdout`` to display a live trace. We wrap that with a
queue + background-thread pattern so the FastAPI layer can broadcast each
line to clients via Server-Sent Events.
"""

from __future__ import annotations

import contextlib
import json
import queue
import threading
import time
from datetime import datetime
from typing import Any, Iterable

import app.config  # noqa: F401 — path bootstrap

from nba_agent import run_agent  # type: ignore
from nba_multi_agent import run_full_debate, AGENTS  # type: ignore  # noqa: F401
from nba_cot_baseline import run_cot_analysis  # type: ignore

# Best-effort enrichment: we never let it break the existing response.
try:
    from app.services.factor_enrichment import enrich_report
    from app.services import data_tools as _data_tools
except Exception:  # pragma: no cover — defensive only
    enrich_report = None  # type: ignore[assignment]
    _data_tools = None  # type: ignore[assignment]


def _safe_enrich(report, home_abbr: str, away_abbr: str, home_name: str, away_name: str):
    """Add ``metric_label`` / ``metric_value`` / ``influence_score`` to factors.

    Always defensive: any exception leaves the report exactly as the agent
    produced it. The contract for callers — and for the existing Streamlit
    pages — is unchanged.
    """
    if enrich_report is None or _data_tools is None or not isinstance(report, dict):
        return report
    try:
        home_stats = _data_tools.get_team_stats(home_abbr) if home_abbr else {}
    except Exception:
        home_stats = {}
    try:
        away_stats = _data_tools.get_team_stats(away_abbr) if away_abbr else {}
    except Exception:
        away_stats = {}
    try:
        h2h = _data_tools.get_head_to_head(home_abbr, away_abbr) if home_abbr and away_abbr else {}
    except Exception:
        h2h = {}
    try:
        return enrich_report(report, home_stats=home_stats, away_stats=away_stats, h2h=h2h)
    except Exception:
        return report


# ---------------------------------------------------------------------------
# Trace writer + report parser
# ---------------------------------------------------------------------------

class _QueueWriter:
    """File-like object that pushes line chunks to a queue."""

    def __init__(self, q: "queue.Queue[dict]"):
        self._q = q
        self._buffer = ""
        self._capture: list[str] = []

    def write(self, text: str) -> int:
        if not text:
            return 0
        if isinstance(text, bytes):
            text = text.decode("utf-8", errors="ignore")
        self._capture.append(text)
        self._buffer += text
        while "\n" in self._buffer:
            line, _, rest = self._buffer.partition("\n")
            self._buffer = rest
            line = line.rstrip()
            if line:
                self._q.put({"event": "trace", "line": line})
        return len(text)

    def flush(self) -> None:
        if self._buffer.strip():
            line = self._buffer.strip()
            self._capture.append("\n")
            self._buffer = ""
            self._q.put({"event": "trace", "line": line})

    def captured(self) -> str:
        return "".join(self._capture)


def parse_report(raw: str) -> dict | None:
    """Pull the JSON object out of a model response."""
    if not raw:
        return None
    body = raw.split("FINAL REPORT:")[-1].strip() if "FINAL REPORT:" in raw else raw.strip()
    start = body.find("{")
    end = body.rfind("}") + 1
    if start < 0 or end <= start:
        return None
    try:
        return json.loads(body[start:end])
    except json.JSONDecodeError:
        return None


def extract_status(line: str, mode: str) -> str:
    """Map a stdout line to a friendly status pill (mirrors Streamlit logic)."""
    s = line.strip()
    if not s:
        return f"Running {mode}..."
    if "MODERATOR SYNTHESIS" in s:
        return "Synthesizing final report"
    if "DEBATE ROUND" in s:
        return s.title()
    if "PHASE 1: INDEPENDENT ANALYSIS" in s:
        return "Running independent agent analysis"
    if s.startswith("Step "):
        return s[:90]
    if s.startswith("Getting "):
        return s
    if "Running chain-of-thought analysis" in s:
        return "Running one-pass reasoning"
    if "FINAL REPORT" in s:
        return "Preparing final answer"
    return f"Running {mode}..."


# ---------------------------------------------------------------------------
# Mode runners
# ---------------------------------------------------------------------------

def _run_single_agent(game_description: str, llm_fn, **_kwargs) -> dict:
    result = run_agent(game_description, llm_fn)
    return {
        "raw": result.get("final_response", ""),
        "result": result,
    }


def _run_debate(game_description: str, llm_fn, num_debate_rounds: int = 2) -> dict:
    result = run_full_debate(game_description, llm_fn, num_debate_rounds=num_debate_rounds)
    return {
        "raw": result.get("final_report", ""),
        "result": result,
    }


def _run_cot(home_abbr: str, away_abbr: str, home_name: str, away_name: str,
             game_description: str, llm_fn, **_kwargs) -> dict:
    result = run_cot_analysis(home_abbr, away_abbr, home_name, away_name, game_description, llm_fn)
    return {
        "raw": result.get("response", ""),
        "result": result,
    }


# Mode keys used by the API — kebab/snake case for stable contracts.
MODE_RUNNERS: dict[str, Any] = {
    "single_agent": _run_single_agent,
    "multi_agent": _run_debate,
    "cot": _run_cot,
}


# ---------------------------------------------------------------------------
# Streaming runner
# ---------------------------------------------------------------------------

def stream_analysis(
    mode: str,
    game_description: str,
    home_abbr: str,
    away_abbr: str,
    home_name: str,
    away_name: str,
    llm_fn,
) -> Iterable[dict]:
    """Yield SSE-shaped events: trace lines, then a final ``done`` event."""
    if mode not in MODE_RUNNERS:
        yield {"event": "error", "message": f"Unknown mode: {mode}"}
        return

    q: "queue.Queue[dict]" = queue.Queue()
    container: dict[str, Any] = {}

    def runner():
        writer = _QueueWriter(q)
        try:
            with contextlib.redirect_stdout(writer):
                if mode == "single_agent":
                    container["payload"] = _run_single_agent(game_description, llm_fn)
                elif mode == "multi_agent":
                    container["payload"] = _run_debate(game_description, llm_fn)
                else:  # cot
                    container["payload"] = _run_cot(
                        home_abbr, away_abbr, home_name, away_name,
                        game_description, llm_fn,
                    )
            writer.flush()
            container["trace"] = writer.captured()
        except Exception as exc:  # surface tool / LLM errors to the client
            container["error"] = str(exc)
            writer.flush()
            container["trace"] = writer.captured()
        finally:
            q.put({"event": "__done__"})

    t = threading.Thread(target=runner, daemon=True)
    t.start()

    while True:
        try:
            item = q.get(timeout=120)
        except queue.Empty:
            yield {"event": "error", "message": "Analysis timed out (no output for 120s)"}
            return

        if item.get("event") == "__done__":
            break

        if item.get("event") == "trace":
            yield {
                "event": "trace",
                "line": item["line"],
                "status": extract_status(item["line"], mode),
            }

    if "error" in container:
        yield {"event": "error", "message": container["error"]}
        return

    payload = container.get("payload", {})
    raw = payload.get("raw", "")
    report = parse_report(raw)
    report = _safe_enrich(report, home_abbr, away_abbr, home_name, away_name)
    yield {
        "event": "done",
        "report": report,
        "raw": payload.get("result", {}),
        "trace": container.get("trace", ""),
        "mode": mode,
        "generated_at": datetime.utcnow().isoformat(),
    }


def run_analysis_blocking(
    mode: str,
    game_description: str,
    home_abbr: str,
    away_abbr: str,
    home_name: str,
    away_name: str,
    llm_fn,
) -> dict:
    """Synchronous variant — used by ``Compare All`` orchestration."""
    q: "queue.Queue[dict]" = queue.Queue()
    container: dict[str, Any] = {}
    writer = _QueueWriter(q)
    with contextlib.redirect_stdout(writer):
        if mode == "single_agent":
            payload = _run_single_agent(game_description, llm_fn)
        elif mode == "multi_agent":
            payload = _run_debate(game_description, llm_fn)
        else:
            payload = _run_cot(home_abbr, away_abbr, home_name, away_name, game_description, llm_fn)
    writer.flush()
    raw = payload.get("raw", "")
    report = parse_report(raw)
    report = _safe_enrich(report, home_abbr, away_abbr, home_name, away_name)
    return {
        "report": report,
        "raw": payload.get("result", {}),
        "trace": writer.captured(),
    }
