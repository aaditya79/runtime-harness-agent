/**
 * Thin client around the FastAPI backend. The dev server proxies /api/* to
 * port 8000, so all calls here are relative.
 */

import type {
  AblationRow,
  AnalysisMode,
  AnalysisRunResult,
  BacktestJobStatus,
  BacktestStartResponse,
  BacktestSummaryRow,
  CalibrationRow,
  Injury,
  MarketConsensus,
  MatchupBundle,
  ParsedReport,
  PipelineName,
  PipelineStartResponse,
  PipelineStatus,
  PredictionRow,
  RoiResponse,
  SimilarGame,
  Team,
  TeamSentiment,
  TeamStats,
  UpcomingGame,
} from "@/types";

const API_ROOT = (import.meta.env.VITE_API_BASE ?? "").replace(/\/$/, "");
const BASE = `${API_ROOT}/api`;

async function get<T>(path: string, params?: Record<string, string | number | undefined>): Promise<T> {
  const url = new URL(BASE + path, window.location.origin);
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== null && v !== "") {
        url.searchParams.set(k, String(v));
      }
    }
  }
  const res = await fetch(url.toString());
  if (!res.ok) {
    throw new Error(`GET ${path} failed: ${res.status}`);
  }
  return res.json();
}

async function post<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(BASE + path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(`POST ${path} failed: ${res.status} ${detail}`);
  }
  return res.json();
}

export const api = {
  health: () => get<{ ok: boolean; llm_configured: boolean; llm_label: string }>("/meta/health"),
  teams: () => get<Team[]>("/meta/teams"),

  upcoming: () => get<UpcomingGame[]>("/games/upcoming"),
  matchup: (home: string, away: string) =>
    get<MatchupBundle>("/games/matchup", { home, away }),
  teamStats: (team: string) => get<TeamStats>("/games/team-stats", { team }),
  injuries: (team: string) => get<Injury[]>("/games/injuries", { team }),
  sentiment: (team: string) => get<TeamSentiment>("/games/sentiment", { team }),
  marketConsensus: (home: string, away: string) =>
    get<MarketConsensus>("/games/market-consensus", { home, away }),
  similar: (homeAbbr: string, awayAbbr: string) =>
    get<SimilarGame[]>("/games/similar", { home_abbr: homeAbbr, away_abbr: awayAbbr }),

  analysisRun: (req: AnalysisRunRequest) =>
    post<AnalysisRunResult>("/analysis/run", req),

  backtestSummary: () =>
    get<{ summary: BacktestSummaryRow[]; metadata: Record<string, any> }>("/backtest/summary"),
  backtestPredictions: () => get<PredictionRow[]>("/backtest/predictions"),
  backtestCalibration: () => get<CalibrationRow[]>("/backtest/calibration"),
  backtestAblations: () => get<AblationRow[]>("/backtest/ablations"),
  backtestRun: (req: { n_games: number; season: string; min_history: number }) =>
    post<BacktestStartResponse>("/backtest/run", req),
  backtestStatus: () => get<BacktestJobStatus>("/backtest/status"),
  pipelinesStatus: () =>
    get<Record<PipelineName, PipelineStatus>>("/pipelines/status"),
  pipelineStart: (name: PipelineName) =>
    post<PipelineStartResponse>(`/pipelines/${name}`),
  // Convenience wrapper used by the Refresh-odds button on the matchup page.
  refreshOdds: () => post<PipelineStartResponse>("/pipelines/odds"),
  simulateRoi: (params: {
    method?: string;
    edge_threshold?: number;
    side_filter?: string;
    min_confidence?: number;
  }) => get<RoiResponse>("/backtest/simulate", params as Record<string, any>),
};

export interface AnalysisRunRequest {
  mode: AnalysisMode;
  home_team: string;
  away_team: string;
  home_abbr: string;
  away_abbr: string;
  game_date: string;
}

/**
 * Open an SSE stream for an analysis. The browser EventSource API only
 * supports GET, so we use fetch + ReadableStream and parse SSE manually.
 */
export interface StreamEvent {
  event: "trace" | "done" | "error";
  line?: string;
  status?: string;
  report?: ParsedReport | null;
  raw?: any;
  trace?: string;
  message?: string;
  mode?: AnalysisMode;
  generated_at?: string;
}

export interface BacktestStreamEvent {
  event: "snapshot" | "line" | "done";
  data: string; // JSON for snapshot/done, raw line for line
}

export async function streamBacktest(
  onEvent: (evt: BacktestStreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(BASE + "/backtest/stream", {
    method: "GET",
    signal,
  });
  if (!response.ok || !response.body) {
    throw new Error(`Backtest stream failed: ${response.status}`);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let idx;
    while ((idx = buffer.indexOf("\n\n")) >= 0) {
      const chunk = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      const dataLines = chunk
        .split("\n")
        .filter((l) => l.startsWith("data:"))
        .map((l) => l.slice(5).trimStart());
      if (dataLines.length === 0) continue;
      try {
        const evt = JSON.parse(dataLines.join("\n")) as BacktestStreamEvent;
        onEvent(evt);
        if (evt.event === "done") return;
      } catch {
        // ignore malformed events
      }
    }
  }
}

export async function streamAnalysis(
  req: AnalysisRunRequest,
  onEvent: (evt: StreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(BASE + "/analysis/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
    signal,
  });

  if (!response.ok || !response.body) {
    throw new Error(`Stream failed: ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let idx;
    while ((idx = buffer.indexOf("\n\n")) >= 0) {
      const chunk = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      // Each chunk is a single SSE event; pull the data: line(s).
      const lines = chunk.split("\n");
      const dataLines = lines
        .filter((l) => l.startsWith("data:"))
        .map((l) => l.slice(5).trimStart());
      if (dataLines.length === 0) continue;
      const payload = dataLines.join("\n");
      try {
        const evt = JSON.parse(payload) as StreamEvent;
        onEvent(evt);
      } catch {
        // ignore malformed events
      }
    }
  }
}
