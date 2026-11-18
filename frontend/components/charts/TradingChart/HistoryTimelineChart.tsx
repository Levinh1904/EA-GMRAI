'use client';

// HistoryTimelineChart — lightweight-charts renderer for the History "Timeline"
// tab. Replaces the old Plotly TimelineChart (23k+ candles) with the same
// lightweight-charts v5 engine used by the Live Market / Replay pages, giving
// smooth wheel-zoom / drag-pan and the native crosshair (magnet mode) with a
// vertical guideline + OHLC legend.
//
//   - Candlestick series built from HistoryBar OHLC (M15 bars).
//   - Regime bands via the shared RegimeBandPrimitive canvas renderer
//     (AI / Reference / Overlay / Bất đồng modes).
//   - Crosshair move drives the OHLC legend; a click on a candle fills the bar
//     detail panel, a click on an AI regime band selects the containing segment.
//   - focusRange prop (segment list / date filter) zooms the visible range.
//   - Chart is created exactly once and cleaned up on unmount (no re-init).

import {
  CandlestickSeries,
  ColorType,
  createChart,
  CrosshairMode,
  type CandlestickData,
  type IChartApi,
  type ISeriesApi,
  type MouseEventParams,
  type Time,
  type UTCTimestamp,
} from 'lightweight-charts';
import { useEffect, useMemo, useRef, useState } from 'react';
import type { HistoryBar, HistorySegment } from '@/lib/types';
import {
  ChartOHLCLegend,
  RegimeBandPrimitive,
  type Band,
  type LegendBar,
} from './chartOverlays';
import styles from './tradingchart.module.css';

export type TimelineStripMode = 'ai' | 'reference' | 'overlay' | 'disagreement';

/** Client-built segment of the reference strip (grouped consecutive reference_regime). */
export interface RefStripSegment {
  start_ts: string;
  end_ts: string;
  regime: string;
}

/** Client-built segment of the disagreement strip (AI vs reference). */
export interface DiffStripSegment {
  start_ts: string;
  end_ts: string;
  agree: boolean;
}

export interface HistoryTimelineChartProps {
  bars: HistoryBar[];
  segments: HistorySegment[];
  /** [startIso, endIso] — when set, the chart zooms to this visible time range. */
  focusRange: [string, string] | null;
  onSelectSegment: (id: number | null) => void;
  onSelectBar: (barTs: string) => void;
  stripMode: TimelineStripMode;
  refSegments?: RefStripSegment[];
  diffSegments?: DiffStripSegment[];
  height?: number;
  /** Indices of `bars` that are live tail (not part of the analysed run). */
  liveFromIndex?: number | null;
}

const BAR_SEC = 15 * 60; // M15 bar spacing in seconds
const DEFAULT_BAR_SPACING = 7;

function toSec(iso: string): UTCTimestamp {
  return Math.floor(new Date(iso).getTime() / 1000) as UTCTimestamp;
}

function bisectLeft(times: number[], t: number): number {
  let lo = 0;
  let hi = times.length;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (times[mid] < t) lo = mid + 1;
    else hi = mid;
  }
  return lo;
}

/** Nearest bar index for a unix-seconds time (magnets to the adjacent M15 bar). */
function nearestIndex(times: number[], t: number): number {
  const idx = bisectLeft(times, t);
  if (idx === 0) return 0;
  if (idx >= times.length) return times.length - 1;
  return t - times[idx - 1] <= times[idx] - t ? idx - 1 : idx;
}

interface SegEntry {
  start: number;
  end: number;
  seg: HistorySegment;
}

export default function HistoryTimelineChart({
  bars,
  segments,
  focusRange,
  onSelectSegment,
  onSelectBar,
  stripMode,
  refSegments = [],
  diffSegments = [],
  height = 560,
  liveFromIndex = null,
}: HistoryTimelineChartProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const aiPrimRef = useRef<RegimeBandPrimitive | null>(null);
  const refPrimRef = useRef<RegimeBandPrimitive | null>(null);
  const stripPrimRef = useRef<RegimeBandPrimitive | null>(null);
  const initializedRef = useRef(false);

  const [legend, setLegend] = useState<LegendBar | null>(null);

  // ---- Memoized chart data -------------------------------------------------
  const candleData = useMemo<CandlestickData<Time>[]>(
    () =>
      bars.map((b) => ({
        time: toSec(b.ts),
        open: b.open,
        high: b.high,
        low: b.low,
        close: b.close,
      })),
    [bars]
  );

  const times = useMemo<number[]>(() => candleData.map((d) => d.time as number), [candleData]);

  // AI bands from segments; Reference bands from the client-built strip;
  // Disagreement bands colored AGREE/DISAGREE.
  const aiBands = useMemo<Band[]>(
    () =>
      segments.map((s) => ({
        start: toSec(s.start_ts) as number,
        end: toSec(s.end_ts) as number,
        regime: s.regime,
      })),
    [segments]
  );

  const refBands = useMemo<Band[]>(
    () =>
      refSegments.map((s) => ({
        start: toSec(s.start_ts) as number,
        end: toSec(s.end_ts) as number,
        regime: s.regime,
      })),
    [refSegments]
  );

  const disagreeBands = useMemo<Band[]>(
    () =>
      diffSegments.map((d) => ({
        start: toSec(d.start_ts) as number,
        end: toSec(d.end_ts) as number,
        regime: d.agree ? 'AGREE' : 'DISAGREE',
      })),
    [diffSegments]
  );

  const segmentsSorted = useMemo<SegEntry[]>(() => {
    const arr = segments.map((seg) => ({
      start: toSec(seg.start_ts) as number,
      end: toSec(seg.end_ts) as number,
      seg,
    }));
    arr.sort((a, b) => a.start - b.start);
    return arr;
  }, [segments]);

  // Refs mirroring latest props for the stable event handlers created once.
  const barsRef = useRef(bars);
  const timesRef = useRef(times);
  const candleDataRef = useRef(candleData);
  const stripModeRef = useRef(stripMode);
  const onSelectSegmentRef = useRef(onSelectSegment);
  const onSelectBarRef = useRef(onSelectBar);
  const segmentsSortedRef = useRef(segmentsSorted);
  const focusRangeRef = useRef(focusRange);
  useEffect(() => {
    barsRef.current = bars;
    timesRef.current = times;
    candleDataRef.current = candleData;
    stripModeRef.current = stripMode;
    onSelectSegmentRef.current = onSelectSegment;
    onSelectBarRef.current = onSelectBar;
    segmentsSortedRef.current = segmentsSorted;
    focusRangeRef.current = focusRange;
  });

  // ---- Mount / unmount — chart + series + subscriptions created once -------
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    const chart = createChart(el, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: 'transparent' },
        textColor: '#93a0b3',
        fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
        fontSize: 11,
      },
      grid: {
        vertLines: { color: 'rgba(139, 152, 169, 0.08)' },
        horzLines: { color: 'rgba(139, 152, 169, 0.08)' },
      },
      crosshair: {
        mode: CrosshairMode.Magnet,
        vertLine: {
          color: '#5b6a80',
          width: 1,
          style: 2,
          labelBackgroundColor: '#2a3240',
        },
        horzLine: {
          color: '#5b6a80',
          width: 1,
          style: 2,
          labelBackgroundColor: '#2a3240',
        },
      },
      rightPriceScale: {
        borderColor: '#222a38',
        scaleMargins: { top: 0.08, bottom: 0.12 },
      },
      timeScale: {
        borderColor: '#222a38',
        timeVisible: true,
        secondsVisible: false,
        rightOffset: 0,
        barSpacing: DEFAULT_BAR_SPACING,
        minBarSpacing: 0.05,
      },
      handleScroll: {
        mouseWheel: true,
        pressedMouseMove: true,
        horzTouchDrag: true,
        vertTouchDrag: true,
      },
      handleScale: {
        axisPressedMouseMove: { time: false, price: true },
        axisDoubleClickReset: { time: true, price: true },
        mouseWheel: true,
        pinch: true,
      },
      localization: {
        locale: 'vi-VN',
        priceFormatter: (p: number) => p.toFixed(2),
      },
    });

    // Debug hook for main-agent browser QA.
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (window as any).__gmraiHistoryChart = chart;

    const series = chart.addSeries(CandlestickSeries, {
      upColor: '#26a69a',
      downColor: '#ef5350',
      borderUpColor: '#26a69a',
      borderDownColor: '#ef5350',
      wickUpColor: '#26a69a',
      wickDownColor: '#ef5350',
      priceLineVisible: false,
    });

    const aiPrim = new RegimeBandPrimitive();
    const refPrim = new RegimeBandPrimitive();
    series.attachPrimitive(aiPrim);
    series.attachPrimitive(refPrim);

    // ---- Regime strip drawn in the bottom band of the pane -----------------
    // lightweight-charts v5 collapses extra panes under `autoSize`, so the
    // trend history is drawn in a reserved band at the bottom of the candle
    // pane instead: candles occupy the top 78% (scale margins below), the
    // strip the remaining 22% — always pixel-aligned with the candles above.
    const stripPrim = new RegimeBandPrimitive();
    stripPrim.setStrip(true);
    stripPrim.setShowLabels(true);
    stripPrim.setArea('bottom');
    series.attachPrimitive(stripPrim);

    // Reserve the bottom band so candles never overlap the strip.
    series.priceScale().applyOptions({ scaleMargins: { top: 0.06, bottom: 0.24 } });

    chartRef.current = chart;
    seriesRef.current = series;
    aiPrimRef.current = aiPrim;
    refPrimRef.current = refPrim;
    stripPrimRef.current = stripPrim;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (window as any).__gmraiStrip = stripPrim;

    // Crosshair move → OHLC legend (rAF-debounced).
    let raf = 0;
    const onCrosshairMove = (param: MouseEventParams<Time>) => {
      if (raf) return;
      raf = requestAnimationFrame(() => {
        raf = 0;
        const t = param.time as number | undefined;
        if (!t) {
          setLegend(null);
          return;
        }
        const timesNow = timesRef.current;
        if (timesNow.length === 0) {
          setLegend(null);
          return;
        }
        const idx = nearestIndex(timesNow, t);
        const b = barsRef.current[idx];
        if (!b) {
          setLegend(null);
          return;
        }
        const barTime = Math.floor(new Date(b.ts).getTime() / 1000);
        if (Math.abs(barTime - t) > BAR_SEC + 1) {
          setLegend(null);
          return;
        }
        const prev = idx > 0 ? barsRef.current[idx - 1] : null;
        setLegend({
          time: b.ts,
          open: b.open,
          high: b.high,
          low: b.low,
          close: b.close,
          volume: Number.NaN,
          prevClose: prev ? prev.close : null,
          ema: null,
          regime: b.regime,
          refRegime: b.reference_regime,
        });
      });
    };
    chart.subscribeCrosshairMove(onCrosshairMove);

    // Click: candle → bar detail; AI band (empty space) → select segment.
    const onClick = (param: MouseEventParams<Time>) => {
      if (!param.time || !param.point) return;
      const t = param.time as number;
      const timesNow = timesRef.current;
      if (timesNow.length === 0) return;
      const idx = nearestIndex(timesNow, t);
      const b = barsRef.current[idx];
      if (!b) return;
      const barTime = Math.floor(new Date(b.ts).getTime() / 1000);
      if (Math.abs(barTime - t) > BAR_SEC + 1) return;

      const ser = seriesRef.current;
      let onCandle = false;
      if (ser) {
        const hi = ser.priceToCoordinate(b.high);
        const lo = ser.priceToCoordinate(b.low);
        if (hi != null && lo != null) {
          const pad = 3;
          onCandle = param.point.y >= hi - pad && param.point.y <= lo + pad;
        }
      }

      const mode = stripModeRef.current;
      if (!onCandle && (mode === 'ai' || mode === 'overlay')) {
        const seg = findSegmentAt(segmentsSortedRef.current, t);
        if (seg) {
          onSelectSegmentRef.current(seg.id);
          return;
        }
      }
      onSelectBarRef.current(b.ts);
    };
    chart.subscribeClick(onClick);

    // Double-click resets to the full data range.
    const onDblClick = (e: MouseEvent) => {
      const target = e.target as HTMLElement;
      if (target.tagName === 'CANVAS' && e.offsetX < el.clientWidth - 70) {
        const ts = chart.timeScale();
        ts.applyOptions({ barSpacing: DEFAULT_BAR_SPACING });
        ts.fitContent();
      }
    };
    el.addEventListener('dblclick', onDblClick);

    return () => {
      cancelAnimationFrame(raf);
      chart.unsubscribeCrosshairMove(onCrosshairMove);
      chart.unsubscribeClick(onClick);
      el.removeEventListener('dblclick', onDblClick);
      series.detachPrimitive(aiPrim);
      series.detachPrimitive(refPrim);
      series.detachPrimitive(stripPrim);
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
      aiPrimRef.current = null;
      refPrimRef.current = null;
      stripPrimRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ---- Data updates (setData only, no series re-creation) ------------------
  useEffect(() => {
    const ser = seriesRef.current;
    if (!ser) return;
    ser.setData(candleData);
    if (candleData.length === 0) return;
    if (initializedRef.current) return;
    initializedRef.current = true;
    requestAnimationFrame(() => {
      const chart = chartRef.current;
      if (!chart) return;
      const fr = focusRangeRef.current;
      const ts = chart.timeScale();
      if (fr) {
        const a = toSec(fr[0]) as number;
        const b = toSec(fr[1]) as number;
        if (b > a) ts.setVisibleRange({ from: a as Time, to: b as Time });
        else ts.fitContent();
      } else {
        ts.fitContent();
      }
    });
  }, [candleData]);

  // ---- Regime bands in the dedicated strip pane ---------------------------
  const stripBands = useMemo<Band[]>(() => {
    let base: Band[] = aiBands;
    if (stripMode === 'reference') base = refBands;
    else if (stripMode === 'disagreement') base = disagreeBands;

    // Bars appended after the analysed run have no model label. Mark them
    // explicitly so the strip never looks like a filled-in prediction.
    if (liveFromIndex != null && liveFromIndex >= 0 && liveFromIndex < bars.length) {
      const firstLive = bars[liveFromIndex];
      const lastLive = bars[bars.length - 1];
      if (firstLive && lastLive) {
        base = [
          ...base,
          {
            start: toSec(firstLive.ts) as number,
            end: toSec(lastLive.ts) as number,
            regime: 'LIVE',
          },
        ];
      }
    }
    return base;
  }, [stripMode, aiBands, refBands, disagreeBands, bars, liveFromIndex]);

  // The renderer binary-searches over `bands`, so the array MUST be sorted by
  // start time (the LIVE tail band is appended after the AI bands, which would
  // otherwise break the search and hide every earlier band).
  const sortedStripBands = useMemo<Band[]>(
    () => [...stripBands].sort((a, b) => a.start - b.start),
    [stripBands]
  );

  // Overlay mode: AI strip on top, Reference strip below it.
  const overlayRefBands = useMemo<Band[]>(
    () => [...refBands].sort((a, b) => a.start - b.start),
    [refBands]
  );

  useEffect(() => {
    const ai = aiPrimRef.current;
    const ref = refPrimRef.current;
    const strip = stripPrimRef.current;
    if (!ai || !ref || !strip) return;

    // Bands are drawn only in the strip band underneath the candles (never
    // tinted over the price series), so the trend history reads as its own
    // timeline row aligned with the chart above.
    ai.setVisible(false);

    if (stripMode === 'overlay') {
      // Two stacked strips: AI on top, Reference underneath.
      strip.setArea('bottomUpper');
      strip.setBands(sortedStripBands);
      ref.setArea('bottomLower');
      ref.setBands(overlayRefBands);
      ref.setVisible(true);
      ref.setStrip(true);
      ref.setShowLabels(true);
    } else {
      strip.setArea('bottom');
      strip.setBands(sortedStripBands);
      ref.setVisible(false);
    }
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (window as any).__gmraiStrip = strip;
  }, [sortedStripBands, stripMode, overlayRefBands]);

  // ---- External focus (segment list / date filter / presets) ---------------
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart || candleDataRef.current.length === 0) return;
    const ts = chart.timeScale();
    if (focusRange) {
      const a = toSec(focusRange[0]) as number;
      const b = toSec(focusRange[1]) as number;
      if (b > a) ts.setVisibleRange({ from: a as Time, to: b as Time });
    } else {
      ts.applyOptions({ barSpacing: DEFAULT_BAR_SPACING });
      ts.fitContent();
    }
  }, [focusRange]);

  // ---- Toolbar actions -----------------------------------------------------
  function handleFit() {
    const chart = chartRef.current;
    if (!chart) return;
    chart.timeScale().applyOptions({ barSpacing: DEFAULT_BAR_SPACING });
    chart.timeScale().fitContent();
  }

  function handleReset() {
    const chart = chartRef.current;
    if (!chart) return;
    const timesNow = timesRef.current;
    const ts = chart.timeScale();
    ts.applyOptions({ barSpacing: DEFAULT_BAR_SPACING });
    if (timesNow.length === 0) {
      ts.fitContent();
      return;
    }
    const last = timesNow[timesNow.length - 1];
    const first = timesNow[Math.max(0, timesNow.length - 1 - 300)];
    ts.setVisibleRange({ from: first as Time, to: last as Time });
  }

  return (
    <div className={styles.chartWrap}>
      <div className={styles.toolbar}>
        <button
          type="button"
          className={styles.toolBtn}
          onClick={handleReset}
          title="Đặt lại về 300 nến gần nhất"
        >
          Reset
        </button>
        <button
          type="button"
          className={styles.toolBtn}
          onClick={handleFit}
          title="Khớp toàn bộ dữ liệu đã tải"
        >
          Fit
        </button>
        <span className={styles.ohlcHint}>
          Lăn chuột: zoom · Kéo: di chuyển · Kéo trục giá: co giãn · Nhấp đúp: toàn bộ
        </span>
      </div>
      <ChartOHLCLegend bar={legend} label="XAUUSD · M15 · History" />
      <div ref={containerRef} className={styles.chartCanvasWrap} style={{ height }} />
    </div>
  );
}

function findSegmentAt(entries: SegEntry[], t: number): HistorySegment | null {
  let lo = 0;
  let hi = entries.length - 1;
  let cand = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (entries[mid].start <= t) {
      cand = mid;
      lo = mid + 1;
    } else {
      hi = mid - 1;
    }
  }
  if (cand >= 0 && t <= entries[cand].end) return entries[cand].seg;
  return null;
}
