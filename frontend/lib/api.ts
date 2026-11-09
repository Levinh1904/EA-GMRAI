// Central API client for the GMRAI FastAPI backend.
// Handles base URL, Bearer token, 401 -> /login redirect, and typed responses.

import type {
  BacktestListResponse,
  BacktestRun,
  BacktestStartRequest,
  CandlesResponse,
  DashboardStats,
  IngestStatusResponse,
  LoginResponse,
  MarketLatest,
  ModelDetail,
  ModelListResponse,
  ModelStatus,
  QualityReportResponse,
  QualityRunResponse,
  RegimeHistoryResponse,
  RegimeLatest,
  ScheduleResponse,
  SystemLogsResponse,
  SystemStatus,
  Timeframe,
  TrainingRunListResponse,
  TrainingStartRequest,
  User,
} from './types';

export const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';
export const TOKEN_KEY = 'gmrai_access_token';

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

export function getAuthToken(): string | null {
  if (typeof window === 'undefined') return null;
  try {
    return window.localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setAuthToken(token: string | null): void {
  if (typeof window === 'undefined') return;
  try {
    if (token) window.localStorage.setItem(TOKEN_KEY, token);
    else window.localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage unavailable — ignore */
  }
}

export function redirectToLogin(): void {
  if (typeof window === 'undefined') return;
  if (window.location.pathname === '/login') return;
  window.location.href = '/login';
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (init?.body) headers.set('Content-Type', 'application/json');
  const token = getAuthToken();
  if (token) headers.set('Authorization', `Bearer ${token}`);

  let res: Response;
  try {
    res = await fetch(`${API_BASE}/api/v1${path}`, { ...init, headers });
  } catch {
    throw new ApiError(0, 'Không thể kết nối tới máy chủ API');
  }

  if (res.status === 401) {
    setAuthToken(null);
    redirectToLogin();
    throw new ApiError(401, 'Phiên đăng nhập đã hết hạn');
  }

  if (!res.ok) {
    let message = `Lỗi máy chủ (HTTP ${res.status})`;
    try {
      const body: unknown = await res.json();
      if (body && typeof body === 'object') {
        if ('detail' in body && body.detail != null) message = String(body.detail);
        else if ('message' in body && body.message != null) message = String(body.message);
      }
    } catch {
      /* non-JSON error body — keep default message */
    }
    throw new ApiError(res.status, message);
  }

  return (await res.json()) as T;
}

/** Generic authenticated GET — usable directly as an SWR fetcher. */
export function apiFetch<T>(path: string): Promise<T> {
  return request<T>(path);
}

export const api = {
  // Auth
  login(username: string, password: string): Promise<LoginResponse> {
    return request<LoginResponse>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    });
  },
  me: () => apiFetch<User>('/auth/me'),

  // Regime
  regimeLatest: () => apiFetch<RegimeLatest>('/regime/latest'),
  regimeHistory: (limit = 500) =>
    apiFetch<RegimeHistoryResponse>(`/regime/history?limit=${limit}`),

  // Market
  candles: (timeframe: Timeframe, limit = 500, offset = 0) =>
    apiFetch<CandlesResponse>(
      `/market/candles?timeframe=${timeframe}&limit=${limit}&offset=${offset}&symbol=XAUUSD`
    ),
  marketLatest: () => apiFetch<MarketLatest>('/market/latest'),

  // Stats
  dashboard: () => apiFetch<DashboardStats>('/stats/dashboard'),

  // Models
  models: (limit = 100, modelType?: string) =>
    apiFetch<ModelListResponse>(
      `/models?limit=${limit}${modelType ? `&model_type=${encodeURIComponent(modelType)}` : ''}`
    ),
  modelDetail: (versionId: number) => apiFetch<ModelDetail>(`/models/${versionId}`),
  setModelStatus: (versionId: number, status: ModelStatus, force = false) =>
    request<{ version_id: number; status: string }>(`/models/${versionId}/status`, {
      method: 'POST',
      body: JSON.stringify({ status, force }),
    }),

  // Training
  trainingRuns: (limit = 20) => apiFetch<TrainingRunListResponse>(`/training/runs?limit=${limit}`),
  startTraining: (params: TrainingStartRequest = {}) =>
    request<ScheduleResponse>('/training/run', {
      method: 'POST',
      body: JSON.stringify(params),
    }),

  // Backtesting
  backtests: (limit = 20) => apiFetch<BacktestListResponse>(`/backtests?limit=${limit}`),
  backtest: (id: number) => apiFetch<BacktestRun>(`/backtests/${id}`),
  startBacktest: (params: BacktestStartRequest) =>
    request<ScheduleResponse>('/backtests', {
      method: 'POST',
      body: JSON.stringify(params),
    }),

  // Data center
  ingestStatus: (limit = 20) => apiFetch<IngestStatusResponse>(`/ingest/status?limit=${limit}`),
  qualityReports: (limit = 20) =>
    apiFetch<QualityReportResponse>(`/quality/reports?limit=${limit}`),
  runQuality: () => request<QualityRunResponse>('/quality/run', { method: 'POST' }),

  // System
  systemStatus: () => apiFetch<SystemStatus>('/system/status'),
  systemLogs: (limit = 100) => apiFetch<SystemLogsResponse>(`/system/logs?limit=${limit}`),
};

/** Download a model artifact/ONNX file through the browser (Bearer-authenticated). */
export async function downloadFile(path: string, filename: string): Promise<void> {
  const headers = new Headers();
  const token = getAuthToken();
  if (token) headers.set('Authorization', `Bearer ${token}`);

  let res: Response;
  try {
    res = await fetch(`${API_BASE}/api/v1${path}`, { headers });
  } catch {
    throw new ApiError(0, 'Không thể kết nối tới máy chủ API');
  }
  if (res.status === 401) {
    setAuthToken(null);
    redirectToLogin();
    throw new ApiError(401, 'Phiên đăng nhập đã hết hạn');
  }
  if (!res.ok) throw new ApiError(res.status, `Tải xuống thất bại (HTTP ${res.status})`);

  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/** Fetch a JSON model artifact (e.g. HMM model.json) as a typed object. */
export async function fetchModelArtifactJson<T>(versionId: number): Promise<T> {
  const headers = new Headers();
  const token = getAuthToken();
  if (token) headers.set('Authorization', `Bearer ${token}`);
  const res = await fetch(`${API_BASE}/api/v1/models/${versionId}/download`, { headers });
  if (res.status === 401) {
    setAuthToken(null);
    redirectToLogin();
    throw new ApiError(401, 'Phiên đăng nhập đã hết hạn');
  }
  if (!res.ok) throw new ApiError(res.status, `Tải artifact thất bại (HTTP ${res.status})`);
  return (await res.json()) as T;
}
