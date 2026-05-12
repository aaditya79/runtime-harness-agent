"""On-demand pipeline runners with background-job tracking.

Each pipeline is one of the existing repo-root scripts. We never modify
those scripts — we just spawn them as subprocesses, capture stdout in a
ring buffer, and expose status + output tails to the frontend.

The runner is single-flight per pipeline: if a job is already running for
that name, a second POST returns the running job instead of starting a
duplicate. Cooldowns apply to *successful* runs to keep external-API
quotas safe.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from collections import deque
from pathlib import Path
from typing import Optional

import app.config  # noqa: F401 — path bootstrap
from app.config import DATA_DIR, REPO_ROOT


# ---------------------------------------------------------------------------
# Pipeline catalog
# ---------------------------------------------------------------------------

class _Pipeline:
    def __init__(
        self,
        name: str,
        script: str,
        title: str,
        description: str,
        eta: str,
        produces: list[Path],
        cooldown_seconds: int = 60,
        timeout_seconds: int = 60 * 90,  # 90 min ceiling for the heaviest one
    ):
        self.name = name
        self.script = script
        self.title = title
        self.description = description
        self.eta = eta
        self.produces = produces
        self.cooldown_seconds = cooldown_seconds
        self.timeout_seconds = timeout_seconds


PIPELINES: dict[str, _Pipeline] = {
    "data": _Pipeline(
        name="data",
        script="nba_data_pipeline.py",
        title="Historical NBA data",
        description=(
            "Pulls game logs, team stats, standings, and head-to-head "
            "records from the nba_api. Required for every other pipeline."
        ),
        eta="~30–60 min",
        produces=[
            DATA_DIR / "game_logs.csv",
            DATA_DIR / "team_stats.csv",
            DATA_DIR / "standings.csv",
            DATA_DIR / "head_to_head.csv",
        ],
        cooldown_seconds=300,
        timeout_seconds=60 * 90,
    ),
    "injuries": _Pipeline(
        name="injuries",
        script="nba_injury_pipeline.py",
        title="Current injuries",
        description="Scrapes the latest injury reports.",
        eta="~1 min",
        produces=[DATA_DIR / "injuries.csv"],
        cooldown_seconds=60,
        timeout_seconds=60 * 5,
    ),
    "odds": _Pipeline(
        name="odds",
        script="nba_odds_pipeline.py",
        title="Live odds",
        description="Refreshes today's slate from The Odds API.",
        eta="~10 s",
        produces=[DATA_DIR / "odds_live.csv"],
        cooldown_seconds=60,
        timeout_seconds=60 * 3,
    ),
    "news": _Pipeline(
        name="news",
        script="nba_news_pipeline.py",
        title="News + sentiment",
        description="Pulls ESPN/CBS articles and computes per-team sentiment.",
        eta="~2–5 min",
        produces=[
            DATA_DIR / "news_articles.csv",
            DATA_DIR / "team_sentiment.csv",
        ],
        cooldown_seconds=60,
        timeout_seconds=60 * 15,
    ),
    "vector_store": _Pipeline(
        name="vector_store",
        script="nba_vector_store.py",
        title="ChromaDB vector store",
        description=(
            "Indexes every historical game into ChromaDB so the agents can "
            "retrieve similar matchups. Run after the data pipeline."
        ),
        eta="~5–15 min",
        produces=[REPO_ROOT / "chroma_db"],
        cooldown_seconds=60,
        timeout_seconds=60 * 30,
    ),
}


# ---------------------------------------------------------------------------
# Job state
# ---------------------------------------------------------------------------

class _Job:
    def __init__(self, pipeline: _Pipeline):
        self.pipeline = pipeline
        self.status: str = "idle"  # idle | running | done | error | timeout
        self.started_at: Optional[float] = None
        self.finished_at: Optional[float] = None
        self.last_run_at: Optional[float] = None
        self.exit_code: Optional[int] = None
        self.output: deque[str] = deque(maxlen=400)  # ring buffer of stdout lines
        self._proc: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()

    def is_running(self) -> bool:
        return self.status == "running"

    def cooldown_remaining(self) -> int:
        if self.last_run_at is None:
            return 0
        elapsed = time.time() - self.last_run_at
        remaining = self.pipeline.cooldown_seconds - elapsed
        return max(0, int(remaining))

    def to_status(self) -> dict:
        return {
            "name": self.pipeline.name,
            "title": self.pipeline.title,
            "description": self.pipeline.description,
            "eta": self.pipeline.eta,
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "last_run_at": self.last_run_at,
            "exit_code": self.exit_code,
            "duration_seconds": (
                int((self.finished_at or time.time()) - self.started_at)
                if self.started_at
                else None
            ),
            "cooldown_remaining": self.cooldown_remaining(),
            "produces": [str(p.relative_to(REPO_ROOT)) for p in self.pipeline.produces],
            "produces_present": [
                {
                    "path": str(p.relative_to(REPO_ROOT)),
                    "exists": p.exists(),
                }
                for p in self.pipeline.produces
            ],
            "output_tail": list(self.output),
        }


_JOBS: dict[str, _Job] = {name: _Job(pl) for name, pl in PIPELINES.items()}


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def _run_subprocess(job: _Job) -> None:
    """Drive a pipeline subprocess to completion in the background thread."""
    pl = job.pipeline
    job.status = "running"
    job.started_at = time.time()
    job.finished_at = None
    job.exit_code = None
    job.output.clear()
    job.output.append(f"$ python3 {pl.script}")

    try:
        # Force unbuffered output so we get lines as they happen.
        env = os.environ.copy()
        env.setdefault("PYTHONUNBUFFERED", "1")
        proc = subprocess.Popen(
            [sys.executable, "-u", pl.script],
            cwd=str(REPO_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
            bufsize=1,
        )
        job._proc = proc

        deadline = time.time() + pl.timeout_seconds
        assert proc.stdout is not None
        for line in proc.stdout:
            job.output.append(line.rstrip())
            if time.time() > deadline:
                proc.kill()
                job.output.append(f"[timeout after {pl.timeout_seconds}s]")
                break

        proc.wait()
        job.exit_code = proc.returncode
        job.status = "done" if proc.returncode == 0 else "error"
    except Exception as exc:  # surface subprocess.Popen failures
        job.output.append(f"[runner error] {exc}")
        job.status = "error"
        job.exit_code = -1
    finally:
        job.finished_at = time.time()
        job.last_run_at = job.finished_at
        job._proc = None


def start_pipeline(name: str) -> dict:
    """Kick off a pipeline run. Returns a status dict."""
    pl = PIPELINES.get(name)
    if pl is None:
        return {"ok": False, "error": f"Unknown pipeline: {name}"}

    job = _JOBS[name]
    with job._lock:
        if job.is_running():
            return {
                "ok": False,
                "error": "Already running",
                "status": job.to_status(),
            }
        cooldown = job.cooldown_remaining()
        if cooldown > 0:
            return {
                "ok": False,
                "error": f"Cooldown active ({cooldown}s left)",
                "rate_limited": True,
                "cooldown_remaining": cooldown,
                "status": job.to_status(),
            }
        thread = threading.Thread(target=_run_subprocess, args=(job,), daemon=True)
        thread.start()

    return {"ok": True, "status": job.to_status()}


def get_status(name: Optional[str] = None) -> dict:
    """Return either one pipeline's status or all pipelines' statuses."""
    if name:
        job = _JOBS.get(name)
        if job is None:
            return {"error": f"Unknown pipeline: {name}"}
        return job.to_status()
    return {n: j.to_status() for n, j in _JOBS.items()}
