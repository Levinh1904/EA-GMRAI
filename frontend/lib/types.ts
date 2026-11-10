// Domain types matching the GMRAI FastAPI backend contract (all under /api/v1).

export type Timeframe = 'M5' | 'M15' | 'H1';

export type Regime =
  | 'SIDEWAYS'
  | 'TREND_UP'
  | 'TREND_DOWN'
  | 'EARLY_TREND_UP'
  | 'EARLY_TREND_DOWN'
  | 'TRANSITION'
  | 'HIGH_VOLATILITY'
  | 'UNKNOWN';

export type Permission = 'BUY_ONLY' | 'SELL_ONLY' | 'NO_TRADE';

export type JobStatus = 'scheduled' | 'running' | 'done' | 'failed' | 'cancelled';

export type ModelStatus =
  | 'training'
  | 'validating'
  | 'candidate'
  | 'approved'
  | 'rejected'
  | 'archived';

// ---------- Auth ----------

export interface LoginResponse {
  access_token: string;
  token_type: string;
  username: string;
  role: string;
}

export interface User {
  id: number;
  username: string;
  role: string;
  is_active: boolean;
}

// ---------- Regime ----------

export type ProbMap = Record<string, number>;

export interface Probabilities {
  hmm_semantic?: ProbMap;
  rf?: ProbMap;
  combined?: ProbMap;
}

export interface RegimeLatest {
  symbol: string;
  timeframe: string;
  timestamp: string;
  regime: Regime;
  confidence: number;
  probabilities: Probabilities;
  model_version: number;
  feature_version: string;
  data_timestamp: string;
  data_source: string;
  expiry: string;
  reason_codes: string[];
  permission: Permission;
  data_age_minutes: number;
}

export interface RegimeHistoryEntry {
  ts: string;
  regime: Regime;
  confidence: number;
  probabilities?: Probabilities;
  reason_codes?: string[];
  permission?: Permission;
  model_version_id?: number;
}

export interface RegimeHistoryResponse {
  history: RegimeHistoryEntry[];
}

// ---------- Market ----------

export interface Candle {
  ts: string;
  open: number;
  high: number;
  low: number;
  close: number;
  tick_volume: number;
  spread: number;
  source: string;
}

export interface CandlesResponse {
  total: number;
  limit: number;
  offset: number;
  candles: Candle[];
}

export interface MarketLatest {
  symbol: string;
  latest: Partial<Record<Timeframe, Candle | null>>;
}

// ---------- Stats ----------

export interface CandleStats {
  count: number;
  latest_ts: string | null;
}

export interface FreshnessInfo {
  age_minutes: number;
  stale: boolean;
  threshold_minutes: number;
}

export interface SyncLog {
  id: number;
  collector_id: string;
  timeframe: string;
  finished_at: string;
  status: string;
  inserted: number;
  updated: number;
  received?: number;
  message?: string | null;
}

export interface QualityReport {
  id: number;
  timeframe: string;
  checked_at: string;
  total_candles: number;
  missing_count: number;
  duplicate_count: number;
  gap_count: number;
  bad_candle_count: number;
  stale_ts: string | null;
  stale: boolean;
}

export interface ActiveModelRef {
  id?: number;
  model_type?: string;
  model_id?: number;
  version?: number;
  status?: string;
}

export interface DashboardStats {
  symbol: string;
  generated_at: string;
  regime: RegimeLatest;
  candles: Partial<Record<Timeframe, CandleStats>>;
  data_freshness: Partial<Record<Timeframe, FreshnessInfo>>;
  last_sync: SyncLog[];
  last_quality_reports: QualityReport[];
  active_models: { hmm: ActiveModelRef[]; random_forest: ActiveModelRef[] };
}

// ---------- Models ----------

export interface VariantResult {
  engine_params?: Record<string, unknown>;
  validation_opt_score?: number;
  test_macro_f1?: number;
  test_accuracy?: number;
  false_trend_rate?: number;
  [key: string]: unknown;
}

export interface StateMapEvidence {
  regime?: string;
  reason?: string;
  evidence?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface HmmArtifact {
  model_type?: string;
  params?: {
    startprob?: number[];
    transmat?: number[][];
    [key: string]: unknown;
  };
  state_mapping?: Record<string, StateMapEvidence>;
  scaler_mean?: number[];
  scaler_std?: number[];
  feature_columns?: string[];
  meta?: Record<string, unknown>;
}

export interface ModelMetrics {
  train_loglik?: number;
  val_loglik?: number;
  engine_params?: Record<string, unknown>;
  chosen_variant?: string;
  variant_results?: Record<string, VariantResult>;
  state_mapping?: unknown;
  onnx_parity?: Record<string, unknown>;
  test_macro_f1?: number;
  test_accuracy?: number;
  false_trend_rate?: number;
  hmm_model_id?: number;
  rf_model_id?: number;
  auto_approved?: boolean;
  [key: string]: unknown;
}

export interface ModelRow {
  version_id: number;
  model_type: string;
  model_id: number;
  version: number;
  status: ModelStatus;
  metrics: ModelMetrics | null;
  created_at: string;
  has_artifact: boolean;
}

export interface ModelListResponse {
  models: ModelRow[];
}

export interface ModelDetail {
  version_id: number;
  model_type: string;
  model_id: number;
  version: number;
  status: ModelStatus;
  metrics: ModelMetrics | null;
  artifact_path: string;
  created_at: string;
}

// ---------- Training ----------

export interface TrainingRun {
  id: number;
  model_type: string;
  params: Record<string, unknown>;
  feature_version: string;
  status: JobStatus;
  metrics: ModelMetrics | null;
  error: string | null;
  started_at: string | null;
  finished_at: string | null;
}

export interface TrainingRunListResponse {
  runs: TrainingRun[];
}

export interface TrainingStartRequest {
  hmm_n_states?: number;
  hmm_n_init?: number;
  seed?: number;
  train_frac?: number;
  val_frac?: number;
  rf_horizon?: number;
  up_threshold_atr?: number;
  weight_hmm?: number;
}

export interface ScheduleResponse {
  status: string;
  job_id: number;
}

// ---------- Backtesting ----------

export interface StatMeanStd {
  mean: number;
  std: number;
}

export interface VariantComparison {
  macro_f1?: StatMeanStd;
  false_trend_rate?: StatMeanStd;
  [key: string]: unknown;
}

export interface BacktestMetrics {
  n_folds?: number;
  chosen_variant?: string;
  variant_comparison?: Record<string, VariantComparison>;
  [key: string]: unknown;
}

export interface BacktestConfig {
  initial_train?: number;
  test_size?: number;
  step?: number | null;
  embargo?: number;
  hmm_n_states?: number;
  hmm_n_init?: number;
  seed?: number;
  rf_horizon?: number;
  up_threshold_atr?: number;
  cost_usd?: number;
  max_hold?: number;
  min_train?: number;
  val_frac?: number;
  [key: string]: unknown;
}

export interface BacktestRun {
  id: number;
  name: string;
  status: JobStatus;
  config: BacktestConfig;
  metrics: BacktestMetrics | null;
  error: string | null;
  started_at: string | null;
  finished_at: string | null;
}

export interface BacktestListResponse {
  runs: BacktestRun[];
}

export interface BacktestStartRequest {
  name: string;
  initial_train: number;
  test_size: number;
  embargo: number;
  hmm_n_states: number;
  hmm_n_init: number;
  rf_horizon: number;
  up_threshold_atr: number;
  cost_usd: number;
  max_hold: number;
}

// ---------- Data center ----------

export interface IngestStatusResponse {
  recent_syncs: SyncLog[];
}

export interface QualityReportResponse {
  reports: QualityReport[];
}

export interface QualityRunResponse {
  status: string;
  results: Record<string, Record<string, unknown>>;
}

// ---------- System ----------

export interface SystemJob {
  id: number;
  job_type: string;
  status: string;
  error: string | null;
  finished_at: string | null;
}

export interface SystemStatus {
  candles_total: number;
  active_models: ActiveModelRef[];
  recent_jobs: SystemJob[];
}

export interface SystemLog {
  id: number;
  level: string;
  component: string;
  message: string;
  created_at: string;
}

export interface SystemLogsResponse {
  logs: SystemLog[];
}

// ---------- History (Historical Market Regime Analyzer) ----------

export type HistoryRunStatus = JobStatus | 'pending';

export interface HistoryRun {
  id: number;
  symbol: string;
  timeframe: string;
  status: HistoryRunStatus;
  data_source: string | null;
  bar_count: number | null;
  segment_count: number | null;
  data_start: string | null;
  data_end: string | null;
  hmm_model_version_id: number | null;
  rf_model_version_id: number | null;
  error: string | null;
  created_at: string;
  finished_at: string | null;
}

export interface HistoryRunListResponse {
  runs: HistoryRun[];
}

export interface HistoryRunDetail extends HistoryRun {
  config: Record<string, unknown> | null;
  feature_version: string | null;
  started_at: string | null;
}

export type ReferenceRegime =
  | 'TREND_UP'
  | 'TREND_DOWN'
  | 'SIDEWAYS'
  | 'TRANSITION'
  | 'HIGH_VOLATILITY'
  | 'UNKNOWN';

export interface HistoryBar {
  ts: string;
  regime: Regime | null;
  confidence: number;
  permission: Permission | null;
  hmm_state: number | null;
  hmm_posterior: number[] | null;
  rf_probs: { TREND_DOWN: number; SIDEWAYS: number; TREND_UP: number } | null;
  reason_codes: string[] | null;
  open: number;
  high: number;
  low: number;
  close: number;
  atr_ratio: number | null;
  adx_norm: number | null;
  efficiency_ratio: number | null;
  h1_trend_context: number | null;
  m5_momentum: number | null;
  // Reference engine (independent rule-based classifier, versioned) — per bar.
  reference_regime: ReferenceRegime | null;
  reference_reason: string | null;
  di_gap: number | null;
  ema_slope: number | null;
  ref_channel_high: number | null;
  ref_channel_low: number | null;
  ref_displacement: number | null;
}

export interface HistoryBarsResponse {
  run_id: number;
  total: number;
  limit: number;
  offset: number;
  bars: HistoryBar[];
}

export interface HistorySegment {
  id: number;
  run_id?: number;
  segment_index: number;
  regime: Regime;
  start_ts: string;
  end_ts: string;
  bar_count: number;
  duration_minutes: number;
  start_price: number;
  end_price: number;
  high_price: number;
  low_price: number;
  net_change: number;
  mfe: number;
  mae: number;
  atr_mean: number;
  adx_mean: number;
  efficiency_mean: number;
  hmm_probs: Record<string, number> | null;
  confidence_mean: number;
  model_version_id: number | null;
  split_reason: string | null;
  range_touches_high: number;
  range_touches_low: number;
}

export interface HistorySegmentsResponse {
  run_id: number;
  total: number;
  limit: number;
  offset: number;
  segments: HistorySegment[];
}

export interface RegimeDurationStat {
  occurrences: number;
  total_minutes: number;
  occupancy_pct: number | null;
  mean_minutes: number | null;
  median_minutes: number | null;
  longest_minutes: number | null;
  shortest_minutes: number | null;
  p25: number | null;
  p75: number | null;
  p90: number | null;
  avg_per_day: number | null;
}

export interface DurationStatsResponse {
  run_id: number;
  regimes: Record<string, RegimeDurationStat>;
  total_transitions: number;
}

export interface TrendStat {
  count: number;
  total_minutes: number;
  mean_minutes: number;
  median_minutes: number;
  longest_minutes: number;
  shortest_minutes: number;
  mean_speed_usd_per_min: number;
  mean_net_change: number;
  mean_mfe: number;
  mean_mae: number;
  mean_atr_ratio: number;
  mean_adx_norm: number;
  mean_efficiency: number;
  mean_bar_count: number;
}

export interface TrendsStatsResponse {
  run_id: number;
  method: string;
  strength_note: string | null;
  TREND_UP: TrendStat;
  TREND_DOWN: TrendStat;
  strength: {
    score_formula: string | null;
    q25: number | null;
    q75: number | null;
    distribution: Record<string, number>;
  };
}

export interface SidewaysStatsResponse {
  run_id: number;
  bucket_note: string | null;
  buckets: Record<string, number>;
  count: number;
  total_minutes: number;
  mean_minutes: number;
  median_minutes: number;
  longest_minutes: number;
  shortest_minutes: number;
  mean_range_width: number;
  mean_range_high: number;
  mean_range_low: number;
  mean_atr_ratio: number;
  mean_adx_norm: number;
  mean_efficiency: number;
  mean_touches_high: number;
  mean_touches_low: number;
  breakouts: number;
  false_breakouts: number;
  false_breakout_rule: string | null;
  next_regime_distribution: Record<string, number>;
}

export interface EarlyTrendStat {
  signals: number;
  confirmed: number;
  wrong_direction: number;
  no_trend: number;
  no_data: number;
  success_rate_pct: number;
  false_rate_pct: number;
  mean_detection_delay_bars: number;
  window_bars: number;
}

export interface EarlyTrendStatsResponse {
  run_id: number;
  EARLY_TREND_UP: EarlyTrendStat;
  EARLY_TREND_DOWN: EarlyTrendStat;
  note: string | null;
}

export interface TransitionsStatsResponse {
  run_id: number;
  regimes: string[];
  counts: Record<string, Record<string, number>>;
  rates: Record<string, Record<string, number>>;
  mean_source_duration_minutes: Record<string, number>;
  total_transitions: number;
  note: string | null;
}

export interface PeriodRow {
  period_start: string;
  trend_up_minutes: number;
  trend_down_minutes: number;
  sideways_minutes: number;
  early_trend_minutes: number;
  transition_minutes: number;
  high_volatility_minutes: number;
  unknown_minutes: number;
  segments: number;
  dominant_regime: Regime | null;
  range_usd: number;
}

export interface PeriodsStatsResponse {
  run_id: number;
  period: string;
  rows: PeriodRow[];
}

export interface MultiTfSample {
  ts: string;
  m15_regime: Regime;
  m5_timing: string;
  h1_context: string;
  agreement: string;
}

export interface MultiTfStatsResponse {
  run_id: number;
  thresholds: { h1_trend_context: number; m5_momentum: number };
  note: string | null;
  counts: Record<string, number>;
  occupancy_pct: Record<string, number>;
  mean_duration_minutes: Record<string, number>;
  sample: MultiTfSample[];
}

export interface CompareVsRunResponse {
  mode: string;
  names: string[];
  overlap_bars: number;
  agreement_rate: number;
  confusion_counts: Record<string, Record<string, number>>;
  duration_minutes: Record<string, Record<string, number>>;
  segment_counts: Record<string, number>;
}

export interface CompareVsReferenceResponse {
  run_id: number;
  mode: string;
  reference_note: string | null;
  classification: {
    accuracy: number;
    macro_f1: number;
    per_class: Record<string, { precision: number; recall: number; f1: number }>;
    confusion_matrix: number[][];
    classes: string[];
  };
  false_trend_rate: number;
  detection: {
    trend_up: { windows: number; missed: number; mean_delay_bars: number; max_delay_bars: number };
    trend_down: { windows: number; missed: number; mean_delay_bars: number; max_delay_bars: number };
  };
}

// ---------- Reference engine comparison (stats/vs_reference) ----------

export interface DetectionWindow {
  windows: number;
  missed: number;
  mean_delay_bars: number | null;
  max_delay_bars: number | null;
}

export interface DurationDisagreement {
  n_intervals: number;
  mean_abs_diff_minutes: number;
}

export interface VsReferenceStats {
  run_id: number;
  reference_version: string | null;
  reference_config: Record<string, unknown> | null;
  note: string | null;
  overlap_bars: number;
  agreement_rate: number;
  classes: string[];
  confusion_counts: Record<string, Record<string, number>>;
  per_class: Record<
    string,
    { precision: number | null; recall: number | null; f1: number | null; support: number }
  >;
  macro_f1: number | null;
  false_trend_rate: number | null;
  false_sideways_rate: number | null;
  missed_sideways_rate: number | null;
  detection: {
    trend_up: DetectionWindow;
    trend_down: DetectionWindow;
  };
  boundaries: {
    tolerance_bars: number;
    ai_boundaries: number;
    reference_boundaries: number;
    matched: number;
    missed: number;
    extra: number;
    mean_abs_distance_bars: number | null;
  };
  /** Regime -> either the flat mean (minutes) or a detailed interval object. */
  duration_disagreement_minutes: Record<string, number | DurationDisagreement>;
}

// ---------- Future outcomes (stats/outcomes) ----------

export interface OutcomeBucket {
  n: number;
  mean_fwd_return: number | null;
  win_rate_pct: number | null;
  mean_mfe: number | null;
  mean_mae: number | null;
  pct_up: number | null;
  pct_down: number | null;
  pct_flat: number | null;
  pct_in_range: number | null;
}

export interface OutcomeStats {
  run_id: number;
  note: string | null;
  horizons: number[];
  /** Key: "ai_regime:TREND_UP" / "reference_regime:TREND_UP" -> horizon ("12") -> bucket. */
  per_regime: Record<string, Record<string, OutcomeBucket>>;
}

export interface ScheduleRunResponse {
  status: string;
  run_id: number;
}
