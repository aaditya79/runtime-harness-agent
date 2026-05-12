# MatchOdds AI — Status & Handoff

> **⚠️ Git rules:** Always `git pull` before pushing. **Never `git push --force` to main.** Main was wiped earlier today by an accidental force-push and we had to manually restore. If your local main looks divergent, ask before reconciling.

Updated: 2026-05-07

---

## 🟢 LATEST STATUS (May 7, 2026) — Aaditya's lane COMPLETE

### What Aaditya finished (all merged to main)

| Item | Result |
|---|---|
| 150-game backtest (all 3 methods, Haiku 4.5) | ✅ 132 games completed (18 skipped — early season, <10 prior games) |
| 7 ablation sweeps (CoT-only) | ✅ All 7 done |
| RESULTS.md Section 5 | ✅ All sections filled with real numbers |
| report.tex + report.pdf | ✅ 11-page two-column paper, publication-quality figures |
| Secondary breakdown (B2B) | ✅ Added — CoT stable, agents degrade on B2B |
| Streamlit UI improvements | ✅ Market divergence, similar games, info density scatter, ablation chart |
| Research Evaluation page | ✅ Info density plot + ablation bar chart added |
| `nba_backtest.py` | ✅ `--methods` flag, `load_dotenv()`, B2B analysis |
| `nba_agent.py` | ✅ `load_dotenv()` |
| Duplicate `nba_streamlit_app.py` | ✅ Deleted — `Matchup_Analysis.py` is canonical |
| Sample data | ✅ `data/sample/` has example CSVs for reproducibility |

### Key eval results (headline numbers for presentation/report)

| Method | Brier | Accuracy | ECE |
|---|---|---|---|
| **CoT (winner)** | **0.228** | **61.4%** | **0.068** |
| Multi-agent debate | 0.283 | 52.3% | 0.167 |
| Single agent | 0.297 | 52.8% | 0.205 |
| Random baseline | 0.250 | — | — |

**Ablation top findings:** H2H is most impactful source (Brier delta +0.010 when disabled), followed by stats (+0.007) and vector_store (+0.006). Sources without historical snapshots show near-zero deltas.

**Cost:** $26.09 total, 8,356 API calls, ~$0.20/game across all 3 methods.

### What is NOT done (Tanish + team)

| Item | Owner | Notes |
|---|---|---|
| **Streamlit Cloud deployment** | Tanish | share.streamlit.io → connect repo → `Matchup_Analysis.py` → paste API keys in Secrets. Takes 10 min. Critical for demo grade. |
| React + FastAPI UI merge | Tanish | Branch `claude/inspiring-curie-905ab0` has a complete React frontend + FastAPI backend. Zero conflicts with current main. See branch README for setup. |
| Manual report-quality scoring | All 3 | Scores already filled in `data/report_quality_scoring.md` — review and adjust if needed |
| Per-member report sections | All 3 | `report.tex` is the source — Aaditya's sections done. Pranav: data pipeline + vector store + CoT sections. Tanish: app, deployment, report quality sections. |
| Market baseline | — | Not deliverable — Kaggle odds CSV schema mismatch, 0 matches. Documented in report Limitations. |
| Star player absence breakdown | — | Not deliverable — no per-day injury history. Documented in report Limitations. |

---

---

## 1. Proposal compliance

### Research Questions
| RQ | Status |
|---|---|
| RQ1 — info density vs prediction quality | 🟡 Infrastructure done, eval pending |
| RQ2 — multi-agent vs CoT | 🟡 Infrastructure done, eval pending |
| RQ3 — which sources matter | 🟡 Infrastructure done, ablation pending |

### Deliverables
| # | Deliverable | Status |
|---|---|---|
| 1 | Agentic RAG pipeline | ✅ Done |
| 2 | Multi-agent debate (3 agents, iterative per Du et al.) | ✅ Done |
| 3 | CoT baseline | ✅ Done |
| 4 | Evaluation (Brier, calibration, info density, ablation, report quality) | 🟡 Code done, results pending |
| 5 | Deployed Streamlit app | 🟡 Local works, cloud deploy pending |
| 6 | GitHub repo + docs + example reports | 🟡 Repo + docs done, example reports pending |

### Data Sources
| Source | Status |
|---|---|
| `nba_api` (game/team/player stats) | ✅ 11,465 games × 9 seasons (2017-18 to 2025-26 incl. playoffs) |
| `nbainjuries` package | ✅ 12 active injuries pulled (needs arm64 JDK; JAVA_HOME set to brew openjdk@18) |
| The Odds API + Kaggle | ✅ 183 live odds; Kaggle loader ready |
| Reddit | ✅ via **public JSON endpoint** (1,567 comments). Proposal said PRAW; OAuth-app path was blocked, public JSON achieves the same role |
| ESPN/CBS news RSS | ✅ 81 articles. Bleacher Report not yet added (proposal lists it; ~30 min add) |
| ChromaDB vector store | ✅ 22,930 game documents indexed |

### Evaluation methods
| Method | Status |
|---|---|
| Brier + calibration curves | 🟡 code done, run pending |
| Info density vs prediction quality (RQ1 plot) | 🟡 code done, run pending |
| Ablation (per-source Brier delta) | 🟡 `--disable-source` flag built, 7-run sweep pending |
| Report quality (20-30 hand-scored, 4 criteria) | ❌ pending eval results |
| Secondary breakdowns (B2B, star absences, home/away) | 🟡 columns exist, slicing pending |

---

## 2. What's left

| # | Task | Owner | Effort |
|---|------|-------|--------|
| 1 | Run 150-game backtest (all 3 methods, Haiku) | Aaditya | ~14-17h, ~$10 |
| 2 | Run 7 ablation sweeps | Aaditya | ~2-3h, ~$2 |
| 3 | Update RESULTS.md Section 5 with real numbers | Aaditya | ~1h |
| 4 | Manual report-quality scoring (20 reports, ~7 each) | All 3 | ~1.5h each |
| 5 | Streamlit UI features (odds compare, divergence flag, vector retrievals, info density plots, ablation viz, caching) | Tanish | ~5-8h |
| 6 | Streamlit Cloud deployment | Tanish | ~1h |
| 7 | Per-member report sections | All 3 | ~2-3h each |
| 8 | (Optional) Bleacher Report RSS to news pipeline | Anyone | ~30 min |

---

## 3. Tanish — UI lane

### What you need to do

1. **Pick canonical Streamlit file.** `nba_streamlit_app.py` (original) vs `Matchup_Analysis.py` (you added, ~2067 lines). Diff, pick one, delete the other.
2. **Add odds comparison + divergence flag.** Per-bookmaker table from `tool_get_odds()`. Compute `divergence = abs(agent_home_prob - market_consensus)`; show callout when ≥0.05.
3. **Surface vector store retrievals.** "Similar past games" section — top 3-5 retrieved games with metadata + outcome. Currently invisible to users.
4. **Caching + secrets.** `@st.cache_data` on data loaders. Create `.streamlit/secrets.toml` mirroring `.env`. Gitignore the secrets file.
5. **(Blocked on Aaditya's eval)** Info density plot on `pages/Research_Evaluation.py` — scatter of any info_density signal vs Brier, segmented by game profile.
6. **(Blocked on Aaditya's ablations)** Ablation results section on eval page — bar chart of per-source Brier delta from `data/backtest_ablation_*.csv`.
7. **Deploy to Streamlit Cloud.** share.streamlit.io → connect repo → configure secrets in their UI.

**Your files:** `nba_streamlit_app.py`, `Matchup_Analysis.py`, `pages/`, `.streamlit/secrets.toml`.
**Don't touch:** `nba_*_pipeline.py`, `nba_vector_store.py`, `nba_agent.py`, `nba_multi_agent.py`, `nba_cot_baseline.py`, `nba_backtest.py`, `nba_cost_logger.py`, `requirements.txt`.

### Pastable Claude Code prompt

```
Read STATUS_AND_HANDOFF.md and RESULTS.md at the repo root, then handle Section 3 (my queue) item by item.

Workflow per item:
- Branch off main: tanish/<short-name>
- One PR per logical commit (split by concern, never mega-commit)
- Always pull before push, never force-push main
- gh pr merge --rebase --delete-branch (no branch protection on main)

Commit style: imperative subject under 70 chars, body explains "previously / now". No AI attribution, no Co-Authored-By, no "Generated with Claude Code" footer. Match Pranav's style — see git log for examples.

Items 5 and 6 are blocked on Aaditya finishing the eval; do everything else first.

Stop and ask me before improvising on architecture.
```

---

## 4. Aaditya — Eval + report sections lane

### What you need to do

1. **Setup (~60 min, one-time):**
   - Clone repo, `python3.12 -m venv .venv`, `pip install -r requirements.txt`
   - `brew install openjdk@18`, then `export JAVA_HOME=/opt/homebrew/opt/openjdk@18/libexec/openjdk.jdk/Contents/Home` (nbainjuries needs arm64 JDK)
   - `cp .env.example .env`, fill in your own `ANTHROPIC_API_KEY`, `ODDS_API_KEY`, `YOUTUBE_API_KEY`
   - Manually download Kaggle dataset: kaggle.com/datasets/erichqiu/nba-odds-and-scores → save to `data/kaggle_odds.csv`

2. **Populate data (~60 min, mostly nba_api rate waits):**
   ```
   .venv/bin/python nba_data_pipeline.py
   .venv/bin/python nba_vector_store.py
   .venv/bin/python nba_news_pipeline.py
   .venv/bin/python nba_reddit_pipeline.py
   .venv/bin/python nba_injury_pipeline.py
   .venv/bin/python nba_odds_pipeline.py
   ```

3. **Smoke (~5 min, ~$0.30):** `python nba_backtest.py --n-games 5 --season 2024-25`. Confirm the cost log at `data/llm_calls.jsonl` is populating and game results print. Stop if it takes >1 hour or all methods fail.

4. **Full eval (~14-17h overnight, ~$10):** `python nba_backtest.py --n-games 150 --season 2024-25`. Run in `nohup` or `tmux`.

5. **7 ablations (~2-3h, ~$2):**
   ```
   for src in youtube news odds injuries vector_store h2h stats; do
     .venv/bin/python nba_backtest.py --n-games 150 --season 2024-25 --disable-source "$src"
   done
   ```

6. **Commit results to a branch + PR + merge:** `data/backtest_predictions.csv`, `data/backtest_summary.csv`, `data/backtest_calibration.csv`, `data/backtest_ablation_*.csv`, `data/backtest_run_metadata.json`, `data/llm_calls.jsonl`.

7. **Update RESULTS.md Section 5** with real numbers from the CSVs. Section 5 has `_TBD_` placeholders for cost, RQ2 comparison, RQ1 correlation, RQ3 ablation deltas, calibration, secondary breakdowns. Pandas one-liners over the CSVs give you each table.

8. **Write your assigned report sections** (per proposal Section 6): "Agent architecture, debate, and evaluation results sections." RESULTS.md is the source of truth for content.

**Your files:** `nba_agent.py`, `nba_multi_agent.py`, `nba_cot_baseline.py`, `nba_backtest.py`, `nba_cost_logger.py`.
**Don't touch:** `nba_*_pipeline.py`, `nba_vector_store.py`, `nba_streamlit_app.py`, `Matchup_Analysis.py`, `pages/`.

### Pastable Claude Code prompt

```
Read STATUS_AND_HANDOFF.md and RESULTS.md at the repo root, then handle Section 4 (my queue) phase by phase.

Workflow per phase:
- Phases 1-2 (setup, data populate) — local, no PR
- Phase 6 onward — branch off main, PR, gh pr merge --merge or --rebase --delete-branch
- Always pull before push, never force-push main
- Commit style: imperative subject under 70 chars, body explains "previously / now". No AI attribution, no Co-Authored-By, no "Generated with Claude Code" footer. Match Pranav's style — see git log for examples.

If anything fails or any step takes way longer than the time estimate, stop and ask Pranav rather than improvising. The amfid issue Pranav documented (slow Python imports) might bite — if `import pandas` takes more than a minute, recreate the venv.

Don't run any other paid LLM calls beyond what these phases need.
```
