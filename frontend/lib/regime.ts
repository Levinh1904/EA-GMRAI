import type { Permission, Regime } from './types';

/** Canonical regime color map (dark quantitative theme). */
export const REGIME_COLORS: Record<string, string> = {
  TREND_UP: '#22c55e',
  TREND_DOWN: '#ef4444',
  SIDEWAYS: '#8b98a9',
  HIGH_VOLATILITY: '#f59e0b',
  TRANSITION: '#a855f7',
  EARLY_TREND_UP: '#14b8a6',
  EARLY_TREND_DOWN: '#14b8a6',
  UNKNOWN: '#4b5563',
};

export const REGIME_LABELS: Record<string, string> = {
  TREND_UP: 'Xu hướng tăng',
  TREND_DOWN: 'Xu hướng giảm',
  SIDEWAYS: 'Đi ngang',
  HIGH_VOLATILITY: 'Biến động cao',
  TRANSITION: 'Chuyển tiếp',
  EARLY_TREND_UP: 'Tăng sớm',
  EARLY_TREND_DOWN: 'Giảm sớm',
  UNKNOWN: 'Không xác định',
};

export function regimeColor(regime: string | null | undefined): string {
  if (!regime) return REGIME_COLORS.UNKNOWN;
  return REGIME_COLORS[regime] ?? REGIME_COLORS.UNKNOWN;
}

export function regimeLabel(regime: string | null | undefined): string {
  if (!regime) return '—';
  return REGIME_LABELS[regime] ?? regime;
}

export function isKnownRegime(regime: string | null | undefined): regime is Regime {
  return !!regime && Object.prototype.hasOwnProperty.call(REGIME_LABELS, regime);
}

export const PERMISSION_LABELS: Record<Permission, string> = {
  BUY_ONLY: 'Chỉ mua (Buy-only)',
  SELL_ONLY: 'Chỉ bán (Sell-only)',
  NO_TRADE: 'Không giao dịch (No-trade)',
};

export function permissionLabel(permission: string | null | undefined): string {
  if (!permission) return '—';
  return PERMISSION_LABELS[permission as Permission] ?? permission;
}

export function permissionTone(permission: string | null | undefined): 'up' | 'down' | 'neutral' {
  if (permission === 'BUY_ONLY') return 'up';
  if (permission === 'SELL_ONLY') return 'down';
  return 'neutral';
}

export const REASON_CODE_LABELS: Record<string, string> = {
  RF_HMM_DIVERGE: 'RF và HMM phân kỳ',
  RF_HMM_AGREE: 'RF và HMM đồng thuận',
  HIGH_VOL_FILTER: 'Bộ lọc biến động cao',
  EARLY_SIGNAL: 'Tín hiệu xu hướng sớm',
  LOW_CONFIDENCE: 'Độ tin cậy thấp',
  STALE_DATA: 'Dữ liệu cũ',
  TRANSITION_FILTER: 'Bộ lọc chuyển tiếp',
};

export function reasonCodeLabel(code: string): string {
  return REASON_CODE_LABELS[code] ?? code;
}

export const MODEL_STATUS_LABELS: Record<string, string> = {
  training: 'Đang huấn luyện',
  validating: 'Đang đánh giá',
  candidate: 'Ứng viên',
  approved: 'Đã duyệt',
  rejected: 'Bị từ chối',
  archived: 'Đã lưu trữ',
};

export const JOB_STATUS_LABELS: Record<string, string> = {
  scheduled: 'Đã lên lịch',
  running: 'Đang chạy',
  done: 'Hoàn tất',
  failed: 'Thất bại',
  cancelled: 'Đã hủy',
};

export function statusLabel(status: string | null | undefined): string {
  if (!status) return '—';
  return MODEL_STATUS_LABELS[status] ?? JOB_STATUS_LABELS[status] ?? status;
}

export type Tone = 'success' | 'danger' | 'warning' | 'info' | 'neutral';

export function statusTone(status: string | null | undefined): Tone {
  switch (status) {
    case 'approved':
    case 'done':
    case 'ok':
      return 'success';
    case 'failed':
    case 'rejected':
    case 'error':
      return 'danger';
    case 'training':
    case 'validating':
    case 'candidate':
    case 'scheduled':
    case 'running':
      return 'info';
    case 'archived':
    case 'cancelled':
      return 'neutral';
    default:
      return 'warning';
  }
}

export function isEarlyTrend(regime: string | null | undefined): boolean {
  return regime === 'EARLY_TREND_UP' || regime === 'EARLY_TREND_DOWN';
}
