'use client';

// TradingChartContainer — canvas-mounting component for the lightweight-charts
// v5 engine. Owns the full chart lifecycle:
//   - create once per mount, full cleanup on unmount (no leaks)
//   - series are created once and only `setData`-updated (no re-init on append)
//   - pan / wheel-zoom / price-axis drag rescale / axis dblclick reset
//   - crosshair (magnet) + OHLC legend
//   - lazy-load older history via visible-logical-range subscription
//   - regime band overlays via a canvas primitive (visible-range culled)

import {
  CandlestickSeries,
  ColorType,
  createChart,
  CrosshairMode,
  HistogramSeries,
  LineSeries,
  type CandlestickData,
  type HistogramData,
  type IChartApi,
  type ISeriesApi,
  type LineData,
  type MouseEventParams,
  type Time,
  type UTCTimestamp,
} from 'lightweight-charts';
import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
} from 'react';
import { computeEma } from '@/lib/market';
import type { Candle, HistoryBar, HistorySegment, Timeframe } from '@/lib/types';
import {
  ChartOHLCLegend,
  RegimeBandPrimitive,
  RegimePopover,
  ReplayCursorPrimitive,
  type Band,
  type BandDetail,
  type LegendBar,
} from './chartOverlays';
import styles from './tradingchart.module.css';

export interface TradingChartHandle {
  zoomIn: () => void;
  zoomOut: () => void;
  reset: () => void;
  fitContent: () => void;
  scrollToRealTime: () => void;
  focusRange: (fromSec: number, toSec: number) => void;
  // Replay-mode imperative controls.
  setCursor: (timeSec: number | null) => void;
  getVisibleLogicalRange: () => { from: number; to: number } | null;
  setVisibleLogicalRange: (from: number, to: number) => void;
}

export interface TradingChartProps {
  candles: Candle[];
  timeframe: Timeframe;
  height?: number;
  hasMore?: boolean;
  loadingMore?: boolean;
  onLoadMore?: () => void;
  showVolume?: boolean;
  showGrid?: boolean;
  showCrosshair?: boolean;
  autoScale?: boolean;
  showEma?: boolean;
  emaPeriod?: number;
  showAiBands?: boolean;
  showRefBands?: boolean;
  aiBands?: Band[];
  refBands?: Band[];
  barsByTime?: Map<number, HistoryBar> | null;
  segments?: HistorySegment[] | null;
  replayMode?: boolean;
}

const TF_BAR_MS: Record<Timeframe, number> = { M5: 5 * 60 * 1000, M15: 15 * 60 * 1000, H1: 3600 * 1000 };
const DEFAULT_BAR_SPACING = 7;
const LEGEND_DEBOUNCE_MS = 40;

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

const TradingChartContainer = forwardRef<TradingChartHandle, TradingChartProps>(
  function TradingChartContainer(props, ref) {
    const {
      candles,
      timeframe,
      height = 520,
      hasMore = false,
      loadingMore = false,
      onLoadMore,
      showVolume = true,
      showGrid = true,
      showCrosshair = true,
      autoScale = true,
      showEma = true,
      emaPeriod = 20,
      showAiBands = true,
      showRefBands = false,
      aiBands,
      refBands,
      barsByTime,
      segments,
      replayMode = false,
    } = props;

    const containerRef = useRef<HTMLDivElement | null>(null);
    const chartRef = useRef<IChartApi | null>(null);
    const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
    const volumeSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null);
    const emaSeriesRef = useRef<ISeriesApi<'Line'> | null>(null);
    const aiBandPrimRef = useRef<RegimeBandPrimitive | null>(null);
    const refBandPrimRef = useRef<RegimeBandPrimitive | null>(null);
    const cursorPrimRef = useRef<ReplayCursorPrimitive | null>(null);
    const prevCandleDataRef = useRef<CandlestickData<Time>[]>([]);

    const hasMoreRef = useRef(hasMore);
    const loadingMoreRef = useRef(loadingMore);
    const onLoadMoreRef = useRef(onLoadMore);
    const timeframeRef = useRef(timeframe);
    const heightRef = useRef(height);
    const autoScaleRef = useRef(autoScale);
    const replayModeRef = useRef(replayMode);

    useEffect(() => {
      hasMoreRef.current = hasMore;
    }, [hasMore]);
    useEffect(() => {
      loadingMoreRef.current = loadingMore;
    }, [loadingMore]);
    useEffect(() => {
      onLoadMoreRef.current = onLoadMore;
    }, [onLoadMore]);
    useEffect(() => {
      timeframeRef.current = timeframe;
    }, [timeframe]);
    useEffect(() => {
      heightRef.current = height;
    }, [height]);
    useEffect(() => {
      autoScaleRef.current = autoScale;
    }, [autoScale]);
    useEffect(() => {
      replayModeRef.current = replayMode;
    }, [replayMode]);

    // Crosshair legend state (updated at most every frame via rAF).
    const [legend, setLegend] = useState<LegendBar | null>(null);
    // Band click popover state.
    const [popover, setPopover] = useState<{ detail: BandDetail; x: number; y: number } | null>(null);
    const [containerWidth, setContainerWidth] = useState(0);

    // Memoized chart data.
    const candleData = useMemo<CandlestickData<Time>[]>(
      () =>
        candles.map((c) => ({
          time: toSec(c.ts),
          open: c.open,
          high: c.high,
          low: c.low,
          close: c.close,
        })),
      [candles]
    );
    const volumeData = useMemo<HistogramData<Time>[]>(
      () =>
        candles.map((c) => ({
          time: toSec(c.ts),
          value: c.tick_volume,
          color: c.close >= c.open ? 'rgba(38, 166, 154, 0.4)' : 'rgba(239, 83, 80, 0.4)',
        })),
      [candles]
    );
    const emaValues = useMemo(() => computeEma(candles.map((c) => c.close), emaPeriod), [candles, emaPeriod]);
    const emaData = useMemo<LineData<Time>[]>(() => {
      const out: LineData<Time>[] = [];
      for (let i = 0; i < candles.length; i++) {
        const v = emaValues[i];
        if (v != null) out.push({ time: toSec(candles[i].ts), value: v });
      }
      return out;
    }, [candles, emaValues]);
    const candleTimes = useMemo(() => candles.map((c) => toSec(c.ts)), [candles]);
    const segmentsByStart = useMemo(() => {
      if (!segments) return null;
      const map = new Map<number, HistorySegment>();
      for (const s of segments) {
        const t = Math.floor(new Date(s.start_ts).getTime() / 1000);
        if (!map.has(t)) map.set(t, s);
      }
      return map;
    }, [segments]);

    // -----------------------------------------------------------------------
    // Mount / unmount — chart + series creation happens exactly once.
    // -----------------------------------------------------------------------
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
          scaleMargins: { top: 0.08, bottom: 0.22 },
        },
        timeScale: {
          borderColor: '#222a38',
          timeVisible: true,
          secondsVisible: false,
          rightOffset: 6,
          barSpacing: DEFAULT_BAR_SPACING,
          minBarSpacing: 0.4,
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

      // Debug hook for main-agent browser QA (programmatic chart control).
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      ;(window as any).__gmraiChart = chart;
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      ;(window as any).__gmraiChartApi = {
        getSeries: () => candleSeriesRef.current,
        getEma: () => emaSeriesRef.current,
        setCrosshair: (price: number, time: unknown) => {
          const ser = candleSeriesRef.current;
          if (ser) chart.setCrosshairPosition(price, time as never, ser);
        },
      };

      const candleSeries = chart.addSeries(CandlestickSeries, {
        upColor: '#26a69a',
        downColor: '#ef5350',
        borderUpColor: '#26a69a',
        borderDownColor: '#ef5350',
        wickUpColor: '#26a69a',
        wickDownColor: '#ef5350',
        priceLineVisible: false,
      });
      const emaSeries = chart.addSeries(LineSeries, {
        color: '#4c8dff',
        lineWidth: 1,
        priceLineVisible: false,
        lastValueVisible: false,
        crosshairMarkerVisible: false,
      });
      const aiPrim = new RegimeBandPrimitive();
      const refPrim = new RegimeBandPrimitive();
      const cursorPrim = new ReplayCursorPrimitive();
      candleSeries.attachPrimitive(aiPrim);
      candleSeries.attachPrimitive(refPrim);
      candleSeries.attachPrimitive(cursorPrim);

      chartRef.current = chart;
      candleSeriesRef.current = candleSeries;
      emaSeriesRef.current = emaSeries;
      aiBandPrimRef.current = aiPrim;
      refBandPrimRef.current = refPrim;
      cursorPrimRef.current = cursorPrim;

      // Crosshair move → legend (rAF-debounced).
      let raf = 0;
      const onCrosshairMove = (param: MouseEventParams<Time>) => {
        if (raf) return;
        raf = requestAnimationFrame(() => {
          raf = 0;
          if (!param.time) {
            setLegend(null);
            return;
          }
          const t = (param.time as number) * 1000;
          const times = candleTimesRef.current;
          const idx = bisectLeft(times, t / 1000);
          const bar = candleDataRef.current[idx];
          if (!bar || (bar.time as number) * 1000 > t + TF_BAR_MS[timeframeRef.current] + 1000) {
            setLegend(null);
            return;
          }
          const c = candlesRef.current[idx];
          const prev = idx > 0 ? candlesRef.current[idx - 1] : null;
          const bars = barsByTimeRef.current;
          const hb = bars ? bars.get(Math.floor(t / 1000)) ?? null : null;
          setLegend({
            time: c.ts,
            open: c.open,
            high: c.high,
            low: c.low,
            close: c.close,
            volume: c.tick_volume,
            prevClose: prev ? prev.close : null,
            ema: emaRef.current[idx] ?? null,
            regime: hb?.regime ?? null,
            refRegime: hb?.reference_regime ?? null,
          });
        });
      };
      chart.subscribeCrosshairMove(onCrosshairMove);

      // Band click → detail popover.
      const onClick = (param: MouseEventParams<Time>) => {
        if (!param.time || !param.point) {
          setPopover(null);
          return;
        }
        const t = (param.time as number);
        const aiBandsNow = aiBandsRef.current;
        const refBandsNow = refBandsRef.current;
        const band = aiBandsNow.find((b) => b.start <= t && t <= b.end) ?? null;
        const refBand = refBandsNow.find((b) => b.start <= t && t <= b.end) ?? null;
        const bars = barsByTimeRef.current;
        const hb = bars ? bars.get(t) ?? null : null;
        if (!band && !refBand && !hb) {
          setPopover(null);
          return;
        }
        const segMap = segmentsByStartRef.current;
        let segment: HistorySegment | null = null;
        if (band) {
          for (const [start, seg] of segMap ?? new Map()) {
            if (start <= t && t <= Math.floor(new Date(seg.end_ts).getTime() / 1000)) {
              segment = seg;
              break;
            }
          }
          if (!segment && band && segMap) {
            // Fallback: nearest segment start before t
            let best: HistorySegment | null = null;
            for (const seg of segMap.values()) {
              const s = Math.floor(new Date(seg.start_ts).getTime() / 1000);
              if (s <= t && (!best || s > Math.floor(new Date(best.start_ts).getTime() / 1000))) {
                best = seg;
              }
            }
            segment = best;
          }
        }
        const tsIso = new Date(t * 1000).toISOString();
        setPopover({
          detail: { ts: tsIso, band, refBand, bar: hb, segment },
          x: param.point.x,
          y: param.point.y,
        });
      };
      chart.subscribeClick(onClick);

      // Lazy-load older history when panning near the oldest loaded bar.
      const onVisibleRange = () => {
        const range = chart.timeScale().getVisibleLogicalRange();
        if (!range) return;
        if (range.from < 4 && hasMoreRef.current && !loadingMoreRef.current) {
          onLoadMoreRef.current?.();
        }
      };
      chart.timeScale().subscribeVisibleLogicalRangeChange(onVisibleRange);

      // Double-click on chart body resets time range (price axis handles its own reset).
      const onDblClick = (e: MouseEvent) => {
        const target = e.target as HTMLElement;
        if (target.tagName === 'CANVAS' && e.offsetX < el.clientWidth - 70) {
          const ts = chart.timeScale();
          ts.applyOptions({ barSpacing: DEFAULT_BAR_SPACING });
          ts.fitContent();
        }
      };
      el.addEventListener('dblclick', onDblClick);

      // Track width for popover flip (autoSize handles the chart canvas itself).
      const ro = new ResizeObserver((entries) => {
        for (const entry of entries) {
          const w = Math.floor(entry.contentRect.width);
          setContainerWidth((prev) => (prev === w ? prev : w));
        }
      });
      ro.observe(el);
      setContainerWidth(Math.floor(el.clientWidth));

      return () => {
        cancelAnimationFrame(raf);
        chart.unsubscribeCrosshairMove(onCrosshairMove);
        chart.unsubscribeClick(onClick);
        chart.timeScale().unsubscribeVisibleLogicalRangeChange(onVisibleRange);
        el.removeEventListener('dblclick', onDblClick);
        ro.disconnect();
        candleSeries.detachPrimitive(aiPrim);
        candleSeries.detachPrimitive(refPrim);
        candleSeries.detachPrimitive(cursorPrim);
        chart.remove();
        chartRef.current = null;
        candleSeriesRef.current = null;
        emaSeriesRef.current = null;
        volumeSeriesRef.current = null;
        aiBandPrimRef.current = null;
        refBandPrimRef.current = null;
        cursorPrimRef.current = null;
      };
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    // Refs mirroring latest props for the stable event handlers above.
    const candleDataRef = useRef(candleData);
    const candlesRef = useRef(candles);
    const candleTimesRef = useRef(candleTimes);
    const emaRef = useRef(emaValues);
    const aiBandsRef = useRef(aiBands ?? []);
    const refBandsRef = useRef(refBands ?? []);
    const barsByTimeRef = useRef(barsByTime ?? null);
    const segmentsByStartRef = useRef(segmentsByStart);
    useEffect(() => {
      candleDataRef.current = candleData;
      candlesRef.current = candles;
      candleTimesRef.current = candleTimes;
      emaRef.current = emaValues;
      aiBandsRef.current = aiBands ?? [];
      refBandsRef.current = refBands ?? [];
      barsByTimeRef.current = barsByTime ?? null;
      segmentsByStartRef.current = segmentsByStart;
    });

    // -----------------------------------------------------------------------
    // Data updates — setData only, no series re-creation.
    // -----------------------------------------------------------------------
    useEffect(() => {
      const ser = candleSeriesRef.current;
      if (!ser) return;

      if (!replayModeRef.current) {
        ser.setData(candleData);
        emaSeriesRef.current?.setData(emaData);
        if (volumeSeriesRef.current) volumeSeriesRef.current.setData(volumeData);
        prevCandleDataRef.current = candleData;
        return;
      }

      // Replay mode: reconcile the cursor-bounded window. A one-bar suffix
      // extension is applied via `update` (no re-init, no scroll jump); any
      // other change (shrink / prepend / reload) uses `setData` and best-effort
      // restores the previous visible logical range.
      const prev = prevCandleDataRef.current;
      let isAppend = prev.length > 0 && candleData.length === prev.length + 1;
      if (isAppend) {
        for (let i = 0; i < prev.length; i++) {
          if (prev[i].time !== candleData[i].time) {
            isAppend = false;
            break;
          }
        }
      }

      if (isAppend) {
        ser.update(candleData[candleData.length - 1]);
        if (volumeSeriesRef.current && volumeData.length > 0) {
          volumeSeriesRef.current.update(volumeData[volumeData.length - 1]);
        }
        if (emaSeriesRef.current && emaData.length > 0) {
          emaSeriesRef.current.update(emaData[emaData.length - 1]);
        }
      } else {
        const ts = chartRef.current?.timeScale();
        const range = ts?.getVisibleLogicalRange() ?? null;
        ser.setData(candleData);
        emaSeriesRef.current?.setData(emaData);
        if (volumeSeriesRef.current) volumeSeriesRef.current.setData(volumeData);
        if (range && range.from != null && range.to != null && ts && candleData.length > 0) {
          ts.setVisibleLogicalRange({ from: range.from, to: range.to });
        }
      }
      prevCandleDataRef.current = candleData;
    }, [candleData, emaData, volumeData]);

    // Regime band overlays.
    useEffect(() => {
      const chart = chartRef.current;
      const prim = aiBandPrimRef.current;
      if (prim) {
        prim.setBands(showAiBands ? aiBands ?? [] : []);
        prim.setVisible(showAiBands);
      }
      if (chart) {
        if (showAiBands && showRefBands) {
          aiBandPrimRef.current?.setArea('top');
          refBandPrimRef.current?.setArea('bottom');
        } else {
          aiBandPrimRef.current?.setArea('full');
          refBandPrimRef.current?.setArea('full');
        }
      }
    }, [aiBands, showAiBands, showRefBands]);

    useEffect(() => {
      const prim = refBandPrimRef.current;
      if (prim) {
        prim.setBands(showRefBands ? refBands ?? [] : []);
        prim.setVisible(showRefBands);
      }
    }, [refBands, showRefBands]);

    // Volume pane toggle.
    useEffect(() => {
      const chart = chartRef.current;
      if (!chart) return;
      if (showVolume && !volumeSeriesRef.current) {
        const vol = chart.addSeries(HistogramSeries, {
          priceScaleId: 'volume',
          priceFormat: { type: 'volume' },
          lastValueVisible: false,
          priceLineVisible: false,
        });
        chart.priceScale('volume').applyOptions({ scaleMargins: { top: 0.85, bottom: 0 } });
        volumeSeriesRef.current = vol;
        vol.setData(volumeData);
      } else if (!showVolume && volumeSeriesRef.current) {
        chart.removeSeries(volumeSeriesRef.current);
        volumeSeriesRef.current = null;
      }
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [showVolume]);

    // Grid toggle.
    useEffect(() => {
      chartRef.current?.applyOptions({
        grid: {
          vertLines: { visible: showGrid, color: 'rgba(139, 152, 169, 0.08)' },
          horzLines: { visible: showGrid, color: 'rgba(139, 152, 169, 0.08)' },
        },
      });
    }, [showGrid]);

    // Crosshair toggle.
    useEffect(() => {
      chartRef.current?.applyOptions({
        crosshair: {
          mode: showCrosshair ? CrosshairMode.Magnet : CrosshairMode.Normal,
          vertLine: {
            visible: showCrosshair,
            color: '#5b6a80',
            width: 1,
            style: 2,
            labelBackgroundColor: '#2a3240',
          },
          horzLine: {
            visible: showCrosshair,
            color: '#5b6a80',
            width: 1,
            style: 2,
            labelBackgroundColor: '#2a3240',
          },
        },
      });
    }, [showCrosshair]);

    // EMA visibility.
    useEffect(() => {
      emaSeriesRef.current?.applyOptions({ visible: showEma });
    }, [showEma]);

    // Auto scale.
    useEffect(() => {
      const chart = chartRef.current;
      if (!chart) return;
      chart.priceScale('right').applyOptions({ autoScale });
    }, [autoScale]);

    // Timeframe change → explicit reset to real time.
    useEffect(() => {
      const chart = chartRef.current;
      if (!chart) return;
      setLegend(null);
      setPopover(null);
      if (replayModeRef.current) return; // replay page drives the view after reload
      const ts = chart.timeScale();
      ts.applyOptions({ barSpacing: DEFAULT_BAR_SPACING });
      ts.scrollToRealTime();
      const range = ts.getVisibleLogicalRange();
      if (range && range.from !== null && range.to !== null && range.to - range.from > 400) {
        // Keep a sane default window after TF switches (~last 300 bars).
        const barCount = Math.max(1, Math.min(300, candleDataRef.current.length - 1));
        const last = candleTimesRef.current[candleTimesRef.current.length - 1];
        const first = candleTimesRef.current[Math.max(0, candleTimesRef.current.length - 1 - barCount)];
        if (last != null && first != null && last > first) {
          ts.setVisibleRange({ from: first, to: last as Time });
        }
      }
    }, [timeframe]);

    // -----------------------------------------------------------------------
    // Imperative API for the toolbar.
    // -----------------------------------------------------------------------
    const zoomIn = useCallback(() => {
      const ts = chartRef.current?.timeScale();
      if (!ts) return;
      const bs = ts.options().barSpacing;
      ts.applyOptions({ barSpacing: Math.min(60, bs * 1.35) });
    }, []);

    const zoomOut = useCallback(() => {
      const ts = chartRef.current?.timeScale();
      if (!ts) return;
      const bs = ts.options().barSpacing;
      ts.applyOptions({ barSpacing: Math.max(0.5, bs / 1.35) });
    }, []);

    const reset = useCallback(() => {
      const chart = chartRef.current;
      if (!chart) return;
      const ts = chart.timeScale();
      ts.applyOptions({ barSpacing: DEFAULT_BAR_SPACING });
      chart.priceScale('right').applyOptions({ autoScale: autoScaleRef.current });
      const times = candleTimesRef.current;
      if (times.length === 0) {
        ts.scrollToRealTime();
        return;
      }
      const last = times[times.length - 1];
      const first = times[Math.max(0, times.length - 1 - 300)];
      ts.setVisibleRange({ from: first, to: last as Time });
      setLegend(null);
      setPopover(null);
    }, []);

    const fitContent = useCallback(() => {
      chartRef.current?.timeScale().fitContent();
    }, []);

    const scrollToRealTime = useCallback(() => {
      chartRef.current?.timeScale().scrollToRealTime();
    }, []);

    const focusRange = useCallback((fromSec: number, toSec: number) => {
      chartRef.current?.timeScale().setVisibleRange({
        from: fromSec as Time,
        to: toSec as Time,
      });
    }, []);

    // -----------------------------------------------------------------------
    // Replay-mode imperative controls.
    // -----------------------------------------------------------------------

    const setCursor = useCallback((timeSec: number | null) => {
      cursorPrimRef.current?.setCursor(timeSec);
    }, []);

    const getVisibleLogicalRange = useCallback(() => {
      const range = chartRef.current?.timeScale().getVisibleLogicalRange();
      if (range && range.from != null && range.to != null) {
        return { from: range.from, to: range.to };
      }
      return null;
    }, []);

    const setVisibleLogicalRange = useCallback((from: number, to: number) => {
      chartRef.current?.timeScale().setVisibleLogicalRange({ from, to });
    }, []);

    useImperativeHandle(
      ref,
      () => ({
        zoomIn,
        zoomOut,
        reset,
        fitContent,
        scrollToRealTime,
        focusRange,
        setCursor,
        getVisibleLogicalRange,
        setVisibleLogicalRange,
      }),
      [
        zoomIn,
        zoomOut,
        reset,
        fitContent,
        scrollToRealTime,
        focusRange,
        setCursor,
        getVisibleLogicalRange,
        setVisibleLogicalRange,
      ]
    );

    const legendLabel = `XAUUSD · ${timeframe}`;

    return (
      <div className={styles.chartWrap}>
        <ChartOHLCLegend bar={legend} label={legendLabel} />
        <div className={styles.chartCanvasWrap} ref={containerRef} style={{ height }} />
        {loadingMore && (
          <div className={styles.loadingOlder}>
            <span className={styles.spinnerSm} /> Đang tải lịch sử cũ hơn…
          </div>
        )}
        {popover && (
          <RegimePopover
            detail={popover.detail}
            x={popover.x}
            y={popover.y}
            onClose={() => setPopover(null)}
            containerWidth={containerWidth}
          />
        )}
      </div>
    );
  }
);

export default TradingChartContainer;
