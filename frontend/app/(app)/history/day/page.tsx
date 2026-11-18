'use client';

// Day History — "what happened on a given day". Causal per-day replay of the
// approved models against one UTC day of M15 bars: OHLC summary, AI regime
// distribution, the independent reference engine's distribution, segments and
// a per-bar table. Yesterday is the default view.
//
// Everything comes from GET /api/v1/history/day (real backend only); the
// endpoint only uses bars before the end of the selected day, so browsing the
// past can never peek at later data.

import dynamic from 'next/dynamic';
import Link from 'next/link';
import { useMemo, useState } from 'react';
import {
  Badge,
  Card,
  EmptyState,
  ErrorState,
  Loading,
  Notice,
  PageHeader,
  RegimeBadge,
  Stat,
} from '@/components/ui/ui';
import { fmtNum, fmtPrice, fmtUtc } from '@/lib/format';
import { regimeColor, regimeLabel } from '@/lib/regime';
import { useApi } from '@/lib/swr';
import type {
  DirectionAccuracyResponse,
  Permission,
  Regime,
  WrongDirectionResponse,
} from '@/lib/types';
import styles from '../../pages.module.css';

const HGroupedBars = dynamic(
  () => import('@/components/charts/HistoryCharts').then((m) => m.HGroupedBars),
  { ssr: false, loading: () => <Loading label="Đang tải biểu đồ…" /> }
);

const RegimeStripChart = dynamic(() => import('@/components/charts/RegimeStripChart'), {
  ssr: false,
});

interface DayBar {
  ts: string;
  regime: Regime;
  confidence: number;
  permission: Permission | null;
  reference_regime: Regime | null;
  reference_reason: string | null;
  hmm_state: number;
  hmm_posterior: number[] | null;
  rf_probs: Record<string, number> | null;
  reason_codes: string[] | null;
  open: number;
  high: number;
  low: number;
  close: number;
  atr_ratio: number | null;
  adx_norm: number | null;
  efficiency_ratio: number | null;
  h1_trend_context: number | null;
  m5_momentum: number | null;
}

interface DaySegment {
  segment_index: number;
  regime: Regime;
  start_ts: string;
  end_ts: string;
  bar_count: number;
  duration_minutes: number;
  start_price: number;
  end_price: number;
  net_change: number;
  mfe: number;
  mae: number;
}

interface DayAnalysis {
  symbol: string;
  day: string;
  data_source: string;
  bar_count: number;
  open?: number;
  close?: number;
  high?: number;
  low?: number;
  net_change?: number;
  net_change_pct?: number;
  range?: number;
  model_versions?: { hmm: number; rf: number };
  summary: {
    regime_bars?: Record<string, number>;
    reference_bars?: Record<string, number>;
    segment_count?: number;
    first_bar?: string;
    last_bar?: string;
  };
  segments: DaySegment[];
  bars: DayBar[];
  direction_accuracy?: DirectionAccuracyResponse;
  wrong_direction?: WrongDirectionResponse;
  reason?: string;
  note?: string;
}

/** Local (browser tz) date as YYYY-MM-DD — used to seed the default day picker. */
function yesterdayIso(): string {
  const d = new Date(Date.now() - 24 * 3600 * 1000);
  return d.toISOString().slice(0, 10);
}

function ShareBars({
  data,
  total,
}: {
  data: Record<string, number>;
  total: number;
}) {
  const rows = Object.entries(data).sort((a, b) => b[1] - a[1]);
  if (rows.length === 0) return <EmptyState hint="Không có dữ liệu" />;
  return (
    <div className={styles.probCol} style={{ gap: 6 }}>
      {rows.map(([regime, n]) => {
        const pct = total > 0 ? (n / total) * 100 : 0;
        return (
          <div key={regime} style={{ display: 'grid', gap: 4 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12.5 }}>
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                <span
                  style={{
                    width: 9,
                    height: 9,
                    borderRadius: 2,
                    background: regimeColor(regime),
                  }}
                />
                {regimeLabel(regime)}
              </span>
              <span className="mono">
                {n} nến · {fmtNum(pct, 1)}%
              </span>
            </div>
            <div className={styles.confidenceBar}>
              <div
                className={styles.confidenceFill}
                style={{ width: `${pct}%`, background: regimeColor(regime) }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}

export default function HistoryDayPage() {
  const [day, setDay] = useState<string>(yesterdayIso());

  const { data, error, isLoading, mutate } = useApi<DayAnalysis>(
    `/history/day?day=${encodeURIComponent(day)}`,
    { revalidateOnFocus: false, refreshInterval: 0 }
  );

  const points = useMemo(
    () => (data?.bars ?? []).map((b) => ({ ts: b.ts, regime: b.regime })),
    [data]
  );
  const changeTone =
    data?.net_change == null ? undefined : data.net_change > 0 ? 'up' : data.net_change < 0 ? 'down' : 'neutral';

  return (
    <div className={styles.stack}>
      <PageHeader
        title="Lịch sử theo ngày"
        subtitle="Xem lại một ngày đã qua: giá, chế độ AI và chế độ tham chiếu (nhân quả, không nhìn tương lai)"
        right={
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <input
              type="date"
              value={day}
              max={new Date().toISOString().slice(0, 10)}
              onChange={(e) => setDay(e.target.value)}
              style={{
                background: 'var(--bg-elevated)',
                color: 'var(--text-primary)',
                border: '1px solid var(--border)',
                borderRadius: 6,
                padding: '6px 10px',
                fontSize: 13,
              }}
            />
            <button
              type="button"
              onClick={() => setDay(yesterdayIso())}
              style={{
                background: 'var(--bg-elevated)',
                color: 'var(--text-primary)',
                border: '1px solid var(--border)',
                borderRadius: 6,
                padding: '6px 10px',
                fontSize: 12.5,
                cursor: 'pointer',
              }}
            >
              Hôm qua
            </button>
            <button
              type="button"
              onClick={() => void mutate()}
              style={{
                background: 'var(--bg-elevated)',
                color: 'var(--text-primary)',
                border: '1px solid var(--border)',
                borderRadius: 6,
                padding: '6px 10px',
                fontSize: 12.5,
                cursor: 'pointer',
              }}
            >
              Tải lại
            </button>
          </div>
        }
      />

      {isLoading && <Loading label="Đang phân tích ngày…" />}
      {error && <ErrorState error={error} onRetry={() => void mutate()} />}

      {data && data.reason === 'NO_DATA_FOR_DAY' && (
        <Notice tone="warn">
          <strong>Không có dữ liệu cho {data.day}.</strong> {data.note}
        </Notice>
      )}

      {data && !data.reason && (
        <>
          <div className={`${styles.grid} ${styles.cols4}`}>
            <Stat label="Ngày (UTC)" value={data.day} sub={`${data.bar_count} nến M15`} />
            <Stat
              label="Đóng cửa"
              value={fmtPrice(data.close)}
              sub={`Mở ${fmtPrice(data.open)}`}
              tone={changeTone}
            />
            <Stat
              label="Thay đổi trong ngày"
              value={
                data.net_change != null
                  ? `${data.net_change >= 0 ? '+' : ''}${fmtNum(data.net_change, 2)}`
                  : '—'
              }
              sub={
                data.net_change_pct != null
                  ? `${data.net_change_pct >= 0 ? '+' : ''}${fmtNum(data.net_change_pct, 2)}%`
                  : undefined
              }
              tone={changeTone}
            />
            <Stat
              label="Biên độ"
              value={fmtNum(data.range, 2)}
              sub={`${fmtPrice(data.low)} – ${fmtPrice(data.high)}`}
            />
          </div>

          <Notice tone="info">
            Nguồn dữ liệu <code>{data.data_source}</code> · mô hình HMM v{data.model_versions?.hmm} + RF v
            {data.model_versions?.rf} · nến {fmtUtc(data.summary.first_bar)} → {fmtUtc(data.summary.last_bar)}
          </Notice>

          <Card title="Dải chế độ trong ngày" subtitle="mỗi màu là chế độ AI của nến M15 tại thời điểm đó">
            {points.length > 0 ? (
              <div className={styles.chartBox}>
                <RegimeStripChart points={points} height={90} />
              </div>
            ) : (
              <EmptyState hint="Không có nến" />
            )}
          </Card>

          <div className={`${styles.grid} ${styles.cols2}`}>
            <Card title="Phân bố chế độ AI" subtitle="số nến theo từng chế độ">
              <ShareBars data={data.summary.regime_bars ?? {}} total={data.bar_count} />
            </Card>
            <Card
              title="Phân bố chế độ tham chiếu (ref_v1)"
              subtitle="bộ phân loại luật độc lập — dùng để đối chiếu"
            >
              <ShareBars data={data.summary.reference_bars ?? {}} total={data.bar_count} />
            </Card>
          </div>

          <Card
            title="Đoạn chế độ trong ngày"
            subtitle={`${data.segments.length} đoạn liên tục`}
          >
            {data.segments.length === 0 ? (
              <EmptyState hint="Không có đoạn" />
            ) : (
              <div className="table-wrap">
                <table className="table">
                  <thead>
                    <tr>
                      <th>#</th>
                      <th>Chế độ</th>
                      <th>Từ</th>
                      <th>Đến</th>
                      <th className="num">Nến</th>
                      <th className="num">Phút</th>
                      <th className="num">Mở</th>
                      <th className="num">Đóng</th>
                      <th className="num">Thay đổi</th>
                      <th className="num">MFE</th>
                      <th className="num">MAE</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.segments.map((s) => (
                      <tr key={`${s.segment_index}-${s.start_ts}`}>
                        <td className="mono">{s.segment_index}</td>
                        <td>
                          <RegimeBadge regime={s.regime} />
                        </td>
                        <td className="mono">{fmtUtc(s.start_ts)}</td>
                        <td className="mono">{fmtUtc(s.end_ts)}</td>
                        <td className="num">{s.bar_count}</td>
                        <td className="num">{s.duration_minutes}</td>
                        <td className="num">{fmtPrice(s.start_price)}</td>
                        <td className="num">{fmtPrice(s.end_price)}</td>
                        <td className="num" style={{ color: s.net_change >= 0 ? 'var(--status-ok)' : 'var(--status-danger)' }}>
                          {s.net_change >= 0 ? '+' : ''}
                          {fmtNum(s.net_change, 2)}
                        </td>
                        <td className="num">{fmtNum(s.mfe, 2)}</td>
                        <td className="num">{fmtNum(s.mae, 2)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>

          {/* ---------------- Direction accuracy for this day ---------------- */}
          {data.direction_accuracy && (
            <Card
              title="Độ chính xác hướng trong ngày"
              subtitle="tín hiệu tăng/giảm có khớp với giá thực tế của ngày này không"
            >
              {data.direction_accuracy.sample && (
                <Notice
                  tone={
                    data.direction_accuracy.sample.reliability === 'ok'
                      ? 'info'
                      : 'warn'
                  }
                >
                  <strong>
                    {data.direction_accuracy.sample.segments} đoạn xu hướng trong ngày
                  </strong>{' '}
                  — {data.direction_accuracy.sample.note}
                </Notice>
              )}

              <div className={`${styles.grid} ${styles.cols4}`} style={{ marginTop: 12 }}>
                <Stat
                  label="Xu hướng tăng"
                  value={`${fmtNum(data.direction_accuracy.per_segment.by_regime.TREND_UP?.accuracy_pct, 1)}%`}
                  sub={
                    data.direction_accuracy.per_segment.by_regime.TREND_UP?.total
                      ? `${fmtNum(data.direction_accuracy.per_segment.by_regime.TREND_UP.correct, 0)}/${fmtNum(data.direction_accuracy.per_segment.by_regime.TREND_UP.total, 0)} đoạn`
                      : 'không có đoạn'
                  }
                  tone={
                    (data.direction_accuracy.per_segment.by_regime.TREND_UP?.accuracy_pct ?? 0) >= 50
                      ? 'up'
                      : 'down'
                  }
                />
                <Stat
                  label="Xu hướng giảm"
                  value={`${fmtNum(data.direction_accuracy.per_segment.by_regime.TREND_DOWN?.accuracy_pct, 1)}%`}
                  sub={
                    data.direction_accuracy.per_segment.by_regime.TREND_DOWN?.total
                      ? `${fmtNum(data.direction_accuracy.per_segment.by_regime.TREND_DOWN.correct, 0)}/${fmtNum(data.direction_accuracy.per_segment.by_regime.TREND_DOWN.total, 0)} đoạn`
                      : 'không có đoạn'
                  }
                  tone={
                    (data.direction_accuracy.per_segment.by_regime.TREND_DOWN?.accuracy_pct ?? 0) >= 50
                      ? 'up'
                      : 'down'
                  }
                />
                <Stat
                  label="Sai hướng"
                  value={fmtNum(data.wrong_direction?.wrong_total, 0)}
                  sub={`trên ${fmtNum(data.direction_accuracy.per_segment.overall.total, 0)} đoạn`}
                  tone="down"
                />
                <Stat
                  label="Đi ngược TB"
                  value={`${fmtNum(data.wrong_direction?.loss?.mean_adverse_pct, 3)}%`}
                  sub={`tệ nhất ${fmtNum(data.wrong_direction?.loss?.worst_adverse_pct, 3)}%`}
                  tone="down"
                />
              </div>

              {(data.direction_accuracy.per_segment.by_regime.TREND_UP?.total ||
                data.direction_accuracy.per_segment.by_regime.TREND_DOWN?.total) && (
                <div style={{ marginTop: 16 }}>
                  <HGroupedBars
                    labels={['Xu hướng tăng', 'Xu hướng giảm']}
                    series={[
                      {
                        name: 'Đúng hướng',
                        values: [
                          data.direction_accuracy.per_segment.by_regime.TREND_UP?.accuracy_pct ?? 0,
                          data.direction_accuracy.per_segment.by_regime.TREND_DOWN?.accuracy_pct ?? 0,
                        ],
                        color: '#22c55e',
                      },
                      {
                        name: 'Sai hướng',
                        values: [
                          100 - (data.direction_accuracy.per_segment.by_regime.TREND_UP?.accuracy_pct ?? 0),
                          100 - (data.direction_accuracy.per_segment.by_regime.TREND_DOWN?.accuracy_pct ?? 0),
                        ],
                        color: '#ef4444',
                      },
                    ]}
                    height={230}
                    fmt={(v) => `${v.toFixed(1)}%`}
                  />
                </div>
              )}

              {data.wrong_direction?.failure_type &&
                data.wrong_direction.wrong_total > 0 && (
                  <div className={`${styles.grid} ${styles.cols2}`} style={{ marginTop: 14 }}>
                    <Stat
                      label="Đảo chiều sau khi đã đi đúng"
                      value={fmtNum(
                        data.wrong_direction.failure_type.reversed_after_favourable_move,
                        0
                      )}
                      sub="đúng nhưng hết hơi"
                      tone="warn"
                    />
                    <Stat
                      label="Sai ngay từ đầu"
                      value={fmtNum(data.wrong_direction.failure_type.never_moved_favourably, 0)}
                      sub="không hề đi đúng hướng"
                      tone="down"
                    />
                  </div>
                )}

              <div className={styles.muted} style={{ fontSize: 12, marginTop: 12 }}>
                Định nghĩa giống tab “Độ chính xác hướng” của cả năm: một đoạn chỉ
                được tính ĐÚNG khi giá đóng cuối đoạn nằm đúng phía so với lúc bắt
                đầu tín hiệu.
              </div>
            </Card>
          )}

          <Card
            title="Chi tiết từng nến"
            subtitle={`${data.bars.length} nến M15 — chế độ AI, chế độ tham chiếu và chỉ báo`}
          >
            <div className="table-wrap" style={{ maxHeight: 520, overflowY: 'auto' }}>
              <table className="table">
                <thead>
                  <tr>
                    <th>Thời gian (UTC)</th>
                    <th className="num">Mở</th>
                    <th className="num">Cao</th>
                    <th className="num">Thấp</th>
                    <th className="num">Đóng</th>
                    <th>Chế độ AI</th>
                    <th className="num">Tin cậy</th>
                    <th>Tham chiếu</th>
                    <th className="num">ADX</th>
                    <th className="num">ATR ratio</th>
                    <th className="num">ER</th>
                  </tr>
                </thead>
                <tbody>
                  {data.bars.map((b) => (
                    <tr key={b.ts}>
                      <td className="mono">{fmtUtc(b.ts)}</td>
                      <td className="num">{fmtPrice(b.open)}</td>
                      <td className="num">{fmtPrice(b.high)}</td>
                      <td className="num">{fmtPrice(b.low)}</td>
                      <td className="num">{fmtPrice(b.close)}</td>
                      <td>
                        <RegimeBadge regime={b.regime} />
                      </td>
                      <td className="num">{fmtNum(b.confidence * 100, 1)}%</td>
                      <td>
                        {b.reference_regime ? (
                          <RegimeBadge regime={b.reference_regime} />
                        ) : (
                          '—'
                        )}
                      </td>
                      <td className="num">{fmtNum(b.adx_norm, 3)}</td>
                      <td className="num">{fmtNum(b.atr_ratio, 2)}</td>
                      <td className="num">{fmtNum(b.efficiency_ratio, 2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>

          <div className={styles.muted} style={{ fontSize: 12 }}>
            {data.note} Muốn xem phân tích toàn bộ lịch sử hoặc bước qua từng nến, dùng{' '}
            <Link href="/history">Lịch sử Regime</Link> hoặc <Link href="/replay">Replay</Link>.
          </div>
        </>
      )}
    </div>
  );
}
