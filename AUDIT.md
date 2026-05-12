# Day-0 Code Audit

_Baseline review of the repo as it stood immediately after the initial commits and the proposal upload. Written to give the team a shared map of what exists, what's solid, and what's missing before we split up the remaining work._

## TL;DR

- The repo is ~60% complete against the proposal.
- Foundation (NBA data pipeline, ChromaDB vector store, Odds API scaffolding) is strong.
- The evaluation infrastructure the proposal centers on — Brier score, calibration curves, ablation, information density — is **not built anywhere in the repo**. This is the single biggest gap.
- Multi-agent debate is scaffolded but isn't iterative in the Du et al. sense.
- The Streamlit app is visually polished but several data paths it depends on are broken or missing.
- Zero tests. Zero.

## Per-file sophistication

Rating is 1–5 (1 = stub, 3 = functional draft, 5 = production-ready). Completeness is against what the proposal implies the file should do.

| File | LOC | Rating | Complete |
|---|---|---|---|
| `nba_data_pipeline.py` | 266 | 4/5 | 95% |
| `nba_vector_store.py` | 281 | 4/5 | 95% |
| `nba_odds_pipeline.py` | 215 | 4/5 | 90% |
| `nba_multi_agent.py` | 513 | 4/5 | 70% |
| `nba_reddit_pipeline.py` | 248 | 3/5 | 80% |
| `nba_cot_baseline.py` | 299 | 3/5 | 60% |
| `nba_agent.py` | 589 | 3/5 | 70% |
| `nba_streamlit_app.py` | 1101 | 2.5/5 | 60% |
| `nba_news_pipeline.py` | 260 | 2/5 | 50% |
| `nba_injury_pipeline.py` | 136 | 2/5 | 40% |

## 1. Architecture

**A1. No evaluation harness exists anywhere.** The proposal's centerpiece — Brier score, calibration curves, ablation study, information density analysis — is unimplemented across all 10 files. No shared scoring function, no batch runner that iterates 150–200 games through the three approaches, no CSV export for comparison. Without this, there are no findings to report.

**A2. No Kaggle historical data integration.** The proposal specifies that live Odds API is demo-only and all evaluation uses Kaggle. `nba_odds_pipeline.py:124` has a placeholder that expects a manually placed CSV at `data/kaggle_odds.csv`. The dataset has not been pulled and there is no loader for it.

**A3. Multi-agent debate is not actually iterative.** `nba_multi_agent.py:220–294` gives each agent one tool call per round, then asks for analysis. Agents cannot respond to a peer's claim by gathering additional data — they only respond once with the context they already have. That is closer to "parallel agents summarized by a moderator" than to the Du et al. debate framework the proposal cites. Round count is hardcoded at 2 with no convergence check.

**A4. Agent tool data dependencies are broken.** `nba_agent.py:148` reads `data/odds_live.csv`, which is not produced by any pipeline that has been run. The same gap applies to news and Reddit data reaching the agent tools. The Streamlit app will call `tool_get_odds()` and silently land on "No data available."

## 2. Code Quality

**Q1. `nba_injury_pipeline.py` uses the wrong source.** The proposal specifies `nbainjuries` (official NBA reports). The current file scrapes ESPN HTML with fragile heuristics like `find_all_previous(limit=10)` for team extraction (lines 46–63). ESPN's DOM changes frequently — this will break silently. Either rewrite against `nbainjuries` per proposal, or amend the proposal.

**Q2. Action parsing across agent files is regex-based.** `nba_agent.py:305–331` splits LLM output on "ACTION:" and handles quoted args with regex — no JSON mode, no structured output retry. `parse_report()` in the Streamlit app (lines 535–547) has the same fragility. Any LLM output drift causes silent failure.

**Q3. Season range is stale and playoffs are excluded.** `nba_data_pipeline.py:30` stops at 2024-25. As of April 2026 the 2025-26 regular season has just finished and is missing. Line 58 filters to `season_type_nullable="Regular Season"`, excluding playoffs — arguably the most informative data for betting precedent.

**Q4. Rolling stats leak across seasons.** `nba_data_pipeline.py:100–103` computes a 10-game rolling win% sorted by date without grouping by season. A team's last three games of one season blend with the first seven of the next — same team, different roster, wrong signal. Needs a `(TEAM_ID, SEASON)` groupby.

**Q5. News pipeline has no primary source and is missing Bleacher Report.** `nba_news_pipeline.py` tries RSS + ESPN scraping + CBS Sports with no indication of which succeeded. Proposal explicitly lists Bleacher Report RSS; the code doesn't include it. Deduplication is title-only (line 229) and team tagging is naive substring matching (lines 183–195).

**Q6. Reddit game-thread search is dead code.** `nba_reddit_pipeline.py:107–131` defines `pull_game_thread_comments()` but it is never called in `main()` (line 171+). The matchup agent is intended to consume game-specific Reddit context — it currently gets only team-level subreddit posts.

## 3. Tests

Nothing exists. Zero test files, zero assertions. `nba_vector_store.py:210–243` has "test queries" that print results but never verify that a filter like `back_to_back=1` actually returns back-to-back games.

Minimum coverage proposed:

- Each pipeline: golden-row assertion — known game ID → expected columns and values.
- Vector store: query returns games that satisfy the filter.
- Agent tools: each tool returns the expected schema on known inputs.
- CoT baseline: Brier score correctness on synthetic inputs.
- End-to-end: one game through all three approaches, report structure validated.

## 4. Performance

**P1. Streamlit has no caching.** `render_team_snapshot()` and `render_injury_summary()` hit the data layer on every team-selection change. No `@st.cache_data`, no session state. The user waits seconds before even clicking "Run Analysis."

**P2. Information density tracking is a proxy, not a measurement.** `nba_cot_baseline.py:84–89` counts total characters and "sources with data". Proposal RQ1 literally asks how much data the agent gathered — that needs token counts, Reddit comment counts, news article counts, and vector store hit counts. None of these are tracked.

**P3. No token budgeting or cost tracking.** 150–200 games × (multi-agent ~15–20 LLM calls + ReAct ~5–8 + CoT 1) = roughly 3k–6k LLM calls. Against the current hardcoded `claude-sonnet-4-20250514`, that is ~$100–200. Proposal budget was $50–100. No per-agent cost logging exists.

**P4. Observation truncation is silent.** `nba_agent.py:404` truncates tool results above 3000 characters with "…(truncated)." High-profile games with dense Reddit/news input — exactly the RQ1 case the project wants to study — will silently lose the signal.

## What's left — concrete deliverables

Ranked by priority:

1. **Evaluation harness.** Brier score + calibration curves + ablation runner + CSV export. ~200 LOC of net-new code. Blocks every research finding.
2. **Kaggle historical odds loader.** Pull the dataset, wire it into `nba_odds_pipeline.py:124`. Blocks evaluation entirely.
3. **Fix `nba_injury_pipeline.py` source.** Switch to `nbainjuries` package per proposal, or decide as a team to amend the proposal.
4. **CoT baseline: true information density metrics.** Token count, Reddit comment count, news article count, vector store hit count. Required for RQ1.
5. **CoT baseline: ablation mode.** CLI flag to disable one source at a time and re-run.
6. **Multi-agent: true iterative debate.** Allow agents to gather more data in response to peers. Convergence-based termination.
7. **Rolling stats season leak fix.** One-line fix at `nba_data_pipeline.py:100`.
8. **Extend `SEASONS` to include 2025-26, and pull playoffs.**
9. **Agent action parsing: switch to structured output (JSON mode) with retry.**
10. **Streamlit: exception handling around agent calls; caching on team snapshots; secrets via `.streamlit/secrets.toml`.**
11. **Streamlit: game picker from upcoming NBA schedule** (currently requires manual team + date entry).
12. **Wire news and Reddit data into agent tools.** Add Bleacher Report RSS. Fix Reddit game-thread dead code.
13. **Minimum test suite — 10+ assertions across pipelines, vector store, and CoT scoring.**
14. **Agent cost and token logging.** Per-run, per-agent.

## Assumptions this audit makes

- Proposal (`proposal.pdf`) is the authoritative spec when it and the README disagree. README has since been updated to match.
- `nbainjuries` in the proposal refers to the Python package of that name, not ESPN's injury page.
- 150–200 evaluation games are intended to be pulled from Kaggle (historical), not the live Odds API.
- The "debate" in the proposal means iterative tool-augmented response (Du et al.), not parallel summarization.

If any of these assumptions is wrong, some audit items reframe — worth discussing in the next team sync.
