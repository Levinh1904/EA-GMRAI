// Global filters for the Historical Analyzer page (date range, timeframe,
// model version, regime mode). Kept in a separate module so the tabs can
// import the types without circular dependencies.

export type RegimeMode = 'ai' | 'reference';

export interface HistoryFilters {
  /** Start of day, ISO datetime (UTC). Null = unbounded. */
  start: string | null;
  /** End of day (inclusive), ISO datetime (UTC). Null = unbounded. */
  end: string | null;
  regimeMode: RegimeMode;
}

export const DEFAULT_FILTERS: HistoryFilters = {
  start: null,
  end: null,
  regimeMode: 'ai',
};

/** Convert "YYYY-MM-DD" date inputs into an inclusive UTC day range. */
export function dayRangeToUtc(startDate: string | null, endDate: string | null): {
  start: string;
  end: string;
} | null {
  if (!startDate || !endDate) return null;
  const s = new Date(`${startDate}T00:00:00Z`).getTime();
  const e = new Date(`${endDate}T00:00:00Z`).getTime();
  if (Number.isNaN(s) || Number.isNaN(e) || e < s) return null;
  return {
    start: new Date(s).toISOString(),
    end: new Date(e + 24 * 60 * 60 * 1000 - 1).toISOString(),
  };
}

export function isoToDateInput(iso: string | null): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  return d.toISOString().slice(0, 10);
}

export function rangeStartMs(filters: HistoryFilters): number | null {
  return filters.start ? new Date(filters.start).getTime() : null;
}

export function rangeEndMs(filters: HistoryFilters): number | null {
  return filters.end ? new Date(filters.end).getTime() : null;
}

/** True if the segment overlaps the filter date range (inclusive). */
export function segmentInRange(
  startTs: string,
  endTs: string,
  filters: HistoryFilters
): boolean {
  const s = rangeStartMs(filters);
  const e = rangeEndMs(filters);
  if (s == null && e == null) return true;
  const a = new Date(startTs).getTime();
  const b = new Date(endTs).getTime();
  if (s != null && b < s) return false;
  if (e != null && a > e) return false;
  return true;
}
