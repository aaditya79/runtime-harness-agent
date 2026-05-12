# MatchOdds AI · Frontend

React + TypeScript + Vite + Tailwind frontend for MatchOdds AI. Talks to the FastAPI backend (`/backend`) over REST and Server-Sent Events.

## Stack

- **Vite + React 18 + TypeScript** — fast dev loop, strict typing.
- **Tailwind CSS** — design tokens for the sports-betting palette (deep navy, orange ember, court blue, win green, loss red).
- **TanStack Query** — server-state cache for all REST data (auto-refetched on game change).
- **React Router** — three pages: Matchup, Research, ROI Simulation.
- **Recharts** — calibration, comparison, ablation, ROI bars and lines.
- **Lucide React** — icons.
- **Custom SSE hook** — streams the live agent trace using `fetch` + a manual SSE parser (browser `EventSource` is GET-only).

## Layout

```
frontend/
├── index.html
├── vite.config.ts            # /api → http://localhost:8000 dev proxy
├── tailwind.config.js        # palette + animations
├── src/
│   ├── main.tsx              # React + Router + QueryClient bootstrap
│   ├── App.tsx               # route table
│   ├── index.css             # Tailwind layers + design tokens
│   ├── lib/
│   │   ├── api.ts            # typed API client + streamAnalysis()
│   │   └── utils.ts          # formatters, prediction parsing
│   ├── hooks/
│   │   └── useStreamingAnalysis.ts
│   ├── components/
│   │   ├── Layout.tsx        # nav, footer, model status
│   │   ├── Panel.tsx         # glass card primitive
│   │   ├── StatChip.tsx
│   │   ├── ProbabilityRing.tsx
│   │   ├── Bar.tsx
│   │   ├── GamePicker.tsx
│   │   ├── AnalysisModePicker.tsx
│   │   ├── MatchupHeader.tsx
│   │   ├── TeamSnapshot.tsx
│   │   ├── InjurySummary.tsx
│   │   ├── SentimentSummary.tsx
│   │   ├── PredictionVisuals.tsx
│   │   ├── KeyFactors.tsx
│   │   ├── SimilarGames.tsx
│   │   ├── MarketDivergence.tsx
│   │   ├── AgentBreakdown.tsx
│   │   ├── AgreementCards.tsx
│   │   ├── ReasoningCards.tsx
│   │   ├── FinalVerdict.tsx
│   │   ├── LiveTrace.tsx
│   │   ├── AnalysisReport.tsx
│   │   └── CompareCards.tsx
│   ├── pages/
│   │   ├── MatchupPage.tsx        # main matchup analysis flow
│   │   ├── ResearchPage.tsx       # backtest dashboard (calibration, ablations, info density)
│   │   └── SimulationPage.tsx     # flat-stake ROI simulator
│   └── types/index.ts             # API + report shapes
└── public/favicon.svg
```

## Setup

```bash
cd frontend
npm install
```

The dev server proxies `/api` to `http://localhost:8000`, so start the backend first.

## Run

```bash
# Terminal 1
cd backend && ./run.sh

# Terminal 2
cd frontend && npm run dev
```

App opens at `http://localhost:5173`.

## Build

```bash
npm run build       # tsc -b && vite build → dist/
npm run preview     # serve the production build
```

## Pages

### Matchup (`/`)
- Live upcoming-games picker driven by `data/odds_live.csv`.
- Team snapshot, injury cards, media sentiment, market consensus, similar past matchups.
- Mode picker: **Multi-Agent Debate**, **Single Agent**, **Chain-of-Thought**, **Compare All**.
- Live SSE trace pane with status pill + auto-scrolling stdout.
- Result render: probability rings, market divergence flag, key factors, agent breakdown (multi-agent), agreement / disagreement cards, reasoning + value assessment, final verdict.
- "Compare All" runs the three modes sequentially and renders side-by-side ROI-style cards, then individual report blocks.
- Download buttons emit a JSON report (single mode) or a bundled comparison.

### Research (`/research`)
- Backtest controls (n_games / season / min_history) — runs `nba_backtest.py` via the backend subprocess endpoint.
- Run-health card from `data/backtest_run_metadata.json`.
- Per-method headline metrics with selectable primary metric.
- Bar comparison across methods for any available metric.
- Calibration curves (Recharts line chart, perfect-calibration diagonal).
- Ablation per-source Brier delta bars (RQ3) when the ablation files exist.
- Information density vs Brier scatter (RQ1) when info-density columns are present.
- Prediction-level inspector with method + correctness filters.

### Simulation (`/simulation`)
- Filters: method, edge threshold, allowed side, min model confidence.
- Best-ROI / most-units / win-rate / most-bets stat cards.
- Method-level table with ROI, win rate, total units, average edge.
- ROI bar chart, cumulative units line chart, simulated bets table.
- Reads `/api/backtest/simulate`, which mirrors the original Streamlit ROI logic.

## Design system

Colour tokens live in `tailwind.config.js`:

- **`bg`** family — deep slate canvas (panels, panel-2, lines)
- **`accent`** — orange ember (the primary brand colour)
- **`court`** — court blue (neutral / data emphasis)
- **`win` / `loss` / `warn`** — outcome semantics
- Background grid + radial accents are layered in `index.css`

Reusable Tailwind component classes are defined under `@layer components` in `index.css` (`.panel`, `.btn`, `.btn-primary`, `.input`, `.chip`, etc.). The aesthetic stays minimal but sports-leaning — animated probability rings, glass cards over a subtle court grid, gradient glows under sticky headers.

## Streaming

The browser `EventSource` API only supports GET. To stream a POST body, `lib/api.ts` calls `fetch` with the analysis payload, then parses `text/event-stream` chunks (`\n\n`-delimited) and decodes each `data:` line as JSON. The `useStreamingAnalysis` hook owns the abort controller, line buffer, and final result.

## Talking to the backend

The frontend never imports from the existing Python files directly. Everything flows through the FastAPI surface, which keeps the Streamlit app, pipelines, and agents completely unchanged.
