'use client';

// Live Market — professional trading view built on the lightweight-charts
// engine. All numbers come from the real FastAPI backend; the collector only
// stores CLOSED candles, so we show an honest "chỉ nến đã đóng" indicator,
// and there are no trade-signal markers (the signals toggle is disabled).

import { useCallback, useMemo, useRef, useState } from 'react';
import dynamic from 'next/dynamic';
import { Card, EmptyState, ErrorState, Loading, Notice } from '@/components/ui/ui';
import {
  MarketStatsCard,
  RecentTransitionsCard,
} from '@/components/market/MarketSections';
import { AiVsReferenceCard } from '@/components/market/AiVsReference';
import { RegimeSidePanel } from '@/components/market/RegimeSidePanel';
import { RegimeTimelineStrip } from '@/components/market/RegimeTimelineStrip';
import { TickerBar } from '@/components/market/TickerBar';
import {
  barsToReferenceBands,
  segmentsToBands,
  tsToSec,
  useBarsIndex,
  useCandlesPaged,
  useLatestDoneRun,
  useRunBars,
  useRunSegments,
} from '@/components/charts/TradingChart/useChartData';
import { ChartToolbar } from '@/components/charts/TradingChart/chartToolbar';
import type { TradingChartHandle } from '@/components/charts/TradingChart/TradingChartContainer';
import { useApi } from '@/lib/swr';
import { fmtNum } from '@/lib/format';
import { regimeColor } from '@/lib/regime';
import type { DashboardStats, MultiTfStatsResponse, RegimeLatest, Timeframe } from '@/lib/types';
import styles from '@/components/market/market.module.css';
import pstyles from '../pages.module.css';

const TradingChartContainer = dynamic(
  () => import('@/components/charts/TradingChart/TradingChartContainer'),
  { ssr: false, loading: () => <Loading label="Đang khởi tạo biểu đồ nến…" /> }
);

const TF_BAR_SEC: Record<Timeframe, number> = { M5: 300, M15: 900, H1: 3600 };

export default function MarketPage() {
  const [tf, setTf] = useState<Timeframe>('M15');
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

  // ---- Data ---------------------------------------------------------------
  const candles = useCandlesPaged(tf);
  const regime = useApi<RegimeLatest>('/regime/latest', { refreshInterval: 15000 });
  const dashboard = useApi<DashboardStats>('/stats/dashboard', { refreshInterval: 10000 });

  const doneRun = useLatestDoneRun();
  const { segments, isLoading: segLoading, error: segError } = useRunSegments(doneRun?.id ?? null);
  const overlaysOn = showAiBands || showRefBands;
  const { bars, isLoading: barsLoading, error: barsError } = useRunBars(
    doneRun?.id ?? null,
    overlaysOn
  );
  const barsByTime = useBarsIndex(bars);
  const multiTf = useApi<MultiTfStatsResponse>(
    doneRun ? `/history/runs/${doneRun.id}/stats/multi_tf` : null,
    { revalidateOnFocus: false, refreshInterval: 0 }
  );

  // ---- Derived -------------------------------------------------------------
  const last = candles.candles.length ? candles.candles[candles.candles.length - 1] : null;
  const prev = candles.candles.length > 1 ? candles.candles[candles.candles.length - 2] : null;
  const freshness = dashboard.data?.data_freshness?.[tf];

  const aiBands = useMemo(() => segmentsToBands(segments), [segments]);
  const refBands = useMemo(() => barsToReferenceBands(bars), [bars]);

  const lastBar = useMemo(() => {
    if (!bars.length) return null;
    const lastTs = last ? new Date(last.ts).getTime() : Infinity;
    // Latest bar at or before the newest loaded candle.
    for (let i = bars.length - 1; i >= 0; i--) {
      const t = new Date(bars[i].ts).getTime();
      if (t <= lastTs) return bars[i];
    }
    return bars[bars.length - 1];
  }, [bars, last]);

  const demoSource =
    candles.candles[0]?.source === 'synthetic_demo' ||
    regime.data?.data_source === 'synthetic_demo';

  // ---- Actions -------------------------------------------------------------
  const loadMore = useCallback(() => {
    void candles.loadMore();
  }, [candles]);

  const handleTimeframeChange = useCallback(
    (next: Timeframe) => {
      if (next === tf) return;
      setActiveRange(null);
      setTf(next);
    },
    [tf]
  );

  const handleRange = useCallback(
    (days: number | null, label: string) => {
      setActiveRange(label);
      const chart = chartRef.current;
      if (!chart) return;
      if (days == null) {
        chart.fitContent();
        return;
      }
      const times = candles.candles.map((c) => new Date(c.ts).getTime());
      if (times.length === 0) return;
      const toMs = times[times.length - 1];
      const fromMs = Math.max(times[0], toMs - days * 24 * 60 * 60 * 1000);
      const buffer = TF_BAR_SEC[tf] * 8;
      chart.focusRange(Math.floor(fromMs / 1000), Math.floor(toMs / 1000) + buffer);
    },
    [candles.candles, tf]
  );

  const handleStripFocus = useCallback(
    (ts: string) => {
      const chart = chartRef.current;
      if (!chart) return;
      const t = tsToSec(ts);
      const tfSec = TF_BAR_SEC[tf];
      chart.focusRange(t - tfSec * 12, t + tfSec * 80);
      setActiveRange(null);
    },
    [tf]
  );

  const handleFullscreen = useCallback(() => {
    const el = fullscreenRef.current;
    if (!el) return;
    if (document.fullscreenElement) {
      void document.exitFullscreen();
    } else {
      void el.requestFullscreen?.();
    }
  }, []);

  return (
    <div className={pstyles.stack}>
      <TickerBar
        last={last}
        prev={prev}
        timeframe={tf}
        freshness={freshness}
        loading={candles.loading}
      />

      {demoSource && (
        <Notice tone="warn">
          Nguồn dữ liệu: <code>synthetic_demo</code> — dữ liệu tổng hợp mô phỏng, không phải dữ
          liệu thị trường thực.
        </Notice>
      )}

      <div className={styles.marketLayout}>
        <div className={styles.chartColumn}>
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

          <div ref={fullscreenRef} className={styles.chartCard}>
            <div className={styles.chartHeader}>
              <span className={styles.closedCandlesBadge} title="Collector chỉ lưu nến đã đóng — không có nến đang hình thành">
                Chỉ nến đã đóng
              </span>
              <span style={{ fontSize: 11.5, color: 'var(--text-tertiary)' }}>
                {candles.candles.length > 0
                  ? `${fmtNum(candles.candles.length, 0)} / ${fmtNum(candles.total, 0)} nến đã tải · nguồn ${last?.source ?? '—'}`
                  : '—'}
              </span>
            </div>

            {candles.loading && candles.candles.length === 0 && (
              <Loading label="Đang tải nến…" />
            )}
            {candles.error && candles.candles.length === 0 && (
              <ErrorState error={candles.error} onRetry={candles.reload} />
            )}
            {!candles.loading && !candles.error && candles.candles.length === 0 && (
              <EmptyState title="Chưa có dữ liệu nến" hint="Hãy thử khung thời gian khác" />
            )}
            {candles.candles.length > 0 && (
              <>
                <TradingChartContainer
                  ref={chartRef}
                  candles={candles.candles}
                  timeframe={tf}
                  height={540}
                  hasMore={candles.hasMore}
                  loadingMore={candles.loadingMore}
                  onLoadMore={loadMore}
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
                  segments={segments}
                />
                {barsLoading && overlaysOn && (
                  <Notice tone="info">
                    Đang tải dữ liệu run lịch sử (chế độ + reference)… dải regime sẽ hiện sau khi
                    tải xong.
                  </Notice>
                )}
                {barsError && overlaysOn && (
                  <Notice tone="warn">
                    Không thể tải dữ liệu chế độ theo từng nến: {String(barsError)}
                  </Notice>
                )}
                {segError && showAiBands && (
                  <Notice tone="warn">Không thể tải segments chế độ AI: {String(segError)}</Notice>
                )}
                <div className={styles.legend}>
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
                        <span key={key} className={styles.legendItem}>
                          <span className={styles.legendDot} style={{ background: regimeColor(key) }} />
                          {label}
                        </span>
                      ))}
                      {showAiBands && showRefBands && (
                        <span className={styles.legendItem} style={{ color: 'var(--text-faint)' }}>
                          (AI phía trên · Reference phía dưới)
                        </span>
                      )}
                    </>
                  )}
                  <span className={styles.legendItem} style={{ color: 'var(--text-faint)' }}>
                    Bấm vào vùng nền regime để xem chi tiết đoạn
                  </span>
                </div>
              </>
            )}
          </div>
        </div>

        <RegimeSidePanel
          regime={regime.data ?? null}
          regimeError={regime.error}
          regimeLoading={regime.isLoading}
          lastBar={lastBar}
          multiTf={multiTf.data ?? null}
        />
      </div>

      <div className={`${pstyles.grid} ${pstyles.cols2}`}>
        <RegimeTimelineStrip
          bars={bars}
          loading={barsLoading}
          error={barsError}
          mode="ai"
          onFocus={handleStripFocus}
          count={240}
        />
        <AiVsReferenceCard bars={bars} loading={barsLoading} error={barsError} />
      </div>

      <div className={`${pstyles.grid} ${pstyles.cols2}`}>
        <MarketStatsCard
          dashboard={dashboard.data ?? null}
          loading={dashboard.isLoading}
          error={dashboard.error}
        />
        <RecentTransitionsCard segments={segments} loading={segLoading} error={segError} />
      </div>

      <div className={pstyles.muted} style={{ fontSize: 12 }}>
        Dải chế độ AI lấy từ run lịch sử mới nhất (#{doneRun?.id ?? '—'}, M15). Biểu đồ chỉ hiển thị
        nến đã đóng — collector không gửi nến đang hình thành. Kéo sang trái để tải thêm lịch sử cũ
        hơn (phân trang 5000 nến/trang). Múi giờ hiển thị: UTC.
      </div>
    </div>
  );
}
