'use client';

// Data layer for the TradingChart: paginated candle loading (append/prepend)
// plus history-run regime data (segments + bars) for the chart overlays.
// Everything comes from the real backend — no mock data anywhere.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import useSWR from 'swr';
import { api } from '@/lib/api';
import { useApi } from '@/lib/swr';
import type {
  CandlesResponse,
  Candle,
  HistoryBar,
  HistoryRun,
  HistoryRunListResponse,
  HistorySegment,
  HistorySegmentsResponse,
  Timeframe,
} from '@/lib/types';

export const CANDLE_PAGE = 5000;
export const BARS_PAGE = 20000;

// ---------------------------------------------------------------------------
// Paginated candles (ascending, newest page loaded first)
// ---------------------------------------------------------------------------

export interface CandlesState {
  candles: Candle[];
  total: number;
  hasMore: boolean;
  loading: boolean; // initial load
  loadingMore: boolean; // prepending an older page
  error: string | null;
  reload: () => void;
  loadMore: () => void;
}

export function useCandlesPaged(timeframe: Timeframe): CandlesState {
  const [candles, setCandles] = useState<Candle[]>([]);
  const [total, setTotal] = useState(0);
  const [oldestOffset, setOldestOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);
  const requestSeq = useRef(0);

  // Initial load: discover total, then fetch the newest page.
  useEffect(() => {
    let cancelled = false;
    const seq = ++requestSeq.current;
    setCandles([]);
    setTotal(0);
    setOldestOffset(0);
    setLoading(true);
    setError(null);

    (async () => {
      try {
        const probe = await api.candles(timeframe, 1, 0);
        if (cancelled || seq !== requestSeq.current) return;
        const totalCount = probe.total;
        const firstOffset = Math.max(0, totalCount - CANDLE_PAGE);
        const page = await api.candles(timeframe, CANDLE_PAGE, firstOffset);
        if (cancelled || seq !== requestSeq.current) return;
        setCandles(page.candles);
        setTotal(page.total);
        setOldestOffset(firstOffset);
      } catch (e) {
        if (cancelled || seq !== requestSeq.current) return;
        setError(e instanceof Error ? e.message : 'Không thể tải dữ liệu nến');
      } finally {
        if (!cancelled && seq === requestSeq.current) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [timeframe, nonce]);

  const loadMore = useCallback(() => {
    if (oldestOffset <= 0) return;
    const seq = ++requestSeq.current;
    setLoadingMore(true);
    setError(null);
    const nextOffset = Math.max(0, oldestOffset - CANDLE_PAGE);
    (async () => {
      try {
        const resp: CandlesResponse = await api.candles(timeframe, CANDLE_PAGE, nextOffset);
        if (seq !== requestSeq.current) return;
        setCandles((prev) => {
          // Dedupe on the boundary (both pages can share the oldest row).
          const newestPrev = prev.length > 0 ? new Date(prev[0].ts).getTime() : -Infinity;
          const fresh = resp.candles.filter((c) => new Date(c.ts).getTime() < newestPrev);
          return [...fresh, ...prev];
        });
        setTotal(resp.total);
        setOldestOffset(nextOffset);
      } catch (e) {
        if (seq !== requestSeq.current) return;
        setError(e instanceof Error ? e.message : 'Không thể tải thêm dữ liệu nến');
      } finally {
        if (seq === requestSeq.current) setLoadingMore(false);
      }
    })();
  }, [oldestOffset, timeframe]);

  const reload = useCallback(() => setNonce((n) => n + 1), []);

  return {
    candles,
    total,
    hasMore: oldestOffset > 0,
    loading,
    loadingMore,
    error,
    reload,
    loadMore,
  };
}

// ---------------------------------------------------------------------------
// Latest completed history run (for regime overlays)
// ---------------------------------------------------------------------------

export function useLatestDoneRun(): HistoryRun | null {
  const { data } = useApi<HistoryRunListResponse>('/history/runs?limit=20', {
    refreshInterval: 120000,
    revalidateOnFocus: false,
  });
  const runs = data?.runs ?? [];
  return useMemo(() => {
    const done = runs.find((r) => r.status === 'done');
    return done ?? runs[0] ?? null;
  }, [runs]);
}

// ---------------------------------------------------------------------------
// All segments of a run (compact — used for AI regime bands)
// ---------------------------------------------------------------------------

export function useRunSegments(runId: number | null): {
  segments: HistorySegment[];
  isLoading: boolean;
  error: unknown;
} {
  const { data, isLoading, error } = useApi<HistorySegmentsResponse>(
    runId != null ? `/history/runs/${runId}/segments?limit=5000&offset=0` : null,
    { revalidateIfStale: false, revalidateOnFocus: false, refreshInterval: 0 }
  );
  return { segments: data?.segments ?? [], isLoading, error };
}

// ---------------------------------------------------------------------------
// All segments of a run, fully paginated (shared SWR cache — used by the
// History page tabs).
// ---------------------------------------------------------------------------

async function fetchAllSegments(runId: number): Promise<HistorySegment[]> {
  const out: HistorySegment[] = [];
  let offset = 0;
  for (;;) {
    const resp = await api.historySegments(runId, { limit: 1000, offset });
    out.push(...resp.segments);
    if (resp.segments.length === 0 || out.length >= resp.total) break;
    offset += resp.limit;
  }
  return out;
}

export function useAllSegments(runId: number | null): {
  segments: HistorySegment[];
  isLoading: boolean;
  error: unknown;
} {
  const { data, isLoading, error } = useSWR<HistorySegment[]>(
    runId != null ? `/history/runs/${runId}/segments-all` : null,
    () => fetchAllSegments(runId as number),
    { revalidateIfStale: false, revalidateOnFocus: false, refreshInterval: 0 }
  );
  return { segments: data ?? [], isLoading, error };
}

// ---------------------------------------------------------------------------
// All bars of a run (heavy — paginated in 20k chunks, cached by SWR)
// ---------------------------------------------------------------------------

async function fetchAllBars(runId: number): Promise<HistoryBar[]> {
  const out: HistoryBar[] = [];
  let offset = 0;
  for (;;) {
    const resp = await api.historyBars(runId, BARS_PAGE, offset);
    out.push(...resp.bars);
    if (resp.bars.length === 0 || out.length >= resp.total) break;
    offset += resp.limit;
  }
  return out;
}

export function useRunBars(
  runId: number | null,
  enabled: boolean
): { bars: HistoryBar[]; isLoading: boolean; error: unknown } {
  const { data, isLoading, error } = useSWR<HistoryBar[]>(
    runId != null && enabled ? `/history/runs/${runId}/bars-all` : null,
    () => fetchAllBars(runId as number),
    { revalidateIfStale: false, revalidateOnFocus: false, refreshInterval: 0 }
  );
  return { bars: data ?? [], isLoading, error };
}

/** Index bars by unix-seconds timestamp for O(1) lookups. */
export function useBarsIndex(bars: HistoryBar[]): Map<number, HistoryBar> {
  return useMemo(() => {
    const map = new Map<number, HistoryBar>();
    for (const b of bars) {
      const t = new Date(b.ts).getTime();
      if (!Number.isNaN(t)) map.set(Math.floor(t / 1000), b);
    }
    return map;
  }, [bars]);
}

// ---------------------------------------------------------------------------
// Band derivation (client-side grouping — real data only)
// ---------------------------------------------------------------------------

export interface RegimeBand {
  start: number; // unix seconds
  end: number; // unix seconds
  regime: string;
}

export function tsToSec(iso: string): number {
  return Math.floor(new Date(iso).getTime() / 1000);
}

/** AI bands from run segments (span [start_ts, end_ts]). */
export function segmentsToBands(segments: HistorySegment[]): RegimeBand[] {
  return segments.map((s) => ({
    start: tsToSec(s.start_ts),
    end: tsToSec(s.end_ts),
    regime: s.regime,
  }));
}

/** Reference bands: group consecutive bars with the same reference_regime. */
export function barsToReferenceBands(bars: HistoryBar[]): RegimeBand[] {
  const out: RegimeBand[] = [];
  let cur: RegimeBand | null = null;
  for (const b of bars) {
    const regime = b.reference_regime ?? 'UNKNOWN';
    const t = tsToSec(b.ts);
    if (!cur || cur.regime !== regime) {
      if (cur) out.push(cur);
      cur = { start: t, end: t, regime };
    } else {
      cur.end = t;
    }
  }
  if (cur) out.push(cur);
  return out;
}
