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
