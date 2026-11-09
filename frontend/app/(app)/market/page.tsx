'use client';

import dynamic from 'next/dynamic';
import { useMemo, useState } from 'react';
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorState,
  Loading,
  Notice,
  PageHeader,
  Segmented,
  Stat,
} from '@/components/ui/ui';
import { api } from '@/lib/api';
import { fmtNum, fmtPrice, fmtUtc } from '@/lib/format';
import { alignRegimePerCandle, computeEma, lastChangePct } from '@/lib/market';
import { regimeColor, regimeLabel } from '@/lib/regime';
import { useApi } from '@/lib/swr';
import type { Candle, MarketLatest, RegimeHistoryResponse, Timeframe } from '@/lib/types';
import styles from '../pages.module.css';

const CandlestickChart = dynamic(() => import('@/components/charts/CandlestickChart'), {
  ssr: false,
  loading: () => <Loading label="Đang tải biểu đồ nến…" />,
});
const RegimeStripChart = dynamic(() => import('@/components/charts/RegimeStripChart'), {
  ssr: false,
});

const TF_OPTIONS: Array<{ value: Timeframe; label: string }> = [
  { value: 'M5', label: 'M5' },
  { value: 'M15', label: 'M15' },
  { value: 'H1', label: 'H1' },
];

const TF_BAR_MS: Record<Timeframe, number> = { M5: 5 * 60 * 1000, M15: 15 * 60 * 1000, H1: 3600 * 1000 };
const TF_LABEL: Record<Timeframe, string> = { M5: 'M5', M15: 'M15', H1: 'H1' };

export default function MarketPage() {
  const [tf, setTf] = useState<Timeframe>('M15');
  const [extra, setExtra] = useState<Candle[]>([]);
  const [nextOffset, setNextOffset] = useState(500);
  const [total, setTotal] = useState<number | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  const { data, error, isLoading } = useApi<{
    total: number;
    limit: number;
    offset: number;
    candles: Candle[];
  }>(`/market/candles?timeframe=${tf}&limit=500&offset=0&symbol=XAUUSD`, {
    refreshInterval: 60000,
  });
  const history = useApi<RegimeHistoryResponse>('/regime/history?limit=500', {
    refreshInterval: 60000,
  });
  const latest = useApi<MarketLatest>('/market/latest', { refreshInterval: 30000 });

  function switchTf(next: Timeframe) {
    if (next === tf) return;
    setTf(next);
    setExtra([]);
    setNextOffset(500);
    setTotal(null);
    setLoadError(null);
  }

  const candles = useMemo<Candle[]>(() => [...extra, ...(data?.candles ?? [])], [extra, data]);

  const ema = useMemo(
    () => computeEma(candles.map((c) => c.close), 20),
    [candles]
  );
  const regimes = useMemo(
    () => alignRegimePerCandle(candles, history.data?.history ?? []),
    [candles, history.data]
  );

  const last = candles.length ? candles[candles.length - 1] : null;
  const changePct = lastChangePct(candles);
  const lastEma = [...ema].reverse().find((v) => v != null) ?? null;
  const hasMore = total != null && total > nextOffset;
  const demoSource = data?.candles[0]?.source === 'synthetic_demo';

  async function loadMore() {
    if (loadingMore) return;
    setLoadingMore(true);
    setLoadError(null);
    try {
      const resp = await api.candles(tf, 500, nextOffset);
      setExtra((prev) => [...resp.candles, ...prev]);
      setNextOffset(resp.offset + resp.limit);
      setTotal(resp.total);
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : 'Tải thêm dữ liệu thất bại');
    } finally {
      setLoadingMore(false);
    }
  }

  return (
    <div className={styles.stack}>
      <PageHeader
        title="Thị trường trực tiếp"
        subtitle="Biểu đồ nến XAUUSD với EMA20 và nền chế độ thị trường"
        right={<Segmented options={TF_OPTIONS} value={tf} onChange={switchTf} />}
      />

      {demoSource && (
        <Notice tone="warn">
          Nguồn dữ liệu: <code>synthetic_demo</code> — dữ liệu tổng hợp mô phỏng, không phải dữ
          liệu thị trường thực.
        </Notice>
      )}

      {last && (
        <div className={`${styles.grid} ${styles.cols4}`}>
          <Card title={`Giá cuối ${TF_LABEL[tf]}`}>
            <Stat
              label="Close"
              value={fmtPrice(last.close)}
              sub={`${fmtUtc(last.ts)}`}
              tone={changePct != null && changePct >= 0 ? 'up' : changePct != null ? 'down' : 'neutral'}
            />
          </Card>
          <Card title="Thay đổi (nến trước)">
            <Stat
              label="Delta"
              value={changePct != null ? `${changePct >= 0 ? '+' : ''}${changePct.toFixed(2)}%` : '—'}
              sub={last.open ? `mở cửa ${fmtPrice(last.open)}` : '—'}
              tone={changePct != null && changePct >= 0 ? 'up' : changePct != null ? 'down' : 'neutral'}
            />
          </Card>
          <Card title="EMA20">
            <Stat label="Giá trị" value={lastEma != null ? fmtPrice(lastEma) : '—'} sub="chu kỳ 20 nến" />
          </Card>
          <Card title="Thanh khoản & chênh lệch">
            <Stat
              label="Tick volume"
              value={fmtNum(last.tick_volume, 0)}
              sub={`spread ${last.spread} điểm`}
            />
          </Card>
        </div>
      )}

      <Card
        title={`Biểu đồ nến ${TF_LABEL[tf]} — XAUUSD`}
        subtitle={
          candles.length
            ? `${fmtNum(candles.length, 0)} / ${total != null ? fmtNum(total, 0) : '…'} nến · nguồn: ${
                last?.source ?? '—'
              }`
            : undefined
        }
      >
        {isLoading && candles.length === 0 && <Loading label="Đang tải nến…" />}
        {error && candles.length === 0 && <ErrorState error={error} />}
        {!isLoading && !error && candles.length === 0 && (
          <EmptyState title="Chưa có dữ liệu nến" hint="Hãy thử khung thời gian khác" />
        )}
        {candles.length > 0 && (
          <>
            <div className={styles.chartBox}>
              <CandlestickChart
                candles={candles}
                ema={ema}
                regimes={regimes}
                height={470}
                title={`${TF_LABEL[tf]} · nến + EMA20 · nền màu = chế độ thị trường (HMM)`}
              />
            </div>
            <div className={styles.chartBox} style={{ marginTop: 10 }}>
              <RegimeStripChart
                points={candles.map((c, i) => ({ ts: c.ts, regime: regimes[i] ?? null }))}
                barWidthMs={TF_BAR_MS[tf]}
                height={96}
              />
            </div>
            <div className={styles.legend}>
              {Object.entries({
                TREND_UP: 'Xu hướng tăng',
                TREND_DOWN: 'Xu hướng giảm',
                SIDEWAYS: 'Đi ngang',
                HIGH_VOLATILITY: 'Biến động cao',
                TRANSITION: 'Chuyển tiếp',
                EARLY_TREND_UP: 'Tăng sớm',
                EARLY_TREND_DOWN: 'Giảm sớm',
                UNKNOWN: 'Không xác định',
              }).map(([key, label]) => (
                <span key={key} className={styles.legendItem}>
                  <span className={styles.legendDot} style={{ background: regimeColor(key) }} />
                  {label}
                </span>
              ))}
            </div>
            <div className={styles.toolbar} style={{ marginTop: 14, marginBottom: 0 }}>
              <Button onClick={loadMore} disabled={loadingMore || !hasMore}>
                {loadingMore ? 'Đang tải…' : `Tải thêm 500 nến (offset ${nextOffset})`}
              </Button>
              {total != null && (
                <span className={styles.muted}>
                  Đã tải {fmtNum(candles.length, 0)} / {fmtNum(total, 0)} nến (phân trang theo offset)
                </span>
              )}
            </div>
            {loadError && <Notice tone="danger">{loadError}</Notice>}
          </>
        )}
      </Card>

      <Card title="Giá mới nhất theo khung thời gian">
        {latest.isLoading && <Loading />}
        {latest.error && <ErrorState error={latest.error} />}
        {latest.data && (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>TF</th>
                  <th>Thời gian (UTC)</th>
                  <th className="num">Mở</th>
                  <th className="num">Cao</th>
                  <th className="num">Thấp</th>
                  <th className="num">Đóng</th>
                  <th className="num">Volume</th>
                  <th className="num">Spread</th>
                  <th>Nguồn</th>
                </tr>
              </thead>
              <tbody>
                {(['M5', 'M15', 'H1'] as Timeframe[]).map((t) => {
                  const c = latest.data?.latest[t];
                  if (!c) return null;
                  return (
                    <tr key={t}>
                      <td>
                        <Badge tone="neutral">{t}</Badge>
                      </td>
                      <td className="mono">{fmtUtc(c.ts)}</td>
                      <td className="num">{fmtPrice(c.open)}</td>
                      <td className="num">{fmtPrice(c.high)}</td>
                      <td className="num">{fmtPrice(c.low)}</td>
                      <td className="num">{fmtPrice(c.close)}</td>
                      <td className="num">{fmtNum(c.tick_volume, 0)}</td>
                      <td className="num">{c.spread}</td>
                      <td>
                        <Badge tone={c.source === 'synthetic_demo' ? 'yellow' : 'teal'}>{c.source}</Badge>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <div className={styles.muted} style={{ fontSize: 12 }}>
        Chế độ thị trường lấy từ lịch sử HMM (/regime/history), gán cho mỗi cây nến theo tín hiệu
        gần nhất trước thời điểm của nến đó.
      </div>
    </div>
  );
}
