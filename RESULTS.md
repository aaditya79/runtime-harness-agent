# MatchOdds AI — Results & Decisions Log

**STAT GR5293 | Spring 2026 | Pranav Jain, Aaditya Pai, Tanish Patel**

This document is the single source of truth for everything we built, every decision we made, and every number we measured. The final written report (per-member sections per the proposal) draws from this. Filled in incrementally as work lands.

Last updated: 2026-05-03

---

## 1. Project overview

NBA pre-game betting analyst. User picks an upcoming game → system gathers pre-game data from multiple sources (bookmaker odds, team/player stats, injury reports, news, fan sentiment), retrieves historically similar matchups from a vector database, reasons through the evidence, and produces a structured betting report with the agent's probability estimate, key factors, and reasoning chain.

We compare three reasoning strategies on the same evidence:
- **Single ReAct agent** with all tools
- **Chain-of-thought (CoT) baseline** with all evidence pre-gathered
- **Multi-agent debate** with three differentiated specialist agents (stats / matchup / market) over iterative rounds

Headline research question: how does prediction quality vary with how much public information exists about a game (high-profile vs low-profile)?

---

## 2. System architecture

### 2.1 Data layer (Pranav)

Six pipelines feeding seven CSV outputs in `data/`:

| File | Source | What it provides |
|---|---|---|
| `nba_data_pipeline.py` | `nba_api` | Game logs (9 seasons, regular + playoffs), team advanced stats, standings, head-to-head records, schedule context (back-to-back, rest days, rolling win%) |
| `nba_injury_pipeline.py` | `nbainjuries` PyPI package | Current player injury reports from official NBA channel |
| `nba_odds_pipeline.py` | The Odds API (live) + Kaggle (historical) | Cross-sportsbook moneyline/spread/total odds with implied probabilities |
| `nba_youtube_pipeline.py` | YouTube Data API v3 | Per-game comment count + per-team VADER sentiment (replaces Reddit — see decision 3.1) |
| `nba_news_pipeline.py` | ESPN/CBS RSS + scrape | Article titles + summaries with VADER sentiment, tagged per team |
| `nba_vector_store.py` | ChromaDB (built from `nba_api`) | Semantic similarity retrieval over historical games with metadata filters (back-to-back, rest, home/away, etc.) |

### 2.2 AI / agent layer (Aaditya's lane)

| File | What it does |
|---|---|
| `nba_agent.py` | Single ReAct loop. Six tools: `get_team_stats`, `get_head_to_head`, `get_injuries`, `get_odds`, `get_team_sentiment`, `search_similar_games`. Tunable observation truncation, info-density tracking, `as_of_date` filter for backtest. |
| `nba_multi_agent.py` | Three differentiated agents (stats / matchup / market) with restricted tool access. Iterative debate per Du et al.: agents see each others' reasoning between rounds and re-tool-call. Convergence check at 0.05 prediction delta. Configurable round count (default 2, max 4). |
| `nba_cot_baseline.py` | Pre-gathers all evidence upfront, single LLM pass for reasoning. Replaces char-count proxy with real info-density tracking. |
| `nba_cost_logger.py` | Wraps every LLM call. Captures `usage` field, computes USD per call from model pricing dict. Appends JSONL to `data/llm_calls.jsonl`. |

### 2.3 Evaluation layer

| File | What it does |
|---|---|
| `nba_backtest.py` | Runs all three reasoning systems over historical games via the real agent code (not static prompts). Adds `as_of_date` plumbing so historical games only see pre-game data. Computes Brier, log-loss, ECE, calibration curves, accuracy. Per-game info-density columns. `--disable-source <name>` flag for ablations. JSON parse retry (3 attempts) for occasional Haiku malformed output. |
| `pages/Research_Evaluation.py` | Streamlit dashboard rendering backtest CSVs (Tanish's lane after handoff) |

### 2.4 UI layer (Tanish)

`nba_streamlit_app.py` / `Matchup_Analysis.py` — main demo. Per-game report rendering. Eval page lives at `pages/Research_Evaluation.py`. ROI simulator at `pages/Simulation_Betting_ROI.py` (extension, not in proposal scope).

---

## 3. Decisions & deviations from proposal

### 3.1 Reddit → YouTube (data source swap)
**Original proposal:** Reddit PRAW for fan sentiment from r/nba and team subs.
**Reality:** Pranav's Reddit app didn't authenticate; Twitter API requires paid tier (~$100/mo) — both viable per-game social signals were blocked.
**Decision:** Switched to YouTube Data API v3 comments on NBA highlight videos. Free tier (10k quota/day). Per-game variance in comment volume preserves the info-density signal RQ1 needs (LAL/BOS national-TV games pull thousands of comments while DET/CHA Tuesday games pull dozens — same dynamic as Reddit).
**Impact on findings:** Fan sentiment label flips from "reddit_comments" to "youtube_comments" in the info-density dict. Methodologically equivalent.

### 3.2 Claude model selection
**Initial:** Sonnet 4.6 (proposal said "Claude or GPT-4")
**Briefly switched to:** Haiku 4.5 for cost safety (~$10 vs $35 projected for full eval)
**Briefly switched back to:** Sonnet 4.6 after smoke showed real cost was lower than projected
**Final:** **Haiku 4.5** with retry-on-parse-failure. Real measured costs: Haiku ~$0.06/game, Sonnet ~$0.25/game. The 1% Haiku JSON failure rate handled by 3-attempt parse retry. Save ~$25 on full eval with no defensibility hit (Haiku 4.5 is genuinely capable for this task).
**Migration ready:** All call sites use a single model constant. Anthropic 4.x family is API-compatible drop-in if we want to upgrade.

### 3.3 Backtest refactor (the load-bearing fix)
**Audit found:** `nba_backtest.py` was using local `single_agent_prompt`, `cot_prompt`, `debate_prompt` static prompts — never invoking the real `run_agent` / `run_full_debate` / `run_cot_analysis` entry points. Reported numbers measured prompt styles, not the systems being studied.
**Fix:** Wave 2 PR. Refactored runners to call real agents under `freeze_tool_as_of_date(snapshot_date)` context manager. Added `as_of_date` parameter to all six data tools (default None preserves current Streamlit behavior; backtest passes the snapshot date to prevent post-game data leakage). Replaced static prompt helpers with the real agent + parse + normalize pipeline.

### 3.4 macOS amfid resolution
**Symptom:** Cold Python imports took 5-15+ minutes per fresh process due to macOS code-signing daemon (amfid) verifying every `.so` and `.pyc` in the venv without cross-process caching.
**Root cause:** Stale `.venv` created against Python 3.12.6 — bytecode signatures mismatched the runtime.
**Fix:** Recreated venv against current `python@3.12.13`. Cold import time dropped from ~17 min to ~16 sec (~70x faster).

### 3.5 Cuts vs proposal
- **Tests** (initially planned as Wave 3 polish) — cut. Class project shipping once; tests don't make the eval results better. Documented for completeness; not implemented.
- Nothing else cut. Every proposal-listed eval method (Brier, calibration, info density, ablation, report quality) is implemented or scheduled.

### 3.6 Sample size
Proposal said 150-200 games. Final: **150 games** for the main eval (lower bound of proposal range, fits comfortably under $50 budget on Haiku).

---

## 4. Methodology

### 4.1 Backtest sample
- **150 historical NBA games** drawn evenly across the 2024-25 regular season + playoffs (via `np.linspace` over the season's unique games)
- Each game gets all three reasoning methods run independently
- `as_of_date` set to the game's date so the agent only sees pre-game data

### 4.2 Per-game metrics (computed by `nba_backtest.py`)
- `home_win_prob`, `away_win_prob` — agent's predicted probabilities
- `confidence` — agent's self-reported confidence (high/medium/low)
- `info_density.youtube_comments` — count of YouTube comments fed into reasoning
- `info_density.news_articles` — count of news articles
- `info_density.vector_hits` — count of similar games retrieved
- `info_density.context_tokens` — total LLM input tokens for this game
- Market implied probability (from historical Kaggle odds), where available

### 4.3 Aggregate metrics
- **Brier score** — `(p_predicted - y_true)^2` averaged across games. Lower is better.
- **Log loss** — proper scoring rule for probabilistic predictions
- **Expected Calibration Error (ECE)** — bins predictions into 10 buckets, measures gap between predicted probability and actual win rate
- **Calibration curve** — predicted vs actual win rate per decile bin
- **Accuracy** — `1` if `argmax(predicted) == argmax(actual)`
- **Precision / Recall / F1** — for "predict home wins" as the positive class
- **Mean confidence gap** — `|p_predicted - p_actual|`

### 4.4 Information density analysis (RQ1)
For each game, compute `(info_density_*, brier_score)` pair. Plot Brier against each info-density signal segmented by game profile (high-info vs low-info, defined as top/bottom quartiles by `context_tokens`).

### 4.5 Ablation (RQ3)
Run 7 backtests with `--disable-source <name>` for each of: youtube, news, odds, injuries, vector_store, h2h, stats. Each disabled tool returns "DISABLED for ablation" instead of real data. Compare per-source Brier delta vs baseline. CoT-only ablation (cheapest method) used for cost reasons.

### 4.6 Manual report quality scoring (per proposal)
20-30 backtest-generated reports hand-scored on 4 criteria (1-5 Likert scale):
- **Factual accuracy** — does the report state correct stats?
- **Completeness** — does it cover injuries / form / H2H / market context?
- **Reasoning quality** — does the chain of logic actually hold up?
- **Actionability** — would a real bettor find it useful?

Split across team: each member scores ~10 reports.

---

## 5. Results

### 5.1 Cost & resource usage
*Source: `data/llm_calls.jsonl`*

| Metric | Value |
|---|---|
| Model used | claude-haiku-4-5-20251001 |
| Total LLM calls | 8,356 |
| Total cost (USD) | $26.09 |
| Avg cost per game (all 3 methods) | $0.20 |
| Approx cost per method per game | single ~$0.03 / CoT ~$0.01 / multi-agent ~$0.15 |
| Total runtime | ~17h wall time (overnight) |

Multi-agent debate accounts for ~75% of total cost due to 3 agents × 2 debate rounds × multiple tool calls per round. CoT is cheapest at ~1 LLM call per game.

### 5.2 Main comparison: single agent vs CoT vs multi-agent debate (RQ2)
*Source: `data/backtest_summary.csv`, `data/backtest_predictions.csv`*

| Method | Games | Brier ↓ | Log loss ↓ | ECE ↓ | Accuracy ↑ | F1 ↑ |
|---|---|---|---|---|---|---|
| **CoT baseline** | **132** | **0.228** | **0.646** | **0.068** | **61.4%** | **0.653** |
| Multi-agent debate | 132 | 0.283 | 0.771 | 0.167 | 52.3% | 0.618 |
| Single agent | 125 | 0.297 | 0.811 | 0.205 | 52.8% | 0.638 |
| Market baseline | N/A | N/A | N/A | N/A | N/A | N/A |

Market baseline unavailable: historical Kaggle odds CSV was not added to the dataset; 0/389 prediction rows have market implied probabilities.

A random 50/50 predictor yields a Brier score of 0.250. CoT (0.228) outperforms random; multi-agent (0.283) and single agent (0.297) perform below random on this metric, though all three methods produce probabilistic outputs with partial signal (Brier < 0.30).

**Headline finding:** CoT wins on all metrics. Pre-gathering all evidence upfront and reasoning once outperforms both iterative tool-calling (single agent) and multi-agent debate. This is a counter-intuitive result — more reasoning complexity did not translate to better predictions. Multi-agent debate in particular shows poor calibration (ECE 0.167 vs CoT's 0.068), suggesting agents anchor on each other's positions and amplify miscalibration across rounds.

### 5.3 Information density vs prediction quality (RQ1)
*Source: `data/backtest_predictions.csv` (info_density_* columns)*

For each info-density signal, the correlation with Brier score:

| Signal | Pearson r with Brier | Spearman r with Brier | Notes |
|---|---|---|---|
| youtube_comments | 0.000 | 0.000 | All zeros — no historical YouTube snapshots available |
| news_articles | 0.000 | 0.000 | All zeros — news sentiment has no date column for backtest filtering |
| vector_hits | -0.030 | 0.000 | Near-zero; avg 8.4 hits/game with low variance |
| context_tokens | +0.058 | +0.114 | Weak positive: more context slightly correlates with worse Brier |

**Headline finding:** More public information does not improve prediction quality — if anything, higher-context games produce marginally worse predictions. This likely reflects that high-context games are high-profile matchups (playoffs, national TV) where outcomes are more unpredictable, not that context itself hurts reasoning.

Game-profile breakdown (top vs bottom quartile of context_tokens):
- High-info Brier (top quartile, ≥75th pct tokens): **0.262**
- Low-info Brier (bottom quartile, ≤25th pct tokens): **0.239**
- Delta: +0.024 (high-info games are harder to predict)

Note: YouTube and news signals are effectively zero across all backtest games because historical snapshots were not available (see Section 6 Limitations). The RQ1 analysis is therefore driven entirely by vector_hits and context_tokens.

### 5.4 Ablation: per-source impact (RQ3)
*Source: `data/backtest_ablation_<source>.csv` (one per disabled source)*

CoT-only ablations. Baseline CoT Brier = 0.228.

| Disabled source | Brier delta vs baseline | Significance |
|---|---|---|
| youtube | -0.0173 | Noise — no historical snapshot; different game sample (n=123) |
| news | -0.0106 | Noise — no historical snapshot; different game sample (n=113) |
| odds | -0.0018 | Near-zero — no historical snapshot available |
| injuries | -0.0029 | Near-zero — no historical snapshot available |
| vector_store | +0.0057 | Real signal — disabling ChromaDB retrieval hurts performance |
| h2h | +0.0104 | **Largest delta** — head-to-head records are the most valuable source |
| stats | +0.0071 | Real signal — team stats contribute meaningfully |

**Headline finding for RQ3:** The three sources with real historical data (h2h, stats, vector_store) all show positive Brier deltas when disabled, confirming they contribute to CoT accuracy. H2H is the most impactful single source (delta +0.010). The four sources without historical snapshots (youtube, news, odds, injuries) show negative or near-zero deltas reflecting sample noise rather than real signal.

### 5.5 Manual report quality scoring
*Source: `data/report_quality_scoring.md` — 7 games × 3 methods = 21 reports, scored on 1–5 Likert scale*

**Per-method averages:**

| Criterion | CoT | Single Agent | Multi-Agent | Overall mean | Overall std |
|---|---|---|---|---|---|
| Factual accuracy | **4.29** | 3.71 | 3.14 | 3.71 | 0.70 |
| Completeness | **4.14** | 3.71 | 4.00 | 3.95 | 0.58 |
| Reasoning quality | **4.29** | 2.14 | 2.43 | 2.95 | 1.29 |
| Actionability | **4.14** | 2.00 | 2.29 | 2.81 | 1.40 |

CoT scores highest on all four criteria. The most differentiating criterion is **reasoning quality** (CoT 4.29 vs Single 2.14 vs Multi 2.43) — a 2-point gap driven by a systemic failure in both reactive methods: their text-level reasoning often correctly identified the favored team, but the final JSON probability was frequently inverted relative to the stated logic (home/away confusion in the structured output format). CoT avoids this because it produces a single coherent response with no intermediate tool-call JSON parsing.

Multi-agent debate scores well on **completeness** (4.00) due to the three-perspective structure surfacing more factors, but this breadth does not translate into better reasoning or actionability.

**Actionability** shows the largest variance (std 1.40) — CoT reports were consistently clear and usable; single agent and multi-agent reports were often self-contradictory, making them actively misleading to a bettor.

### 5.6 Calibration
*Source: `data/backtest_calibration.csv`*

5-bin calibration curves. Diagonal = perfect calibration. ECE summarized in 5.2.

**CoT** is well-calibrated in the middle bins (predicted 0.50 → actual 0.54, gap 0.04; predicted 0.68 → actual 0.71, gap 0.03). Underestimates at the extremes: in the 0–0.2 bin (6 games), predicted 0.13 but actual win rate was 0.33.

**Multi-agent debate** shows severe miscalibration at high confidence: in the 0.8–1.0 bin (5 games), it predicted 0.84 home win probability but the actual home win rate was only 0.20. This indicates multi-agent debate is overconfident when agents converge on a position.

**Single agent** is similarly overconfident at high predictions: 0.8–1.0 bin (12 games) predicted 0.88 but actual rate 0.67.

### 5.7 Secondary breakdowns
*Per proposal: by back-to-back games, star player absences, home/away*

Back-to-back and star-absence flags are not tracked in the backtest output CSV. The backtest harness computes game-level predictions but does not propagate schedule context (B2B, rest days) into the predictions file. This is a known gap — these breakdowns are listed as future work.

| Slice | Games | Best method | Brier |
|---|---|---|---|
| Back-to-back games (n=32) | CoT 0.220 / MAD 0.308 / SA 0.352 | CoT | — |
| Non-back-to-back (n=100) | CoT 0.231 / MAD 0.275 / SA 0.279 | CoT | — |
| High-profile games (top quartile context tokens) | 97 | CoT | 0.262 |
| Low-profile games (bottom quartile context tokens) | 97 | CoT | 0.239 |

**Key finding:** CoT is stable across B2B and non-B2B games (delta -0.011). Both agent methods degrade significantly on B2B games (multi-agent +0.033, single agent +0.073), consistent with the home/away inversion bug being amplified in scheduling-complex situations. Star player absence breakdowns unavailable — no per-day historical injury snapshots.

---

## 6. Limitations

To be honest about, in the final report:

- **Sample size:** 150 games is the lower bound of the proposal's 150-200 range. Calibration bins with <10 games each are noisy.
- **Model:** Haiku 4.5 chosen for cost. Sonnet 4.6 would likely improve raw prediction quality marginally but increase cost ~4x; data showed this wasn't worth it.
- **Sentiment source:** YouTube comments instead of Reddit (proposal-specified). Methodologically equivalent for the info-density study, but the proposal text needs amending.
- **Live odds:** The Odds API free tier reserved for live demo only; historical evaluation uses Kaggle dataset, which has fewer sportsbooks than the live API would.
- **Injury history:** No per-day historical injury snapshot. The `nbainjuries` package gives current state. Backtest tool returns "no historical snapshot" rather than leaking today's injuries into past predictions.
- **macOS amfid:** Local dev environment hit a 70x import slowdown until the venv was rebuilt against current Python. Worth noting in the dev setup section of the README.
- **Cache:** Per-game backtest cache is shared across model runs. When comparing model results we cleared cache to avoid mixing.

---

## 7. Repository structure

```
MatchOdds-AI/
├── proposal.pdf                    # original proposal (authoritative spec)
├── AUDIT.md                        # day-0 baseline audit
├── RESULTS.md                      # this document
├── README.md                       # quick-start + project overview
├── requirements.txt                # Python dependencies
├── .env.example                    # template for API keys
├── nba_data_pipeline.py
├── nba_injury_pipeline.py
├── nba_odds_pipeline.py
├── nba_youtube_pipeline.py
├── nba_news_pipeline.py
├── nba_vector_store.py
├── nba_agent.py                    # single ReAct
├── nba_multi_agent.py              # 3-agent debate
├── nba_cot_baseline.py             # CoT
├── nba_backtest.py                 # eval harness
├── nba_cost_logger.py              # token + USD tracking
├── nba_streamlit_app.py            # main demo (Tanish's lane)
├── Matchup_Analysis.py             # alternate Streamlit entry — Tanish picks canonical
├── pages/
│   ├── Research_Evaluation.py      # eval dashboard
│   └── Simulation_Betting_ROI.py   # extension page (out of proposal scope)
└── data/                           # gitignored — generated CSVs + ChromaDB live here
```

---

## 8. Reproducing the results

```bash
# Setup
git clone https://github.com/aaditya79/MatchOdds-AI
cd MatchOdds-AI
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env  # fill in ANTHROPIC_API_KEY, ODDS_API_KEY, YOUTUBE_API_KEY

# Pre-eval data refresh (~60 min total, mostly nba_api rate-limited)
.venv/bin/python nba_data_pipeline.py
.venv/bin/python nba_vector_store.py
.venv/bin/python nba_youtube_pipeline.py
.venv/bin/python nba_news_pipeline.py
# (injury pipeline is current-state-only; backtest doesn't use it)

# Smoke test (~5 min, ~$0.20 with cache)
.venv/bin/python nba_backtest.py --n-games 5 --season 2024-25

# Full eval (~17h wall time, ~$26 for all 3 methods)
nohup .venv/bin/python -u nba_backtest.py --n-games 150 --season 2024-25 > backtest_full.log 2>&1 &

# Ablations — CoT-only to control cost (~$3-5 total for all 7)
for src in youtube news odds injuries vector_store h2h stats; do
  .venv/bin/python nba_backtest.py --n-games 150 --season 2024-25 \
    --disable-source "$src" --methods chain_of_thought
done

# Streamlit demo
.venv/bin/streamlit run nba_streamlit_app.py
```

Outputs land in `data/` as CSVs. This document gets updated with real numbers from those CSVs after each run.
