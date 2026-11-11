'use client';

// Historical Market Replay — step through real XAUUSD history bar-by-bar with
// the AI + Reference regime overlays, showing only data up to the replay cursor
// (no future information). Built on the shared lightweight-charts wrapper.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import dynamic from 'next/dynamic';
import { EmptyState, ErrorState, Loading, Notice } from '@/components/ui/ui';
import { ChartToolbar } from '@/components/charts/TradingChart/chartToolbar';
import type { TradingChartHandle } from '@/components/charts/TradingChart/TradingChartContainer';
import {
  useLatestDoneRun,
  useRunBars,
} from '@/components/charts/TradingChart/useChartData';
import { useHmmStateMap } from '@/app/(app)/history/shared';
import {
  asofJoinBars,
  buildBands,
  findCursorIndex,
  floorToBar,
  toSec,
  toSecMs,
  useReplayCandles,
} from '@/components/market/replay/useReplayData';
import { ReplayControls } from '@/components/market/replay/ReplayControls';
import { ReplaySidePanel } from '@/components/market/replay/ReplaySidePanel';
import { fmtNum, fmtUtcSec } from '@/lib/format';
import { regimeColor } from '@/lib/regime';
import type { Candle, HistoryBar, Timeframe } from '@/lib/types';
import rstyles from '@/components/market/replay/replay.module.css';
import pstyles from '../pages.module.css';

const TradingChartContainer = dynamic(
  () => import('@/components/charts/TradingChart/TradingChartContainer'),
  { ssr: false, loading: () => <Loading label="Đang khởi tạo biểu đồ nến…" /> }
);

const BASE_MS = 500; // 1x = 1 candle / 500ms

export default function ReplayPage() {
  const [tf, setTf] = useState<Timeframe>('M15');
  const [anchorDate, setAnchorDate] = useState<Date>(
    () => new Date(Date.now() - 7 * 24 * 3600 * 1000)
  );
  const [cursorTs, setCursorTs] = useState<number | null>(null);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [activeRange, setActiveRange] = useState<string | null>(null);

  // View toggles
  const [showVolume, setShowVolume] = useState(true);
  const [showGrid, setShowGrid] = useState(true);
  const [showCrosshair, setShowCrosshair] = useState(true);
  const [autoScale, setAutoScale] = useState(true);
  const [showEma, setShowEma] = useState(true);
  const [showAiBands, setShowAiBands] = useState(true);
  const [showRefBands, setShowRefBands] = useState(false);

  const chartRef = useRef<TradingChartHandle | null>(null);
  const fullscreenRef = useRef<HTMLDivElement | null>(null);

  const anchorMs = useMemo(() => floorToBar(anchorDate.getTime(), tf), [anchorDate, tf]);

  // ---- Data ---------------------------------------------------------------
  const { candles, loading, loadingOlder, loadingNewer, hasOlder, hasNewer, error, loadOlder, loadNewer } =
    useReplayCandles(tf, anchorMs);

  const doneRun = useLatestDoneRun();
  const { bars, isLoading: barsLoading } = useRunBars(doneRun?.id ?? null, true);
  const hmmStateMap = useHmmStateMap(doneRun?.hmm_model_version_id ?? null);

  // ---- Refs mirroring latest state for stable playback handlers -----------
  const candlesRef = useRef<Candle[]>([]);
  const cursorTsRef = useRef<number | null>(null);
  const hasNewerRef = useRef(false);
  useEffect(() => {
    candlesRef.current = candles;
  }, [candles]);
  useEffect(() => {
    cursorTsRef.current = cursorTs;
  }, [cursorTs]);
  useEffect(() => {
    hasNewerRef.current = hasNewer;
  }, [hasNewer]);

  // ---- Derived -------------------------------------------------------------
  const cursorIndex = useMemo(
    () => (candles.length && cursorTs != null ? findCursorIndex(candles, cursorTs) : -1),
    [candles, cursorTs]
  );
  const clampedIndex = cursorIndex < 0 ? -1 : cursorIndex;
  const visibleCandles = useMemo(
    () => (clampedIndex >= 0 ? candles.slice(0, clampedIndex + 1) : []),
    [candles, clampedIndex]
  );

  // Causal (as-of) join of M15 bars to the loaded candles.
  const joined = useMemo(() => asofJoinBars(candles, bars), [candles, bars]);
  const aiBands = useMemo(
    () => buildBands(visibleCandles, joined.slice(0, visibleCandles.length).map((hb) => hb?.regime ?? null)),
    [visibleCandles, joined]
  );
  const refBands = useMemo(
    () =>
      buildBands(
        visibleCandles,
        joined.slice(0, visibleCandles.length).map((hb) => hb?.reference_regime ?? null)
      ),
    [visibleCandles, joined]
  );
  const barsByTime = useMemo(() => {
    const m = new Map<number, HistoryBar>();
    for (let i = 0; i < visibleCandles.length; i++) {
      const hb = joined[i];
      if (hb) m.set(toSec(visibleCandles[i].ts), hb);
    }
    return m;
  }, [visibleCandles, joined]);

  const cursorCandle: Candle | null = clampedIndex >= 0 ? candles[clampedIndex] : null;
  const cursorBar: HistoryBar | null = clampedIndex >= 0 ? joined[clampedIndex] ?? null : null;
  const prevClose: number | null =
    clampedIndex > 0 ? candles[clampedIndex - 1].close : null;

  const cursorCount = clampedIndex >= 0 ? clampedIndex + 1 : 0;
  const nowText = cursorCandle
    ? `Đang phát: ${fmtUtcSec(cursorCandle.ts)} · nến #${cursorCount} / ${candles.length}`
    : 'Chưa có dữ liệu';

  const anchorInput = useMemo(() => {
    const d = anchorDate;
    const p = (n: number) => String(n).padStart(2, '0');
    return `${d.getUTCFullYear()}-${p(d.getUTCMonth() + 1)}-${p(d.getUTCDate())}T${p(d.getUTCHours())}:${p(d.getUTCMinutes())}`;
  }, [anchorDate]);

  // ---- Full reload lifecycle ----------------------------------------------
  // When the anchor or timeframe changes: reset the cursor to the anchor and
  // clear the chart until the new window arrives.
  useEffect(() => {
    setPlaying(false);
    if (anchorMs != null) setCursorTs(anchorMs);
    chartRef.current?.setCursor(null);
  }, [anchorMs, tf]);

  // Apply the freshly-loaded window once a reload completes.
  const applyFull = useCallback(() => {
    const cs = candlesRef.current;
    if (cs.length === 0) {
      chartRef.current?.setCursor(null);
      return;
    }
    const cts = cursorTsRef.current ?? toSecMs(cs[0].ts);
    let idx = findCursorIndex(cs, cts);
    if (idx < 0) idx = 0;
    const snapTs = toSecMs(cs[idx].ts);
    if (snapTs !== cursorTsRef.current) setCursorTs(snapTs);
    chartRef.current?.setCursor(toSec(cs[idx].ts));
  }, []);

  // Callback ref: also position the replay cursor once the chart mounts.
  const attachChart = useCallback((h: TradingChartHandle | null) => {
    chartRef.current = h;
    if (!h) return;
    const cs = candlesRef.current;
    const cts = cursorTsRef.current;
    if (cs.length > 0 && cts != null) {
      let idx = findCursorIndex(cs, cts);
      if (idx < 0) idx = 0;
      h.setCursor(toSec(cs[idx].ts));
    } else {
      h.setCursor(null);
    }
  }, []);

  const prevLoadingRef = useRef(true);
  useEffect(() => {
    if (loading) {
      prevLoadingRef.current = true;
      return;
    }
    const wasLoading = prevLoadingRef.current;
    prevLoadingRef.current = false;
    if (!wasLoading) return;
    applyFull();
  }, [loading, applyFull]);

  // ---- Transport handlers ---------------------------------------------------
  const stepForward = useCallback(() => {
    const cs = candlesRef.current;
    const cts = cursorTsRef.current;
    if (cs.length === 0 || cts == null) return;
    const idx = findCursorIndex(cs, cts);
    if (idx < 0) return;
    if (idx + 1 < cs.length) {
      const next = cs[idx + 1];
      setCursorTs(toSecMs(next.ts));
      chartRef.current?.setCursor(toSec(next.ts));
    } else if (hasNewerRef.current) {
      loadNewer();
    }
  }, [loadNewer]);

  const stepBack = useCallback(() => {
    const cs = candlesRef.current;
    const cts = cursorTsRef.current;
    if (cs.length === 0 || cts == null) return;
    const idx = findCursorIndex(cs, cts);
    if (idx <= 0) return;
    const prev = cs[idx - 1];
    setCursorTs(toSecMs(prev.ts));
    chartRef.current?.setCursor(toSec(prev.ts));
  }, []);

  const jumpToStart = useCallback(() => {
    const cs = candlesRef.current;
    if (cs.length === 0) return;
    setCursorTs(toSecMs(cs[0].ts));
    chartRef.current?.setCursor(toSec(cs[0].ts));
  }, []);

  const togglePlay = useCallback(() => setPlaying((p) => !p), []);

  // ---- Playback loop --------------------------------------------------------
  useEffect(() => {
    if (!playing) return;
    const interval = BASE_MS / speed;
    const id = window.setTimeout(() => {
      const cs = candlesRef.current;
      const cts = cursorTsRef.current;
      if (cs.length === 0 || cts == null) return;
      const idx = findCursorIndex(cs, cts);
      if (idx < 0) {
        setPlaying(false);
        return;
      }
      if (idx + 1 < cs.length) {
        const next = cs[idx + 1];
        setCursorTs(toSecMs(next.ts));
        chartRef.current?.setCursor(toSec(next.ts));
      } else if (hasNewerRef.current) {
        loadNewer();
      } else {
        setPlaying(false);
      }
    }, interval);
    return () => window.clearTimeout(id);
  }, [playing, speed, candles, cursorTs, loadNewer]);

  // ---- View actions ---------------------------------------------------------
  const handleTimeframeChange = useCallback(
    (next: Timeframe) => {
      if (next === tf) return;
      setActiveRange(null);
      setTf(next);
    },
    [tf]
  );

  const handleAnchorInput = useCallback((value: string) => {
    if (!value) return;
    const d = new Date(`${value}:00Z`);
    if (Number.isNaN(d.getTime())) return;
    setActiveRange(null);
    setAnchorDate(d);
  }, []);

  const handleRange = useCallback(
    (days: number | null, label: string) => {
      setActiveRange(label);
      const chart = chartRef.current;
      const cts = cursorTsRef.current;
      if (!chart || cts == null) return;
      if (days == null) {
        chart.fitContent();
        return;
      }
      const to = Math.floor(cts / 1000);
      const from = Math.floor((cts - days * 24 * 3600 * 1000) / 1000);
      chart.focusRange(from, to);
    },
    []
  );

  const handleFullscreen = useCallback(() => {
    const el = fullscreenRef.current;
    if (!el) return;
    if (document.fullscreenElement) void document.exitFullscreen();
    else void el.requestFullscreen?.();
  }, []);

  const canBack = clampedIndex > 0;
  const canForward = clampedIndex >= 0 && (clampedIndex < candles.length - 1 || hasNewer);

  const demoSource = candles[0]?.source === 'synthetic_demo';

  return (
    <div className={pstyles.stack}>
      <ReplayControls
        timeframe={tf}
        onTimeframeChange={handleTimeframeChange}
        anchorInput={anchorInput}
        onAnchorInput={handleAnchorInput}
        playing={playing}
        onTogglePlay={togglePlay}
        onJumpToStart={jumpToStart}
        onStepBack={stepBack}
        onStepForward={stepForward}
        speed={speed}
        onSpeedChange={setSpeed}
        canBack={canBack}
        canForward={canForward}
        nowText={nowText}
        disabled={loading}
      />

      {demoSource && (
        <Notice tone="warn">
          Nguồn dữ liệu: <code>synthetic_demo</code> — dữ liệu tổng hợp mô phỏng, không phải dữ
          liệu thị trường thực.
        </Notice>
      )}

      <div className={rstyles.replayLayout}>
        <div className={rstyles.chartColumn}>
          <ChartToolbar
            timeframe={tf}
            onTimeframeChange={handleTimeframeChange}
            activeRange={activeRange}
            onRange={handleRange}
            onZoomIn={() => chartRef.current?.zoomIn()}
            onZoomOut={() => chartRef.current?.zoomOut()}
            onReset={() => {
              setActiveRange(null);
              chartRef.current?.reset();
            }}
            onFitContent={() => {
              setActiveRange('TẤT CẢ');
              chartRef.current?.fitContent();
            }}
            autoScale={autoScale}
            onAutoScaleToggle={() => setAutoScale((v) => !v)}
            showGrid={showGrid}
            onGridToggle={() => setShowGrid((v) => !v)}
            showCrosshair={showCrosshair}
            onCrosshairToggle={() => setShowCrosshair((v) => !v)}
            showVolume={showVolume}
            onVolumeToggle={() => setShowVolume((v) => !v)}
            showEma={showEma}
            onEmaToggle={() => setShowEma((v) => !v)}
            showAiBands={showAiBands}
            onAiBandsToggle={() => setShowAiBands((v) => !v)}
            showRefBands={showRefBands}
            onRefBandsToggle={() => setShowRefBands((v) => !v)}
            onFullscreen={handleFullscreen}
          />

          <div ref={fullscreenRef} className={rstyles.chartCard}>
            <div className={rstyles.chartHeader}>
              <span className={rstyles.replayBadge}>
                Chế độ phát lại · không có thông tin tương lai
              </span>
              <span style={{ fontSize: 11.5, color: 'var(--text-tertiary)' }}>
                {candles.length > 0
                  ? `${fmtNum(visibleCandles.length, 0)}/${fmtNum(candles.length, 0)} nến đã hiển thị · con trỏ #${cursorCount}`
                  : '—'}
              </span>
            </div>

            {loading && candles.length === 0 && <Loading label="Đang tải nến quanh thời điểm đã chọn…" />}
            {error && candles.length === 0 && (
              <ErrorState error={error} title="Không thể tải dữ liệu nến" />
            )}
            {!loading && !error && candles.length === 0 && (
              <EmptyState title="Không có dữ liệu nến" hint="Hãy chọn thời điểm khác hoặc khung thời gian khác" />
            )}
            {candles.length > 0 && (
              <>
                <TradingChartContainer
                  ref={attachChart}
                  candles={visibleCandles}
                  timeframe={tf}
                  height={540}
                  showVolume={showVolume}
                  showGrid={showGrid}
                  showCrosshair={showCrosshair}
                  autoScale={autoScale}
                  showEma={showEma}
                  showAiBands={showAiBands}
                  showRefBands={showRefBands}
                  aiBands={aiBands}
                  refBands={refBands}
                  barsByTime={barsByTime}
                  replayMode
                />
                {barsLoading && <Notice tone="info">Đang tải dữ liệu run lịch sử (chế độ + reference)…</Notice>}
                <div className={rstyles.legendRow}>
                  {(showAiBands || showRefBands) && (
                    <>
                      {Object.entries({
                        TREND_UP: 'Xu hướng tăng',
                        TREND_DOWN: 'Xu hướng giảm',
                        SIDEWAYS: 'Đi ngang',
                        EARLY_TREND_UP: 'Tăng sớm',
                        EARLY_TREND_DOWN: 'Giảm sớm',
                        TRANSITION: 'Chuyển tiếp',
                        HIGH_VOLATILITY: 'Biến động cao',
                      }).map(([key, label]) => (
                        <span key={key} className={rstyles.legendItem}>
                          <span className={rstyles.legendDot} style={{ background: regimeColor(key) }} />
                          {label}
                        </span>
                      ))}
                      {showAiBands && showRefBands && (
                        <span className={rstyles.legendMuted}>(AI phía trên · Reference phía dưới)</span>
                      )}
                    </>
                  )}
                  <span className={rstyles.legendMuted}>
                    Múi giờ UTC · chế độ AI/Reference hiển thị theo nến M15 gần nhất tại thời điểm con trỏ
                  </span>
                </div>
                <div className={rstyles.loadRow}>
                  {hasOlder && (
                    <button type="button" className={rstyles.loadBtn} onClick={loadOlder} disabled={loadingOlder}>
                      {loadingOlder ? 'Đang tải…' : 'Tải cũ hơn'}
                    </button>
                  )}
                  {hasNewer && (
                    <button type="button" className={rstyles.loadBtn} onClick={loadNewer} disabled={loadingNewer}>
                      {loadingNewer ? 'Đang tải…' : 'Tải mới hơn'}
                    </button>
                  )}
                </div>
              </>
            )}
          </div>
        </div>

        <ReplaySidePanel
          candle={cursorCandle}
          bar={cursorBar}
          prevClose={prevClose}
          tf={tf}
          hmmStateMap={hmmStateMap}
          barsLoading={barsLoading}
          hasRun={doneRun != null}
        />
      </div>
    </div>
  );
}
