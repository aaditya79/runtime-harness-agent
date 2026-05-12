<h1 align="center">⛹️ MatchOdds AI</h1>

<p align="center">
  <strong>Agentic RAG for NBA pre-game betting analysis</strong><br/>
  Chain-of-thought · Single ReAct agent · Multi-agent debate — evaluated on 132 real games
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/React-Vite-61DAFB?logo=react&logoColor=black" />
  <img src="https://img.shields.io/badge/FastAPI-backend-009688?logo=fastapi&logoColor=white" />
  <img src="https://img.shields.io/badge/Claude-Haiku_4.5-orange?logo=anthropic&logoColor=white" />
  <img src="https://img.shields.io/badge/ChromaDB-vector_store-green" />
  <img src="https://img.shields.io/badge/Columbia-STAT_GR5293-003DA5" />
</p>

---

## What It Does

Given an upcoming NBA game, MatchOdds AI pulls pre-game data from six sources, runs it through one of three LLM reasoning systems, and produces a structured report with win probabilities, key factors, bookmaker market comparison, historically similar games, and a full reasoning trace.

Built as a research platform to answer:

| | Research Question |
|---|---|
| **RQ1** | Does more pre-game data improve predictions, or do high-profile games become harder due to efficient markets? |
| **RQ2** | Does multi-agent debate with differentiated tool access outperform a single chain-of-thought pass? |
| **RQ3** | Which data sources actually move the needle on Brier score? |

---

## Results

> 132 games · 2024–25 NBA season · Claude Haiku 4.5 · all methods share the same tool layer

| Method | Brier ↓ | Log Loss ↓ | ECE ↓ | Accuracy ↑ |
|---|:---:|:---:|:---:|:---:|
| 🏆 **CoT Baseline** | **0.228** | **0.646** | **0.068** | **61.4%** |
| Multi-Agent Debate | 0.283 | 0.771 | 0.167 | 52.3% |
| Single ReAct Agent | 0.297 | 0.811 | 0.205 | 52.8% |
| *Random (50/50)* | *0.250* | — | — | — |

Both agent-based methods fall **below the random-predictor Brier baseline of 0.25**, driven by a home/away label inversion in their structured JSON outputs. CoT avoids this by producing a single coherent generation.

### Ablation — which sources matter? (RQ3)

| Disabled Source | Brier | Delta | Signal? |
|---|:---:|:---:|:---:|
| h2h | 0.2385 | **+0.010** | ✅ Real historical data |
| stats | 0.2352 | **+0.007** | ✅ Real historical data |
| vector_store | 0.2338 | **+0.006** | ✅ Real historical data |
| odds | 0.2263 | −0.002 | ❌ No historical snapshot |
| injuries | 0.2252 | −0.003 | ❌ No historical snapshot |
| news | 0.2175 | −0.011 | ❌ No historical snapshot |
| youtube | 0.2108 | −0.017 | ❌ No historical snapshot |

Baseline CoT Brier = 0.2281. Only the three sources with real historical data contribute signal.

**Cost:** $49.84 total · $26.09 main eval (8,356 API calls, all 3 methods) · ~$23.75 for 7 CoT-only ablation sweeps

---

## Architecture

```
┌──────────────────────────────────────────────┐
│          React Frontend  (Vite + TS)          │
│   Matchup Analysis · Research · Simulation   │
└──────────────────┬───────────────────────────┘
                   │  HTTP / SSE streaming
┌──────────────────▼───────────────────────────┐
│              FastAPI Backend                  │
│    /games · /analysis · /backtest · /pipelines│
└──────────────────┬───────────────────────────┘
                   │
        ┌──────────┴──────────────────┐
        ▼                             ▼
 ┌─────────────┐          ┌──────────────────────┐
 │ CoT Baseline│          │  Single ReAct Agent  │
 │  1 LLM call │          │    up to 12 steps    │
 └─────────────┘          └──────────────────────┘
                          ┌──────────────────────┐
                          │  Multi-Agent Debate  │
                          │ 3 agents · 2 rounds  │
                          └──────────┬───────────┘
                                     │
┌────────────────────────────────────▼─────────┐
│              Tool Layer  (6 functions)        │
│  get_team_stats  ·  get_head_to_head         │
│  get_injuries    ·  get_odds                 │
│  get_team_sentiment  ·  search_similar_games │
│            (all accept as_of_date)           │
└──────────────────┬───────────────────────────┘
                   │
┌──────────────────▼───────────────────────────┐
│                 Data Layer                    │
│  nba_api · 11,465 games · 9 seasons          │
│  ChromaDB · 22,930 embedded game documents   │
│  The Odds API + Kaggle historical odds       │
│  nbainjuries · ESPN/CBS RSS · YouTube · Reddit│
└──────────────────────────────────────────────┘
```

### Reasoning Methods

| Method | LLM Calls | Description |
|---|:---:|---|
| **CoT Baseline** | 1 | All six tools called deterministically upfront; single structured prompt |
| **Single ReAct Agent** | 5–12 | Plans, calls tools one at a time, observes results, finalizes when ready |
| **Multi-Agent Debate** | 15–20 | Stats · Matchup · Market agents with differentiated tool access; 2 debate rounds; moderator synthesizes |

---

## Data Sources

| Source | Details |
|---|---|
| `nba_api` | 11,465 games · 9 seasons (2017–18 through 2025–26, incl. playoffs) |
| ChromaDB vector store | 22,930 embedded game docs with back-to-back, rest days, home/away filters |
| nbainjuries | Current player availability (point-in-time; no per-day historical snapshots) |
| The Odds API + Kaggle | Live cross-sportsbook moneylines; Kaggle dataset for historical backtesting |
| ESPN + CBS Sports RSS | 81 articles ingested; VADER sentiment per team |
| YouTube Data API v3 | Comment counts and sentiment on NBA highlight videos |
| Reddit public JSON | 1,567 comments (OAuth PRAW was blocked on university network; public endpoint used instead) |

---

## Setup

### Prerequisites

- Python 3.10+, Node.js 18+
- **Apple Silicon only:** Java OpenJDK 18 for `nbainjuries`
  ```bash
  brew install openjdk@18
  export JAVA_HOME=/opt/homebrew/opt/openjdk@18/libexec/openjdk.jdk/Contents/Home
  ```

### 1 — Install

```bash
git clone https://github.com/aaditya79/MatchOdds-AI.git
cd MatchOdds-AI
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 2 — API keys

```bash
cp .env.example .env
# Set: ANTHROPIC_API_KEY, ODDS_API_KEY, YOUTUBE_API_KEY
```

### 3 — Populate data (one-time, ~60 min)

```bash
python nba_data_pipeline.py    # nba_api historical data
python nba_vector_store.py     # build ChromaDB index
python nba_news_pipeline.py    # ESPN/CBS RSS
python nba_reddit_pipeline.py  # Reddit public JSON
python nba_injury_pipeline.py  # requires JAVA_HOME
python nba_odds_pipeline.py    # The Odds API
```

### 4 — Start backend

```bash
cd backend && pip install -r requirements.txt && ./run.sh
# FastAPI at http://localhost:8000
```

### 5 — Start frontend

```bash
cd frontend && npm install && npm run dev
# React app at http://localhost:5173
```

---

## Backtesting

```bash
# Smoke test (~$0.30)
python nba_backtest.py --n-games 5 --season 2024-25

# Full eval — 132 games, ~17 hours, ~$26
python nba_backtest.py --n-games 150 --season 2024-25

# Ablation sweep (CoT only, one source disabled at a time)
for src in h2h stats vector_store odds injuries news youtube; do
  python nba_backtest.py --n-games 150 --season 2024-25 --disable-source "$src"
done
```

Results are cached by `(game_id, method, ablation)` — interrupted runs resume without duplicating API calls.

**Output files:** `backtest_predictions.csv` · `backtest_summary.csv` · `backtest_calibration.csv` · `backtest_ablation_<source>.csv` · `backtest_run_metadata.json` · `llm_calls.jsonl`

---

## Key Findings

- **CoT wins on every metric.** One structured pass over pre-gathered evidence beats both iterative tool-calling and multi-agent debate on Brier, log loss, ECE, and accuracy.
- **Both agent methods fall below the random Brier baseline.** The home/away label inversion in structured JSON outputs systematically corrupts predictions; CoT has no intermediate JSON parsing step.
- **More data does not help (RQ1).** Pearson r = +0.058 between context tokens and Brier score. High-profile games are marginally harder, consistent with efficient markets tightening the lines on nationally covered games.
- **Only three sources contribute real signal (RQ3).** h2h (+0.010), stats (+0.007), vector store (+0.006). The other four return no historical snapshots in the backtest.
- **Agents degrade on back-to-back games.** CoT Brier delta = −0.011 on B2B games; multi-agent +0.033; single agent +0.073.

---

## Project Structure

```
MatchOdds-AI/
├── frontend/                  # React + TypeScript (Vite)
│   └── src/pages/
│       ├── MatchupPage.tsx    # main analysis UI
│       ├── ResearchPage.tsx   # backtest results, calibration, ablation charts
│       └── SimulationPage.tsx # betting simulation
├── backend/                   # FastAPI
│   └── app/routers/           # /games /analysis /backtest /pipelines
├── nba_agent.py               # single ReAct agent
├── nba_multi_agent.py         # multi-agent debate (3 agents × 2 rounds)
├── nba_cot_baseline.py        # chain-of-thought baseline
├── nba_backtest.py            # evaluation harness
├── nba_cost_logger.py         # per-call cost tracking
├── nba_*_pipeline.py          # data collection (6 pipelines)
├── harness/                   # validate-trace-enforce runtime layer
│   ├── models.py              # EnforcementAction, TraceRecord, HarnessResult, …
│   ├── tracer.py              # Tracer — trace_tool(), log_agent_state(), finalize()
│   ├── validator.py           # Validator — prob coherence + stat citation checks
│   ├── guardrail.py           # GuardrailEngine — PASS / BLOCK / REVISE / ESCALATE
│   └── engine.py              # run_with_harness() — wires all three layers
├── test_harness.py            # harness demo: live run + BLOCK + REVISE injection
├── data/sample/               # example CSVs for reproducibility
├── fig_*.png                  # publication-quality figures
├── report.tex / report.pdf    # 13-page research paper
└── requirements.txt
```

---

## Runtime Harness

A validate-trace-enforce layer wrapping the multi-agent debate system, built as a research prototype for trustworthy financial LLMs.

**Three enforcement rules, applied in priority order:**

| Rule | Trigger | Action |
|---|---|---|
| Prob coherence | `home_win_prob + away_win_prob` deviates from 1.0 by > 2 % | `BLOCK` |
| Agent disagreement | Spread across debate agents' `home_win_prob` exceeds 15 % | `ESCALATE` |
| Stat citation | A cited stat deviates from ground-truth by > 15 % | `REVISE` |
| All clear | — | `PASS` |

**Components (`harness/`):**

- `models.py` — `EnforcementAction`, `ValidationResult`, `TraceRecord` (SHA-256 hashed), `HarnessResult`
- `tracer.py` — `Tracer` with a `trace_tool()` context manager, `log_agent_state()`, and `finalize()`
- `validator.py` — `Validator` checks probability coherence and stat citation consistency against an optional ground-truth dict
- `guardrail.py` — `GuardrailEngine` maps validation + trace to an enforcement action
- `engine.py` — `run_with_harness()` wires all three layers around any `run_full_debate()` or `run_agent()` call

**Demo:**
```bash
python test_harness.py   # live debate run + BLOCK injection + REVISE injection → 3/3 rules verified
```

---

## References

1. Du et al. (2024). Improving factuality and reasoning in language models through multiagent debate. *ICML 2024.*
2. Lewis et al. (2020). Retrieval-augmented generation for knowledge-intensive NLP tasks. *NeurIPS 2020.*
3. Wei et al. (2022). Chain-of-thought prompting elicits reasoning in large language models. *NeurIPS 2022.*
4. Yao et al. (2023). ReAct: Synergizing reasoning and acting in language models. *ICLR 2023.*
5. Hutto & Gilbert (2014). VADER: A parsimonious rule-based model for sentiment analysis of social media text. *ICWSM 2014.*
6. Qiu, E. (2024). NBA odds and scores dataset. *Kaggle.*
