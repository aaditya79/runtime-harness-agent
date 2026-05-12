"""Backtest CSV loaders + ROI simulator + async job runner.

Reads the artifacts produced by ``nba_backtest.py``:
    data/backtest_summary.csv
    data/backtest_predictions.csv
    data/backtest_calibration.csv
    data/backtest_run_metadata.json
    data/backtest_ablation_*_summary.csv

Also runs ``nba_backtest.py`` as a subprocess. The runner is non-blocking:
each stdout line is mirrored to the FastAPI process's terminal AND fanned
out to subscribers (used by the SSE stream + the polling status endpoint).

Caching: the script itself memoises per-(game, method) under
``data/backtest_cache/``, so re-running with the same parameters skips
games that already have cached predictions. The job runner is also
single-flight — concurrent ``POST /api/backtest/run`` calls return the
running job instead of starting a duplicate.
"""

from __future__ import annotations

import glob
import json
import math
import os
import queue
import subprocess
import sys
import threading
import time
from collections import deque
from pathlib import Path
from typing import Generator, Optional

import numpy as np
import pandas as pd

import app.config  # noqa: F401 — path bootstrap
from app.config import DATA_DIR, REPO_ROOT


SUMMARY_PATH = DATA_DIR / "backtest_summary.csv"
PRED_PATH = DATA_DIR / "backtest_predictions.csv"
CAL_PATH = DATA_DIR / "backtest_calibration.csv"
META_PATH = DATA_DIR / "backtest_run_metadata.json"


METHOD_DISPLAY = {
    "single_agent": "Single Agent",
    "chain_of_thought": "Chain-of-Thought",
    "multi_agent_debate": "Multi-Agent Debate",
}


def _df_to_records(df: pd.DataFrame) -> list[dict]:
    """Pandas -> JSON-safe list[dict] (drops NaN, stringifies datetimes)."""
    if df.empty:
        return []
    cleaned = df.copy()
    for col in cleaned.columns:
        if pd.api.types.is_datetime64_any_dtype(cleaned[col]):
            cleaned[col] = cleaned[col].astype(str)
    records = cleaned.where(pd.notnull(cleaned), None).to_dict(orient="records")
    # numpy scalars -> python primitives for JSON
    for rec in records:
        for k, v in list(rec.items()):
            if isinstance(v, (np.integer,)):
                rec[k] = int(v)
            elif isinstance(v, (np.floating,)):
                rec[k] = None if math.isnan(float(v)) else float(v)
            elif isinstance(v, (np.bool_,)):
                rec[k] = bool(v)
    return records


def load_summary() -> list[dict]:
    if not SUMMARY_PATH.exists():
        return []
    return _df_to_records(pd.read_csv(SUMMARY_PATH))


def load_predictions() -> list[dict]:
    if not PRED_PATH.exists():
        return []
    return _df_to_records(pd.read_csv(PRED_PATH))


def load_calibration() -> list[dict]:
    if not CAL_PATH.exists():
        return []
    return _df_to_records(pd.read_csv(CAL_PATH))


def load_metadata() -> dict:
    if not META_PATH.exists():
        return {}
    try:
        return json.loads(META_PATH.read_text())
    except Exception:
        return {}


def load_ablations() -> list[dict]:
    files = glob.glob(str(DATA_DIR / "backtest_ablation_*_summary.csv"))
    if not files or not SUMMARY_PATH.exists():
        return []
    base_df = pd.read_csv(SUMMARY_PATH)
    base_cot = base_df[base_df["method"] == "chain_of_thought"]
    if base_cot.empty:
        return []
    baseline_brier = float(base_cot["brier_score"].iloc[0])

    rows: list[dict] = []
    for fpath in sorted(files):
        path = Path(fpath)
        source = path.name.replace("backtest_ablation_", "").replace("_summary.csv", "")
        df = pd.read_csv(path)
        cot_row = df[df["method"] == "chain_of_thought"]
        if cot_row.empty:
            continue
        ablation_brier = float(cot_row["brier_score"].iloc[0])
        rows.append({
            "source": source,
            "ablation_brier": round(ablation_brier, 4),
            "baseline_brier": round(baseline_brier, 4),
            "brier_delta": round(ablation_brier - baseline_brier, 4),
            "n_games": int(cot_row["n_games"].iloc[0]),
        })
    rows.sort(key=lambda r: r["brier_delta"], reverse=True)
    return rows


# ---------------------------------------------------------------------------
# ROI simulator
# ---------------------------------------------------------------------------

def _safe_prob(value) -> float:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return float("nan")
    return min(max(x, 1e-6), 1 - 1e-6)


def simulate_roi(
    method: str = "All",
    edge_threshold: float = 0.05,
    side_filter: str = "Both",
    min_confidence: float = 0.50,
) -> dict:
    """Run a flat-stake simulation against backtest predictions.

    Returns a dict with ``available``, ``reason`` (machine-readable code),
    ``message`` (human guidance), ``diagnostics`` (counts the UI uses to
    point at the right fix), plus the usual ``summary`` and ``bets`` rows.
    """

    def _empty(reason: str, message: str, diagnostics: Optional[dict] = None) -> dict:
        return {
            "summary": [],
            "bets": [],
            "available": False,
            "reason": reason,
            "message": message,
            "diagnostics": diagnostics or {},
        }

    if not PRED_PATH.exists():
        return _empty(
            "predictions_missing",
            "No backtest predictions on disk yet. Open the Research page and run a backtest first.",
        )

    df = pd.read_csv(PRED_PATH)
    if df.empty:
        return _empty(
            "predictions_empty",
            "data/backtest_predictions.csv exists but is empty. Re-run the backtest.",
        )

    has_market_cols = (
        "market_home_implied_prob" in df.columns
        and "market_away_implied_prob" in df.columns
    )
    if not has_market_cols:
        return _empty(
            "market_columns_missing",
            "Backtest predictions don't include market columns yet. "
            "Re-run the backtest after pulling the latest nba_backtest.py.",
            {"row_count": int(len(df))},
        )

    market_rows = (
        df["market_home_implied_prob"].notna() & df["market_away_implied_prob"].notna()
    ).sum()
    if market_rows == 0:
        return _empty(
            "market_data_missing",
            "Predictions have market columns but every row is null. "
            "data/odds_historical.csv was not produced when nba_backtest.py ran. "
            "To populate it: download the Kaggle dataset "
            "(kaggle.com/datasets/erichqiu/nba-odds-and-scores) to "
            "data/kaggle_odds.csv, run the Odds pipeline, then re-run the backtest.",
            {
                "row_count": int(len(df)),
                "rows_with_market_data": 0,
                "missing_file": "data/odds_historical.csv",
                "manual_step": "data/kaggle_odds.csv",
            },
        )

    if method != "All":
        df = df[df["method"] == method].copy()
    if df.empty:
        return _empty(
            "no_rows_after_method_filter",
            f"No predictions in the file for method = {method}.",
            {"row_count": 0},
        )

    sim_rows: list[dict] = []
    for _, row in df.iterrows():
        home_prob = _safe_prob(row.get("home_win_prob"))
        away_prob = _safe_prob(row.get("away_win_prob"))
        market_home = _safe_prob(row.get("market_home_implied_prob"))
        market_away = _safe_prob(row.get("market_away_implied_prob"))
        if any(math.isnan(x) for x in [home_prob, away_prob, market_home, market_away]):
            continue
        confidence = max(home_prob, away_prob)
        if confidence < min_confidence:
            continue

        home_edge = home_prob - market_home
        away_edge = away_prob - market_away
        chosen_side = chosen_edge = chosen_market_prob = None
        won = None

        if side_filter in ("Both", "Home Only") and home_edge >= edge_threshold:
            chosen_side = "Home"
            chosen_edge = home_edge
            chosen_market_prob = market_home
            won = int(row["actual_home_win"]) == 1
        if side_filter in ("Both", "Away Only") and away_edge >= edge_threshold:
            if chosen_side is None or away_edge > chosen_edge:
                chosen_side = "Away"
                chosen_edge = away_edge
                chosen_market_prob = market_away
                won = int(row["actual_home_win"]) == 0

        if chosen_side is None:
            continue

        decimal_odds = 1.0 / chosen_market_prob
        units = (decimal_odds - 1.0) if won else -1.0

        sim_rows.append({
            "date": str(row.get("date")),
            "season": row.get("season", ""),
            "game_id": row.get("game_id", ""),
            "away_team": row.get("away_team"),
            "home_team": row.get("home_team"),
            "method": row.get("method"),
            "side_bet": chosen_side,
            "edge": round(float(chosen_edge), 4),
            "model_home_prob": round(float(home_prob), 4),
            "model_away_prob": round(float(away_prob), 4),
            "market_home_implied_prob": round(float(market_home), 4),
            "market_away_implied_prob": round(float(market_away), 4),
            "model_confidence": round(float(confidence), 4),
            "won": int(bool(won)),
            "units": round(float(units), 4),
        })

    if not sim_rows:
        return {
            "summary": [],
            "bets": [],
            "available": True,
            "reason": "no_qualifying_bets",
            "message": (
                "No bets passed the current filters. Try lowering the edge "
                "threshold, dropping the minimum confidence, or switching to "
                "'Both' for the side filter."
            ),
            "diagnostics": {
                "rows_evaluated": int(len(df)),
                "rows_with_market_data": int(market_rows),
                "edge_threshold": edge_threshold,
                "min_confidence": min_confidence,
                "side_filter": side_filter,
            },
        }

    bets_df = pd.DataFrame(sim_rows)
    bets_df["date"] = pd.to_datetime(bets_df["date"], errors="coerce")
    bets_df = bets_df.sort_values(["method", "date", "game_id"]).reset_index(drop=True)
    bets_df["cum_units"] = bets_df.groupby("method")["units"].cumsum()
    bets_df["date"] = bets_df["date"].astype(str)

    summary_df = (
        bets_df.groupby("method")
        .agg(
            n_bets=("units", "count"),
            win_rate=("won", "mean"),
            total_units=("units", "sum"),
            avg_units_per_bet=("units", "mean"),
            avg_edge=("edge", "mean"),
            avg_model_confidence=("model_confidence", "mean"),
        )
        .reset_index()
    )
    summary_df["roi"] = summary_df["total_units"] / summary_df["n_bets"]

    return {
        "summary": _df_to_records(summary_df),
        "bets": _df_to_records(bets_df),
        "available": True,
        "reason": "ok",
        "message": "",
        "diagnostics": {
            "rows_evaluated": int(len(df)),
            "rows_with_market_data": int(market_rows),
            "qualifying_bets": int(len(sim_rows)),
        },
    }


# ---------------------------------------------------------------------------
# Async backtest job runner
# ---------------------------------------------------------------------------
#
# Goals:
#   * Caching — the script's own per-(game, method) cache under
#     ``data/backtest_cache/`` makes re-runs cheap. We add a single-flight
#     guard at the API layer so concurrent POSTs reuse the running job.
#   * Terminal logs — each subprocess line is tee'd to ``sys.stdout`` so
#     the dev running ``uvicorn`` sees real-time progress in their terminal.
#   * In-app streaming — every line is also pushed onto a ring buffer (for
#     the polling endpoint) and fanned out to live SSE subscribers.

# Sentinel values written to the broadcast queue.
_DONE = object()


class _BacktestJob:
    """Mutable, in-memory state for a single backtest run."""

    def __init__(self) -> None:
        self.status: str = "idle"  # idle | running | done | error | timeout
        self.params: Optional[dict] = None
        self.started_at: Optional[float] = None
        self.finished_at: Optional[float] = None
        self.exit_code: Optional[int] = None
        self.output: deque[str] = deque(maxlen=2000)
        self._proc: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()
        # Live SSE subscribers — one queue per connected client.
        self._subscribers: list["queue.Queue[object]"] = []
        self._subscribers_lock = threading.Lock()

    def is_running(self) -> bool:
        return self.status == "running"

    def to_status(self) -> dict:
        duration = None
        if self.started_at is not None:
            end = self.finished_at if self.finished_at is not None else time.time()
            duration = int(end - self.started_at)
        return {
            "status": self.status,
            "params": self.params,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_seconds": duration,
            "exit_code": self.exit_code,
            "output_tail": list(self.output),
        }

    def _broadcast(self, item: object) -> None:
        with self._subscribers_lock:
            for sub in list(self._subscribers):
                try:
                    sub.put_nowait(item)
                except queue.Full:
                    pass

    def subscribe(self) -> "queue.Queue[object]":
        q: "queue.Queue[object]" = queue.Queue(maxsize=1024)
        with self._subscribers_lock:
            self._subscribers.append(q)
        return q

    def unsubscribe(self, q: "queue.Queue[object]") -> None:
        with self._subscribers_lock:
            try:
                self._subscribers.remove(q)
            except ValueError:
                pass


_JOB = _BacktestJob()


def get_job_status() -> dict:
    return _JOB.to_status()


def _run_backtest_subprocess(n_games: int, season: str, min_history: int) -> None:
    """Drive ``nba_backtest.py`` to completion, tee'ing stdout."""
    job = _JOB
    cmd = [
        sys.executable,
        "-u",  # unbuffered child output → we get lines as they happen
        "nba_backtest.py",
        "--n-games", str(n_games),
        "--min-games-history", str(min_history),
    ]
    if season and season != "All":
        cmd.extend(["--season", season])

    banner = f"$ {' '.join(cmd)}"
    job.output.append(banner)
    job._broadcast(banner)
    sys.stdout.write(banner + "\n")
    sys.stdout.flush()

    try:
        env = os.environ.copy()
        env.setdefault("PYTHONUNBUFFERED", "1")
        proc = subprocess.Popen(
            cmd,
            cwd=str(REPO_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
            bufsize=1,
        )
        job._proc = proc

        assert proc.stdout is not None
        for line in proc.stdout:
            clean = line.rstrip()
            if not clean:
                continue
            job.output.append(clean)
            job._broadcast(clean)
            # Mirror to uvicorn's terminal so devs see live progress.
            sys.stdout.write(line)
            sys.stdout.flush()

        proc.wait()
        job.exit_code = proc.returncode
        job.status = "done" if proc.returncode == 0 else "error"
    except Exception as exc:  # surface launch / pipe failures
        msg = f"[runner error] {exc}"
        job.output.append(msg)
        job._broadcast(msg)
        sys.stdout.write(msg + "\n")
        sys.stdout.flush()
        job.status = "error"
        job.exit_code = -1
    finally:
        job.finished_at = time.time()
        job._proc = None
        job._broadcast(_DONE)


def start_backtest(n_games: int, season: str, min_history: int) -> dict:
    """Kick off a backtest in the background. Idempotent: returns the
    running job if one is already in flight.
    """
    job = _JOB
    with job._lock:
        if job.is_running():
            return {
                "ok": False,
                "error": "Backtest already running",
                "status": job.to_status(),
            }
        job.status = "running"
        job.params = {
            "n_games": int(n_games),
            "season": season,
            "min_history": int(min_history),
        }
        job.started_at = time.time()
        job.finished_at = None
        job.exit_code = None
        job.output.clear()
        thread = threading.Thread(
            target=_run_backtest_subprocess,
            args=(n_games, season, min_history),
            daemon=True,
            name="backtest-runner",
        )
        thread.start()

    return {"ok": True, "status": job.to_status()}


def stream_lines() -> Generator[dict, None, None]:
    """Yield SSE events: replay the buffer, then live-stream until done."""
    job = _JOB

    # Snapshot what's already in the ring buffer so a late-joining client
    # gets context.
    yield {"event": "snapshot", "data": json.dumps(job.to_status())}

    sub = job.subscribe()
    try:
        # If the job isn't running, we still emitted the snapshot — close out.
        if not job.is_running():
            yield {"event": "done", "data": json.dumps(job.to_status())}
            return

        while True:
            try:
                item = sub.get(timeout=300)
            except queue.Empty:
                # 5-minute idle without output → assume hang / disconnect.
                yield {"event": "done", "data": json.dumps(job.to_status())}
                return

            if item is _DONE:
                yield {"event": "done", "data": json.dumps(job.to_status())}
                return

            yield {"event": "line", "data": str(item)}
    finally:
        job.unsubscribe(sub)


# Back-compat: the previous synchronous helper still exists so any caller
# that wants a one-shot blocking run can keep using it. Not used by the
# default API any more.
def run_backtest(n_games: int, season: str, min_history: int) -> tuple[bool, str]:
    """Spawn ``nba_backtest.py`` synchronously. Legacy / test helper."""
    cmd = [
        sys.executable,
        "nba_backtest.py",
        "--n-games", str(n_games),
        "--min-games-history", str(min_history),
    ]
    if season and season != "All":
        cmd.extend(["--season", season])

    proc = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True)
    return proc.returncode == 0, (proc.stdout or "") + (proc.stderr or "")
