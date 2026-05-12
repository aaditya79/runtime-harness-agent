export interface Team {
  name: string;
  abbr: string;
  logo: string;
}

export interface UpcomingGame {
  game_id: string;
  home_team: string;
  away_team: string;
  home_abbr: string | null;
  away_abbr: string | null;
  commence_time: string;
  commence_time_label: string;
  label: string;
}

export interface TeamStats {
  team?: string;
  season?: string;
  season_record?: string;
  last_10_record?: string;
  avg_points_last_10?: number;
  avg_fg_pct_last_10?: number;
  avg_fg3_pct_last_10?: number;
  avg_rebounds_last_10?: number;
  avg_assists_last_10?: number;
  avg_turnovers_last_10?: number;
  avg_plus_minus_last_10?: number;
  last_game?: {
    date: string;
    matchup: string;
    result: "W" | "L";
    points: number;
  };
  back_to_back_today?: number;
}

export interface Injury {
  team: string;
  player: string;
  position: string;
  status: string;
  est_return: string;
  comment: string;
}

export interface TeamSentiment {
  team?: string;
  article_count?: number;
  avg_sentiment?: number;
  positive_article_count?: number;
  negative_article_count?: number;
  sentiment_label?: string;
}

export interface SimilarGame {
  game_description: string;
  metadata: Record<string, any>;
  similarity_score?: number;
  distance?: number;
}

export interface MatchupBundle {
  home_abbr: string;
  away_abbr: string;
  home_logo: string;
  away_logo: string;
  home_stats: TeamStats;
  away_stats: TeamStats;
  home_injuries: Injury[];
  away_injuries: Injury[];
  home_sentiment: TeamSentiment;
  away_sentiment: TeamSentiment;
}

export interface MarketConsensus {
  available: boolean;
  market_home_prob?: number;
  market_away_prob?: number;
  books_sampled?: number;
  bookmakers?: string[];
}

export type AnalysisMode = "single_agent" | "multi_agent" | "cot";

export interface KeyFactor {
  factor: string;
  impact: "favors_home" | "favors_away" | "neutral" | string;
  importance: "high" | "medium" | "low" | string;
  source_agent?: string;
  // Optional enrichment fields added by the FastAPI backend after parsing.
  influence_score?: number; // 0..100
  metric_label?: string; // e.g. "Net rating Δ"
  metric_value?: string; // e.g. "+8.4"
  category?: string;
}

export interface AgentAnalysis {
  prediction?: { home_win_prob?: number; away_win_prob?: number };
  confidence?: string;
  key_points?: string[];
  reasoning?: string;
  market_implied?: { home_win_prob?: number; away_win_prob?: number };
  value_spots?: string[];
}

export interface ParsedReport {
  game?: string;
  date?: string;
  prediction?: { home_win_prob?: number; away_win_prob?: number; confidence?: string };
  synthesized_prediction?: { home_win_prob?: number; away_win_prob?: number; confidence?: string };
  agent_prediction?: { home_win_prob?: number; away_win_prob?: number; confidence?: string };
  market_odds?: any;
  key_factors?: KeyFactor[];
  reasoning?: string;
  value_assessment?: string;
  areas_of_agreement?: string[];
  areas_of_disagreement?: string[];
  agent_predictions?: Record<string, { home?: number; away?: number }>;
}

export interface AnalysisRunResult {
  report: ParsedReport | null;
  raw: any;
  trace: string;
}

export interface BacktestSummaryRow {
  method: string;
  n_games?: number;
  accuracy?: number;
  precision?: number;
  recall?: number;
  f1?: number;
  log_loss?: number;
  brier_score?: number;
  mae_prob?: number;
  avg_confidence?: number;
  avg_gap?: number;
  ece?: number;
}

export interface CalibrationRow {
  method: string;
  bin?: number;
  avg_pred_home_win_prob: number;
  actual_home_win_rate: number;
  count?: number;
}

export interface PredictionRow {
  date: string;
  away_team: string;
  home_team: string;
  method: string;
  home_win_prob: number;
  away_win_prob: number;
  actual_home_win: number;
  correct: number;
  confidence: string;
  brier_score?: number;
  market_home_implied_prob?: number;
  market_away_implied_prob?: number;
  info_density_context_tokens?: number;
  info_density_vector_hits?: number;
  info_density_youtube_comments?: number;
  info_density_news_articles?: number;
}

export interface AblationRow {
  source: string;
  ablation_brier: number;
  baseline_brier: number;
  brier_delta: number;
  n_games: number;
}

export interface RoiBet {
  date: string;
  away_team: string;
  home_team: string;
  method: string;
  side_bet: string;
  edge: number;
  model_confidence: number;
  market_home_implied_prob: number;
  market_away_implied_prob: number;
  won: number;
  units: number;
  cum_units: number;
}

export interface RoiSummaryRow {
  method: string;
  n_bets: number;
  win_rate: number;
  total_units: number;
  avg_units_per_bet: number;
  avg_edge: number;
  avg_model_confidence: number;
  roi: number;
}

export interface RoiResponse {
  available: boolean;
  summary: RoiSummaryRow[];
  bets: RoiBet[];
  reason?:
    | "ok"
    | "predictions_missing"
    | "predictions_empty"
    | "market_columns_missing"
    | "market_data_missing"
    | "no_rows_after_method_filter"
    | "no_qualifying_bets";
  message?: string;
  diagnostics?: Record<string, unknown>;
}

export type PipelineName = "data" | "injuries" | "odds" | "news" | "vector_store";

export interface PipelineStatus {
  name: PipelineName;
  title: string;
  description: string;
  eta: string;
  status: "idle" | "running" | "done" | "error" | "timeout";
  started_at: number | null;
  finished_at: number | null;
  last_run_at: number | null;
  exit_code: number | null;
  duration_seconds: number | null;
  cooldown_remaining: number;
  produces: string[];
  produces_present: { path: string; exists: boolean }[];
  output_tail: string[];
}

export interface PipelineStartResponse {
  ok: boolean;
  error?: string;
  rate_limited?: boolean;
  cooldown_remaining?: number;
  status?: PipelineStatus;
}

export interface BacktestJobStatus {
  status: "idle" | "running" | "done" | "error" | "timeout";
  params: { n_games: number; season: string; min_history: number } | null;
  started_at: number | null;
  finished_at: number | null;
  duration_seconds: number | null;
  exit_code: number | null;
  output_tail: string[];
}

export interface BacktestStartResponse {
  ok: boolean;
  error?: string;
  status: BacktestJobStatus;
}
