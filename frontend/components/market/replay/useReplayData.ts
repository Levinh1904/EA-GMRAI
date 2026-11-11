'use client';

// Data layer for the Historical Market Replay feature.
//  - `useReplayCandles`: loads a bounded, deduplicated window of candles around
//    a chosen anchor datetime (via from/to), paging older/newer as needed.
//  - `asofJoinBars` / `buildBands`: causal (as-of) join of M15 history bars to
//    arbitrary candles, and regime-band derivation for the overlay primitives.

import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '@/lib/api';
import type { Candle, HistoryBar, Timeframe } from '@/lib/types';
import type { Band } from '@/components/charts/TradingChart/chartOverlays';

export const TF_BAR_SEC: Record<Timeframe, number> = { M5: 300, M15: 900, H1: 3600 };
export const TF_BAR_MS: Record<Timeframe, number> = { M5: 300_000, M15: 900_000, H1: 3_600_000 };

const LOOKBACK_CANDLES = 1200; // candles loaded before the anchor
const LOOKAHEAD_CANDLES = 800; // candles loaded after the anchor (play room)
const PAGE_LIMIT = 5000; // backend cap
const MAX_WINDOW = 12000; // in-memory cap (no-op loads once reached)

export function toSecMs(iso: string): number {
  const t = new Date(iso).getTime();
  return Number.isNaN(t) ? 0 : t;
}

export function toSec(iso: string): number {
  return Math.floor(toSecMs(iso) / 1000);
}

/** Floor a unix-ms timestamp to the start of its timeframe bar. */
export function floorToBar(tsMs: number, tf: Timeframe): number {
  const bar = TF_BAR_MS[tf];
  return Math.floor(tsMs / bar) * bar;
}

function dedupe(candles: Candle[]): Candle[] {
  const seen = new Set<number>();
  const out: Candle[] = [];
  for (const c of candles) {
    const t = toSecMs(c.ts);
    if (!seen.has(t)) {
      seen.add(t);
      out.push(c);
    }
  }
  return out;
}

/** Index of the candle at-or-before `tsMs`, or -1 if none precedes it. */
export function findCursorIndex(candles: Candle[], tsMs: number): number {
  let lo = 0;
  let hi = candles.length - 1;
  let best = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    const t = toSecMs(candles[mid].ts);
    if (t <= tsMs) {
      best = mid;
      lo = mid + 1;
    } else {
      hi = mid - 1;
    }
  }
  return best;
}

export interface ReplayCandlesState {
  candles: Candle[];
  loading: boolean;
  loadingOlder: boolean;
  loadingNewer: boolean;
  hasOlder: boolean;
  hasNewer: boolean;
  error: string | null;
  loadOlder: () => void;
  loadNewer: () => void;
}

export function useReplayCandles(timeframe: Timeframe, anchorMs: number | null): ReplayCandlesState {
  const [candles, setCandles] = useState<Candle[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingOlder, setLoadingOlder] = useState(false);
  const [loadingNewer, setLoadingNewer] = useState(false);
  const [hasOlder, setHasOlder] = useState(false);
  const [hasNewer, setHasNewer] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);

  const seqRef = useRef(0);
  const candlesRef = useRef<Candle[]>([]);
  const boundsRef = useRef<{ minMs: number; maxMs: number } | null>(null);

  const commit = useCallback((next: Candle[]) => {
    const merged = dedupe(next);
    candlesRef.current = merged;
    setCandles(merged);
    const b = boundsRef.current;
    if (merged.length === 0) {
      setHasOlder(false);
      setHasNewer(false);
      return;
    }
    const rMin = toSecMs(merged[0].ts);
    const rMax = toSecMs(merged[merged.length - 1].ts);
    setHasOlder(b ? rMin > b.minMs : false);
    setHasNewer(b ? rMax < b.maxMs : false);
  }, []);

  // Full reload when the timeframe or anchor changes.
  useEffect(() => {
    let cancelled = false;
    const seq = ++seqRef.current;
    setCandles([]);
    candlesRef.current = [];
    boundsRef.current = null;
    setLoading(true);
    setError(null);
    setHasOlder(false);
    setHasNewer(false);

    (async () => {
      try {
        // Discover the dataset bounds for this timeframe.
        const oldest = await api.candlesRange(timeframe, { limit: 1, offset: 0 });
        const totalCount = oldest.total;
        let minMs = 0;
        let maxMs = 0;
        if (oldest.candles.length > 0) minMs = toSecMs(oldest.candles[0].ts);
        if (totalCount > 0) {
          const newest = await api.candlesRange(timeframe, {
            limit: 1,
            offset: Math.max(0, totalCount - 1),
          });
          if (newest.candles.length > 0) maxMs = toSecMs(newest.candles[0].ts);
        }
        if (cancelled || seq !== seqRef.current) return;
        boundsRef.current = { minMs, maxMs };

        const anchor = anchorMs ?? maxMs;
        const fromMs = anchor - LOOKBACK_CANDLES * TF_BAR_MS[timeframe];
        const toMs = anchor + LOOKAHEAD_CANDLES * TF_BAR_MS[timeframe];
        const resp = await api.candlesRange(timeframe, {
          from: new Date(fromMs).toISOString(),
          to: new Date(toMs).toISOString(),
          limit: PAGE_LIMIT,
        });
        if (cancelled || seq !== seqRef.current) return;
        commit(resp.candles);
      } catch (e) {
        if (cancelled || seq !== seqRef.current) return;
        setError(e instanceof Error ? e.message : 'Không thể tải dữ liệu nến');
      } finally {
        if (!cancelled && seq === seqRef.current) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [timeframe, anchorMs, nonce, commit]);

  const loadOlder = useCallback(() => {
    const cur = candlesRef.current;
    if (cur.length === 0 || cur.length >= MAX_WINDOW) return;
    const seq = ++seqRef.current;
    setLoadingOlder(true);
    setError(null);
    const oldestMs = toSecMs(cur[0].ts);
    const fromMs = oldestMs - LOOKBACK_CANDLES * TF_BAR_MS[timeframe];
    (async () => {
      try {
        const resp = await api.candlesRange(timeframe, {
          from: new Date(fromMs).toISOString(),
          to: new Date(oldestMs - 1).toISOString(),
          limit: PAGE_LIMIT,
        });
        if (seq !== seqRef.current) return;
        const oldestPrev = candlesRef.current.length > 0 ? toSecMs(candlesRef.current[0].ts) : Infinity;
        const fresh = resp.candles.filter((c) => toSecMs(c.ts) < oldestPrev);
        commit([...fresh, ...candlesRef.current]);
      } catch (e) {
        if (seq !== seqRef.current) return;
        setError(e instanceof Error ? e.message : 'Không thể tải thêm dữ liệu nến');
      } finally {
        if (seq === seqRef.current) setLoadingOlder(false);
      }
    })();
  }, [timeframe, commit]);

  const loadNewer = useCallback(() => {
    const cur = candlesRef.current;
    if (cur.length === 0 || cur.length >= MAX_WINDOW) return;
    const seq = ++seqRef.current;
    setLoadingNewer(true);
    setError(null);
    const newestMs = toSecMs(cur[cur.length - 1].ts);
    const toMs = newestMs + LOOKAHEAD_CANDLES * TF_BAR_MS[timeframe];
    (async () => {
      try {
        const resp = await api.candlesRange(timeframe, {
          from: new Date(newestMs + 1).toISOString(),
          to: new Date(toMs).toISOString(),
          limit: PAGE_LIMIT,
        });
        if (seq !== seqRef.current) return;
        const newestPrev = candlesRef.current.length > 0 ? toSecMs(candlesRef.current[candlesRef.current.length - 1].ts) : -Infinity;
        const fresh = resp.candles.filter((c) => toSecMs(c.ts) > newestPrev);
        commit([...candlesRef.current, ...fresh]);
      } catch (e) {
        if (seq !== seqRef.current) return;
        setError(e instanceof Error ? e.message : 'Không thể tải thêm dữ liệu nến');
      } finally {
        if (seq === seqRef.current) setLoadingNewer(false);
      }
    })();
  }, [timeframe, commit]);

  return { candles, loading, loadingOlder, loadingNewer, hasOlder, hasNewer, error, loadOlder, loadNewer };
}

// ---------------------------------------------------------------------------
// Causal (as-of) join of M15 history bars to candles of any timeframe.
// Both inputs are ascending; each candle maps to the most recent M15 bar at or
// before its timestamp (no future information).
// ---------------------------------------------------------------------------

export function asofJoinBars(candles: Candle[], bars: HistoryBar[]): (HistoryBar | null)[] {
  const out: (HistoryBar | null)[] = new Array(candles.length).fill(null);
  let b = -1;
  for (let i = 0; i < candles.length; i++) {
    const t = toSecMs(candles[i].ts);
    while (b + 1 < bars.length && toSecMs(bars[b + 1].ts) <= t) b++;
    if (b >= 0) out[i] = bars[b];
  }
  return out;
}

/** Derive contiguous regime bands from per-candle regime values (band end = last candle ts). */
export function buildBands(
  candles: Candle[],
  regimes: (string | null)[],
  defaultRegime = 'UNKNOWN'
): Band[] {
  const bands: Band[] = [];
  let cur: Band | null = null;
  for (let i = 0; i < candles.length; i++) {
    const regime = regimes[i] ?? defaultRegime;
    const t = toSec(candles[i].ts);
    if (!cur || cur.regime !== regime) {
      if (cur) bands.push(cur);
      cur = { start: t, end: t, regime };
    } else {
      cur.end = t;
    }
  }
  if (cur) bands.push(cur);
  return bands;
}

/** Build a timestamp-keyed index of bars for the OHLC legend (candle ts -> bar). */
export function asofBarsIndex(candles: Candle[], bars: HistoryBar[]): Map<number, HistoryBar> {
  const map = new Map<number, HistoryBar>();
  const joined = asofJoinBars(candles, bars);
  for (let i = 0; i < candles.length; i++) {
    const hb = joined[i];
    if (hb) map.set(toSec(candles[i].ts), hb);
  }
  return map;
}
