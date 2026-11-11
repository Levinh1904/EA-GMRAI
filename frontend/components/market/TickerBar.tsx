'use client';

// Top ticker bar for the Live Market page: symbol, last closed candle price,
// change vs previous closed candle, spread, market open/closed status, data
// connection status and last update time (UTC). All values from the real API.

import { fmtNum, fmtPrice, fmtUtc } from '@/lib/format';
import { useApi } from '@/lib/swr';
import type { Candle, FreshnessInfo, MarketTick, Timeframe } from '@/lib/types';
import styles from './market.module.css';

export interface MarketStatusInfo {
  status: 'open' | 'closed' | 'stale';
  label: string;
  reason: string;
}

export function deriveMarketStatus(
  lastTs: string | null | undefined,
  tfMs: number
): MarketStatusInfo {
  if (!lastTs) return { status: 'closed', label: 'Không có dữ liệu', reason: 'Chưa có nến' };
  const last = new Date(lastTs).getTime();
  if (Number.isNaN(last)) return { status: 'closed', label: 'Không có dữ liệu', reason: 'Sai định dạng thời gian' };
  const now = Date.now();
  const gapMin = (now - last) / 60000;
  const dow = new Date(now).getUTCDay();
  const weekend = dow === 0 || dow === 6;
  if (gapMin > 8 * 60) {
    return {
      status: 'closed',
      label: 'Đóng cửa / không cập nhật',
      reason: `Nến cuối cách đây ${Math.round(gapMin / 60)} giờ — thị trường có thể đang đóng cửa`,
    };
  }
  if (weekend && gapMin > (tfMs / 60000) * 2) {
    return {
      status: 'closed',
      label: 'Cuối tuần — đóng cửa',
      reason: 'Thị trường vàng đóng cửa cuối tuần (UTC)',
    };
  }
  return {
    status: 'open',
    label: 'Mở cửa',
    reason: `Nến cuối cách đây ${Math.round(gapMin)} phút`,
  };
}

export function TickerBar({
  last,
  prev,
  timeframe,
  freshness,
  loading,
}: {
  last: Candle | null;
  prev: Candle | null;
  timeframe: Timeframe;
  freshness: FreshnessInfo | undefined;
  loading: boolean;
}) {
  const tfMs = timeframe === 'M5' ? 300000 : timeframe === 'M15' ? 900000 : 3600000;
  const market = deriveMarketStatus(last?.ts, tfMs);
  const tick = useApi<MarketTick>('/market/tick', { refreshInterval: 2000 });

  const change = last && prev ? last.close - prev.close : null;
  const changePct = change != null && prev && prev.close ? (change / prev.close) * 100 : null;
  const dir = change == null ? '' : change > 0 ? styles.tickerUp : change < 0 ? styles.tickerDown : '';

  const connection = loading
    ? { tone: styles.dotNeutral, label: 'Đang kết nối…', title: 'Đang tải dữ liệu' }
    : freshness?.stale
      ? {
          tone: styles.dotDanger,
          label: 'Dữ liệu cũ',
          title: `Dữ liệu ${timeframe} cũ hơn ngưỡng ${freshness.threshold_minutes ?? '—'} phút`,
        }
      : {
          tone: styles.dotOk,
          label: 'Trực tiếp',
          title: `Dữ liệu mới (${freshness?.age_minutes?.toFixed(0) ?? '—'} phút)`,
        };

  const marketDot =
    market.status === 'open'
      ? styles.dotOk
      : market.status === 'stale'
        ? styles.dotWarn
        : styles.dotNeutral;

  return (
    <div className={styles.ticker}>
      <div className={styles.tickerMain}>
        <span className={styles.tickerSymbol}>XAUUSD</span>
        <span className={styles.tickerBadge}>{timeframe}</span>
        <span className={`${styles.tickerPrice} ${dir}`}>
          {tick.data?.bid != null ? fmtPrice(tick.data.bid) : last ? fmtPrice(last.close) : '—'}
        </span>
        <span className={`${styles.tickerChange} ${dir}`}>
          {change == null
            ? '—'
            : `${change >= 0 ? '+' : ''}${fmtPrice(change)} (${changePct != null && changePct >= 0 ? '+' : ''}${changePct?.toFixed(2) ?? '—'}%)`}
        </span>
        <span className={styles.tickerCell}>
          <span className={styles.tickerLabel}>Spread</span>
          <span className="num">{last ? fmtNum(last.spread, 1) : '—'}</span>
        </span>
        {last && (
          <span className={styles.tickerCell}>
            <span className={styles.tickerLabel}>Nến đóng</span>
            <span className="num">{fmtUtc(last.ts)}</span>
          </span>
        )}
      </div>
      <div className={styles.tickerMeta}>
        <span className={styles.tickerStatus} title={market.reason}>
          <span className={`${styles.dot} ${marketDot}`} />
          {market.label}
        </span>
        <span className={styles.tickerStatus} title={connection.title}>
          <span className={`${styles.dot} ${connection.tone}`} />
          {connection.label}
        </span>
        <span className={styles.tickerCell}>
          <span className={styles.tickerLabel}>Cập nhật</span>
          <span className="num">{last ? fmtUtc(last.ts) : '—'}</span>
        </span>
        {tick.data?.live && (
          <span className={styles.tickerCell} title={tick.data.note ?? ''}>
            <span className={styles.tickerLabel}>Bid trực tiếp</span>
            <span className="num" style={{ color: 'var(--accent)' }}>
              LIVE · {tick.data.bid != null ? fmtPrice(tick.data.bid) : '—'}
              {tick.data.age_seconds != null ? ` · ${tick.data.age_seconds.toFixed(0)}s` : ''}
            </span>
          </span>
        )}
      </div>
    </div>
  );
}
