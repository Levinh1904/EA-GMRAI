'use client';

// Live market chart for the trade_ens-only build. Only closed candles are
// loaded; there are no HMM/RF regime overlays or historical replay controls.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import dynamic from 'next/dynamic';
import { Badge, Card, EmptyState, ErrorState, Loading, Notice, PageHeader } from '@/components/ui/ui';
import { MarketStatsCard } from '@/components/market/MarketSections';
import { TickerBar } from '@/components/market/TickerBar';
import { ChartToolbar } from '@/components/charts/TradingChart/chartToolbar';
import type { TradingChartHandle } from '@/components/charts/TradingChart/TradingChartContainer';
import type { Band } from '@/components/charts/TradingChart/chartOverlays';
import { tsToSec, useCandlesPaged } from '@/components/charts/TradingChart/useChartData';
import { useApi } from '@/lib/swr';
import { fmtNum, fmtPrice, fmtUtcSec } from '@/lib/format';
import type { DashboardStats, MarketLatest, Timeframe, TradeHistory } from '@/lib/types';
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
  const [showVolume, setShowVolume] = useState(true);
  const [showGrid, setShowGrid] = useState(true);
  const [showCrosshair, setShowCrosshair] = useState(true);
  const [autoScale, setAutoScale] = useState(true);
  const [showEma, setShowEma] = useState(true);

  const chartRef = useRef<TradingChartHandle | null>(null);
  const fullscreenRef = useRef<HTMLDivElement | null>(null);

  const candles = useCandlesPaged(tf);
  const dashboard = useApi<DashboardStats>('/stats/dashboard', { refreshInterval: 10000 });
  const latest = useApi<MarketLatest>('/market/latest', { refreshInterval: 5000 });
  const tradeHistory = useApi<TradeHistory>('/trade-model/history?limit=5000', {
    refreshInterval: 60000,
  });

  const last = candles.candles.length ? candles.candles[candles.candles.length - 1] : null;
  const prev = candles.candles.length > 1 ? candles.candles[candles.candles.length - 2] : null;
  const latestCandle = latest.data?.latest?.[tf] ?? last;
  const freshness = dashboard.data?.data_freshness?.[tf];
  const demoSource = latestCandle?.source === 'synthetic_demo';

  // If the cheap /latest probe is newer than the paginated chart tail, refresh
  // the chart so the newest CLOSED candle is not missed.
  useEffect(() => {
    if (!latestCandle?.ts || !last?.ts) return;
    if (new Date(latestCandle.ts).getTime() > new Date(last.ts).getTime()) {
      candles.reload();
    }
  }, [latestCandle?.ts, last?.ts, candles.reload]);

  const signalBands = useMemo<Band[]>(() => {
    if (tf !== 'M15' || !tradeHistory.data) return [];
    const bars = tradeHistory.data.bars;
    const out: Band[] = [];
    let cur: Band | null = null;
    for (const b of bars) {
      if (b.signal !== 'LONG' && b.signal !== 'SHORT') {
        if (cur) out.push(cur);
        cur = null;
        continue;
      }
      const start = tsToSec(b.ts);
      const end = start + 900;
      if (!cur || cur.regime !== b.signal) {
        if (cur) out.push(cur);
        cur = { start, end, regime: b.signal };
      } else {
        cur.end = end;
      }
    }
    if (cur) out.push(cur);
    return out;
  }, [tf, tradeHistory.data]);

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
      <PageHeader
        title="Thị trường"
        subtitle="XAUUSD · nến đã đóng · chỉ hiển thị, không phải tín hiệu giao dịch"
      />

      <TickerBar
        last={latestCandle}
        prev={prev}
        timeframe={tf}
        freshness={freshness}
        loading={candles.loading}
      />

      {demoSource && (
        <Notice tone="warn">
          Nguồn <code>synthetic_demo</code> — dữ liệu tổng hợp, không phải thị trường thật.
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
            onFullscreen={handleFullscreen}
          />

          <div ref={fullscreenRef} className={styles.chartCard}>
            <div className={styles.chartHeader}>
              <span className={styles.closedCandlesBadge} title="Collector chỉ lưu nến đã đóng">
                Chỉ nến đã đóng
              </span>
              <span style={{ fontSize: 11.5, color: 'var(--text-tertiary)' }}>
                {latestCandle
                  ? `Nến đóng gần nhất: ${fmtUtcSec(latestCandle.ts)} · ${fmtPrice(latestCandle.close)} USD`
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
              <EmptyState title="Chưa có dữ liệu nến" hint="Thử khung thời gian khác" />
            )}
            {candles.candles.length > 0 && (
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
                showAiBands={tf === 'M15' && signalBands.length > 0}
                aiBands={signalBands}
                showRefBands={false}
              />
            )}
          </div>
        </div>
      </div>

      <div className={styles.legend}>
        <span className={styles.legendItem}><span className={styles.legendDot} style={{ background: '#22c55e' }} /> LONG</span>
        <span className={styles.legendItem}><span className={styles.legendDot} style={{ background: '#ef4444' }} /> SHORT</span>
        <span className={styles.legendItem} style={{ color: 'var(--text-faint)' }}>
          Dải tín hiệu từ lịch sử in-sample TRADE_ENS · chỉ M15
        </span>
      </div>

      <Card title="Thống kê dữ liệu" subtitle="/stats/dashboard">
        <MarketStatsCard
          dashboard={dashboard.data ?? null}
          loading={dashboard.isLoading}
          error={dashboard.error}
        />
      </Card>

      <Notice tone="info">
        Biểu đồ chỉ hiển thị nến đã đóng. Tín hiệu trade_ens nằm ở trang Trade Ens; GMRAI không
        gửi lệnh.
      </Notice>
    </div>
  );
}
