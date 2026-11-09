import type { Candle, Regime, RegimeHistoryEntry } from './types';

/** Exponential moving average over `values`; null for warm-up positions. */
export function computeEma(values: number[], period: number): (number | null)[] {
  const out: (number | null)[] = new Array(values.length).fill(null);
  if (values.length === 0) return out;
  const k = 2 / (period + 1);
  let ema = values[0];
  out[0] = ema;
  for (let i = 1; i < values.length; i++) {
    ema = values[i] * k + ema * (1 - k);
    out[i] = ema;
  }
  return out;
}

/**
 * Map each candle timestamp to the most recent regime history entry at or
 * before it (both series are ascending). Returns null where no history covers
 * the candle.
 */
export function alignRegimePerCandle(
  candles: Candle[],
  history: RegimeHistoryEntry[]
): (Regime | null)[] {
  const out: (Regime | null)[] = new Array(candles.length).fill(null);
  let h = -1;
  for (let i = 0; i < candles.length; i++) {
    const t = new Date(candles[i].ts).getTime();
    while (h + 1 < history.length && new Date(history[h + 1].ts).getTime() <= t) {
      h++;
    }
    if (h >= 0) out[i] = history[h].regime;
  }
  return out;
}

/** Last candle price change vs previous candle, in percent. */
export function lastChangePct(candles: Candle[]): number | null {
  if (candles.length < 2) return null;
  const prev = candles[candles.length - 2].close;
  const last = candles[candles.length - 1].close;
  if (!prev || prev === 0) return null;
  return ((last - prev) / prev) * 100;
}

export function candleDirection(candle: Candle): 'up' | 'down' | 'flat' {
  if (candle.close > candle.open) return 'up';
  if (candle.close < candle.open) return 'down';
  return 'flat';
}
