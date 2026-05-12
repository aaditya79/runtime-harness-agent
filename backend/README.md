# MatchOdds AI · Backend

FastAPI backend that wraps the existing Streamlit-era Python modules (`nba_agent.py`, `nba_multi_agent.py`, `nba_cot_baseline.py`, the data pipelines, vector store, cost logger). The backend does **not** modify any of those files — it imports them, captures their `print()` traces, and exposes the results over a clean REST + SSE interface.

## Layout

```
backend/
├── app/
│   ├── main.py              # FastAPI factory
│   ├── config.py            # path bootstrap + .env loading
│   ├── teams.py             # team / abbreviation / logo metadata
│   ├── routers/             # HTTP routes
│   │   ├── meta.py          # /api/meta/health, /api/meta/teams
│   │   ├── games.py         # upcoming, team-stats, injuries, sentiment, odds, similar
│   │   ├── analysis.py      # /api/analysis/stream (SSE) + /api/analysis/run
│   │   └── backtest.py      # backtest summary / predictions / calibration / ablations / simulate
│   └── services/
│       ├── llm.py           # picks Anthropic, falls back to OpenAI
│       ├── data_tools.py    # JSON-decoded wrappers around nba_agent tool functions
│       ├── games.py         # upcoming-games loader, market consensus, similar games
│       ├── analysis.py      # stdout capture, SSE event generator, report parser
│       └── backtest.py      # CSV loaders + ROI simulator + subprocess runner
├── requirements.txt
└── run.sh                   # dev launcher
```

## Setup

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

The backend reads its API keys from the **repo root** `.env` (already used by the Streamlit app). At minimum set one of:

```
ANTHROPIC_API_KEY=...
# or
OPENAI_API_KEY=...
```

The data pipelines (CSVs in `data/` and the ChromaDB store) must be populated by running the existing pipeline scripts at the repo root, exactly as documented in the project README.

## Run

```bash
./run.sh
# or:
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

OpenAPI docs live at `http://localhost:8000/docs`.

## Endpoints

### Meta
| Method | Path | Description |
|---|---|---|
| GET | `/api/meta/health` | Liveness + which LLM is configured |
| GET | `/api/meta/teams` | Full NBA team list with abbreviations and logos |

### Games / matchup data
| Method | Path | Description |
|---|---|---|
| GET | `/api/games/upcoming` | Upcoming games from the live odds feed |
| GET | `/api/games/matchup?home=&away=` | Bundled snapshot (stats + injuries + sentiment) |
| GET | `/api/games/team-stats?team=` | Team form (last 10) |
| GET | `/api/games/injuries?team=` | Latest injury report (filtered) |
| GET | `/api/games/sentiment?team=` | Aggregated media sentiment |
| GET | `/api/games/head-to-head?home=&away=` | All-time H2H summary |
| GET | `/api/games/odds?home=&away=` | Per-bookmaker odds snapshot |
| GET | `/api/games/market-consensus?home=&away=` | Averaged market home/away probabilities |
| GET | `/api/games/similar?home_abbr=&away_abbr=` | Top vector-store retrievals for the matchup |

### Analysis
| Method | Path | Description |
|---|---|---|
| POST | `/api/analysis/run` | Synchronous `single_agent` / `multi_agent` / `cot` (used by Compare All) |
| POST | `/api/analysis/stream` | Same modes, **streamed** as SSE — emits `trace` events line-by-line, ends with one `done` event carrying the parsed report |

Request body:

```json
{
  "mode": "multi_agent",
  "home_team": "Boston Celtics",
  "away_team": "Los Angeles Lakers",
  "home_abbr": "BOS",
  "away_abbr": "LAL",
  "game_date": "2026-05-12"
}
```

SSE stream payloads:

```text
event: message
data: {"event":"trace","line":"  Stats & Metrics Agent","status":"Working on Stats & Metrics Agent"}

event: message
data: {"event":"done","report":{ ... },"raw":{ ... },"trace":"...","mode":"multi_agent"}
```

### Backtest / research
| Method | Path | Description |
|---|---|---|
| GET | `/api/backtest/summary` | Per-method headline metrics + run metadata |
| GET | `/api/backtest/predictions` | Game-level predictions |
| GET | `/api/backtest/calibration` | Calibration curve data |
| GET | `/api/backtest/ablations` | Per-source Brier deltas (RQ3) |
| POST | `/api/backtest/run` | Spawns `nba_backtest.py` (`{n_games, season, min_history}`) |
| GET | `/api/backtest/simulate` | Flat-stake ROI simulator (`method`, `edge_threshold`, `side_filter`, `min_confidence`) |

## Streaming model

The Streamlit app captures `stdout` from the agents to render a "live trace". The FastAPI version follows the same shape:

1. `services/analysis.py` runs the agent on a worker thread.
2. A queue-backed `_QueueWriter` swaps in via `contextlib.redirect_stdout`.
3. Each completed line is pushed onto a queue.
4. The SSE generator awaits the queue on the event loop and emits one event per line.
5. A final `done` event carries the parsed JSON report, the raw agent dict, and the full captured trace.

That keeps `nba_agent.py`, `nba_multi_agent.py`, and `nba_cot_baseline.py` completely unchanged — the React frontend just sees their stdout in real time.

## Notes

- The backend `chdir`s into the repo root on import so the existing modules' relative `data/foo.csv` paths resolve regardless of where uvicorn is launched.
- Python 3.9 is supported (FastAPI signatures stick to `Optional[str]` / `List[dict]`).
- The Streamlit app, pages, and data pipelines remain untouched. You can still run `streamlit run Matchup_Analysis.py` if you want the legacy UI.
