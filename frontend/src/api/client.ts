import axios from 'axios';

const api = axios.create({ baseURL: '/api', timeout: 120000 });

// ── Analysis types ──────────────────────────────────────────────

export interface Candle {
  t: string;
  o: number;
  h: number;
  l: number;
  c: number;
  v: number;
}

export interface Pivot {
  index: number;
  timestamp: string;
  price: number;
  pivot_type: 'swing_high' | 'swing_low';
}

export interface Leg {
  leg_id: number;
  direction: 'up' | 'down';
  start_timestamp: string;
  end_timestamp: string;
  start_price: number;
  end_price: number;
  absolute_change: number;
  percent_change: number;
  duration_minutes: number;
  duration_bars: number;
}

export interface Summary {
  total_legs: number;
  avg_percent_change: number;
  avg_duration_minutes: number;
  min_percent_change: number;
  max_percent_change: number;
  up_legs_count: number;
  down_legs_count: number;
  median_percent_change: number;
  median_duration_minutes: number;
  up_down_asymmetry: number;
  amplitude_duration_correlation: number;
  net_change_pct: number;
  efficiency_ratio: number;
  realized_vol_pct_per_bar: number;
  max_drawdown_pct: number;
  up_legs_avg_change?: number | null;
  down_legs_avg_change?: number | null;
}

export interface Metadata {
  symbol: string;
  timeframe: string;
  pivot_method: string;
  start_date: string;
  end_date: string;
  total_candles: number;
  total_pivots: number;
  total_legs: number;
  run_timestamp: string;
}

export interface PatternMatch {
  anchor_leg_id: number;
  similarity_score: number;
  match_signature: string;
  next_direction: 'up' | 'down';
  next_change_pct: number;
  next_duration_bars: number;
  horizon_change_pct: number;
  horizon_direction: string;
}

export interface PatternInsight {
  pattern_signature: string;
  pattern_length: number;
  forecast_horizon: number;
  matches_used: number;
  dominant_bias: string;
  bullish_probability: number;
  bearish_probability: number;
  expected_next_change_pct: number;
  expected_horizon_change_pct: number;
  expected_next_duration_bars: number;
  next_change_p25_pct: number | null;
  next_change_p75_pct: number | null;
  horizon_change_p25_pct: number | null;
  horizon_change_p75_pct: number | null;
  base_confidence: number;
  adaptive_confidence: number;
  historical_direction_hit_rate: number;
  historical_horizon_hit_rate: number;
  summary: string;
  matches: PatternMatch[];
}

export interface PatternLearning {
  total_backtests: number;
  direction_hit_rate: number;
  horizon_hit_rate: number;
  baseline_reversion_hit_rate: number;
  baseline_majority_hit_rate: number;
  direction_edge_vs_baseline: number;
  mean_abs_error_next_change_pct: number | null;
  persistent_samples: number;
  persistent_direction_hit_rate: number;
  persistent_horizon_hit_rate: number;
  adaptive_weight: number;
  learning_note: string;
  regime_key: string;
  regime_label: string;
  regime_samples: number;
  regime_direction_hit_rate: number;
  regime_horizon_hit_rate: number;
  median_next_change_pct: number | null;
  p25_next_change_pct: number | null;
  p75_next_change_pct: number | null;
  median_horizon_change_pct: number | null;
  p25_horizon_change_pct: number | null;
  p75_horizon_change_pct: number | null;
  median_next_duration_bars: number | null;
}

export interface MoonPhaseEventPoint {
  timestamp: string;
  phase_name: string;
  phase_code: string;
  phase_fraction: number;
  nearest_pivot_timestamp: string | null;
  nearest_pivot_type: string | null;
  nearest_pivot_price: number | null;
  hours_to_nearest_pivot: number | null;
  aligned_within_window: boolean;
  next_leg_direction: string | null;
  next_leg_percent_change: number | null;
  next_leg_duration_bars: number | null;
}

export interface MoonPhaseInsight {
  phase_window_hours: number;
  total_events: number;
  aligned_events: number;
  alignment_rate: number;
  avg_hours_to_pivot: number | null;
  strongest_phase: string | null;
  strongest_bias: string | null;
  strongest_bias_score: number;
  summary: string;
  events: MoonPhaseEventPoint[];
  phase_stats: Array<{
    phase_name: string;
    occurrences: number;
    aligned_events: number;
    alignment_rate: number;
    swing_high_rate: number;
    swing_low_rate: number;
    bullish_next_leg_rate: number;
    bearish_next_leg_rate: number;
    dominant_bias: string;
  }>;
}

export interface CorrelationObservation {
  timestamp: string;
  btc_normalized: number;
  asset_normalized: number;
  rolling_return_correlation: number | null;
}

export interface AssetCorrelation {
  asset_name: string;
  asset_symbol: string;
  overlap_points: number;
  rolling_window_days: number;
  price_correlation: number | null;
  return_correlation: number | null;
  beta_to_asset: number | null;
  latest_rolling_correlation: number | null;
  latest_relative_strength_pct: number | null;
  summary: string;
  observations: CorrelationObservation[];
}

export interface StructureAnchor {
  timestamp: string;
  price: number;
  role: string;
}

export interface StructureDiscovery {
  discovery_id: string;
  structure_type: string;
  title: string;
  status: string;
  direction: 'bullish' | 'bearish' | 'neutral';
  confidence: number;
  start_timestamp: string;
  end_timestamp: string;
  anchors: StructureAnchor[];
  evidence: string[];
  measurements: Record<string, number | string>;
  invalidation_price: number | null;
  zone_low: number | null;
  zone_high: number | null;
}

export interface DecisionContribution {
  source: string;
  stance: 'invest' | 'divest' | 'neutral';
  weight: number;
  score: number;
  rationale: string;
  detail: string;
  prior_weight?: number | null;
  learned_multiplier?: number | null;
  alignment_samples?: number | null;
}

export interface DecisionInvalidation {
  price: number;
  kind: string;
  flips_toward: string;
  rationale: string;
}

export interface DecisionBandStat {
  action: string;
  count: number;
  avg_forward_return_pct: number | null;
  aligned_rate: number | null;
}

export interface DecisionCheckpoint {
  timestamp: string;
  close: number;
  score: number;
  action: string;
  forward_return_pct: number | null;
}

export interface DecisionWalkForward {
  horizon_bars: number;
  checkpoints: DecisionCheckpoint[];
  band_stats: DecisionBandStat[];
  benchmark_return_pct: number | null;
  note: string;
}

export interface DecisionSourceStat {
  source: string;
  prior_weight: number;
  multiplier: number;
  effective_weight: number;
  samples: number;
  hits: number;
  aligned_rate: number | null;
  live_samples: number;
  replay_samples: number;
}

export interface DecisionGradedItem {
  candle_timestamp: string;
  action: string;
  source: string;
  composite_score: number;
  forward_return_pct: number | null;
  aligned: boolean | null;
  invalidated: boolean;
}

export interface DecisionTrackRecord {
  graded_total: number;
  aligned_total: number;
  alignment_rate: number | null;
  invalidated_total: number;
  live_graded: number;
  replay_graded: number;
  pending: number;
  avg_forward_return_pct: number | null;
  band_stats: DecisionBandStat[];
  source_stats: DecisionSourceStat[];
  recent_graded: DecisionGradedItem[];
  calibration_factor: number;
  note: string;
}

export interface DecisionBrief {
  action: 'strong_invest' | 'invest' | 'hold' | 'divest' | 'strong_divest';
  composite_score: number;
  conviction: number;
  quality: string;
  summary: string;
  contributions: DecisionContribution[];
  invalidations: DecisionInvalidation[];
  conflicts: string[];
  excluded: string[];
  last_price: number | null;
  walk_forward: DecisionWalkForward | null;
  conviction_uncalibrated?: number | null;
  track_record?: DecisionTrackRecord | null;
}

export interface AnalysisResult {
  metadata: Metadata;
  summary: Summary;
  pivots: Pivot[];
  legs: Leg[];
  candles: Candle[];
  candles_resampled: boolean;
  pattern_insight: PatternInsight | null;
  pattern_learning: PatternLearning | null;
  moon_phase_insight: MoonPhaseInsight | null;
  correlations: Record<string, AssetCorrelation>;
  structure_discoveries: StructureDiscovery[];
  forming_leg: Leg | null;
  decision_brief: DecisionBrief | null;
  correlation_errors: Record<string, string>;
}

export interface AppConfig {
  symbol: string;
  timeframe: string;
  lookback_period: string;
  pivot_method: string;
  min_move_pct: number;
  left_bars: number;
  right_bars: number;
  use_atr_filter: boolean;
  atr_period: number;
  atr_multiplier: number;
  enable_pattern_recognition: boolean;
  pattern_length: number;
  pattern_forecast_horizon: number;
  pattern_max_matches: number;
  enable_decision_engine: boolean;
  decision_walk_forward_checkpoints: number;
  enable_decision_memory: boolean;
  enable_adaptive_decision_weights: boolean;
  decision_learning_min_samples: number;
  decision_memory_max_records: number;
  enable_moon_phase_analysis: boolean;
  enable_gold_correlation_analysis: boolean;
  enable_nasdaq_correlation_analysis: boolean;
  enable_oil_correlation_analysis: boolean;
  [key: string]: unknown;
}

export interface Options {
  timeframes: string[];
  pivot_methods: string[];
  sources: string[];
  symbols: string[];
}

export const analysisApi = {
  options: () => api.get<Options>('/options'),
  getConfig: () => api.get<AppConfig>('/config'),
  putConfig: (fields: Partial<AppConfig>) => api.put<AppConfig>('/config', fields),
  analyze: (body: { symbol?: string; timeframe?: string; lookback?: string; config?: Partial<AppConfig> }) =>
    api.post<AnalysisResult>('/analyze', body, { timeout: 300000 }),
  result: () => api.get<AnalysisResult>('/result'),
  exportData: () => api.post<{ files: Record<string, string> }>('/export'),
  insight: () => api.post<{ insight: string }>('/insight', {}, { timeout: 120000 }),
  decisionBrief: () => api.post<{ brief: string }>('/decision/brief', {}, { timeout: 120000 }),
};

// ── Agent types (same shape as the opportunity_pipeline pane) ──

export interface AgentChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

export interface AgentPendingAction {
  tool: string;
  args: Record<string, unknown>;
  summary: string;
}

export interface AgentTraceStep {
  tool: string;
  args: Record<string, unknown>;
  result: string;
  kind: 'read' | 'write';
}

export interface AgentChatResponse {
  type: 'message' | 'confirm';
  content?: string;
  pending?: AgentPendingAction;
  trace?: AgentTraceStep[];
}

export interface AgentStoredMessage {
  id: number;
  role: 'user' | 'assistant';
  content: string;
  created_at: string;
}

export const agentApi = {
  chat: (messages: AgentChatMessage[], confirm?: { tool: string; args: Record<string, unknown> }) =>
    api.post<AgentChatResponse>('/agent/chat', { messages, confirm: confirm ?? null }, { timeout: 300000 }),
  getStatus: () => api.get('/agent/status'),
  getHistory: (limit = 200) =>
    api.get<{ messages: AgentStoredMessage[]; count: number }>(`/agent/chat/history?limit=${limit}`),
  clearHistory: () => api.delete('/agent/chat/history'),
};

export default api;
