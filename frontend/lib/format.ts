/** Formatting helpers. All timestamps are rendered in UTC with an explicit "UTC" label. */

export function toDate(iso: string | null | undefined): Date | null {
  if (!iso) return null;
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? null : d;
}

/** "2026-11-09 16:04 UTC" */
export function fmtUtc(iso: string | null | undefined): string {
  const d = toDate(iso);
  if (!d) return '—';
  return `${d.toISOString().slice(0, 16).replace('T', ' ')} UTC`;
}

/** "2026-11-09 16:04:05 UTC" */
export function fmtUtcSec(iso: string | null | undefined): string {
  const d = toDate(iso);
  if (!d) return '—';
  return `${d.toISOString().slice(0, 19).replace('T', ' ')} UTC`;
}

export function fmtAge(minutes: number | null | undefined): string {
  if (minutes == null || Number.isNaN(minutes)) return '—';
  if (minutes < 1) return '<1 phút trước';
  if (minutes < 60) return `${Math.round(minutes)} phút trước`;
  const hours = minutes / 60;
  if (hours < 24) return `${hours.toFixed(1)} giờ trước`;
  return `${(hours / 24).toFixed(1)} ngày trước`;
}

export function fmtNum(value: number | null | undefined, digits = 2): string {
  if (value == null || Number.isNaN(value)) return '—';
  return value.toLocaleString('en-US', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

export function fmtPrice(value: number | null | undefined): string {
  return fmtNum(value, 2);
}

/** value in [0,1] -> "68.7%" */
export function fmtPct(value: number | null | undefined, digits = 1): string {
  if (value == null || Number.isNaN(value)) return '—';
  return `${(value * 100).toFixed(digits)}%`;
}

export function fmtDuration(start: string | null, end: string | null): string {
  const s = toDate(start);
  const e = toDate(end);
  if (!s || !e) return '—';
  const ms = e.getTime() - s.getTime();
  if (ms < 0) return '—';
  const sec = Math.round(ms / 1000);
  if (sec < 60) return `${sec} giây`;
  const min = Math.round(sec / 60);
  if (min < 60) return `${min} phút`;
  return `${(min / 60).toFixed(1)} giờ`;
}

export function variantName(variant: string): string {
  switch (variant) {
    case 'hmm_only':
      return 'Chỉ HMM';
    case 'rf_only':
      return 'Chỉ RF';
    case 'combined':
      return 'HMM + RF';
    default:
      return variant;
  }
}
