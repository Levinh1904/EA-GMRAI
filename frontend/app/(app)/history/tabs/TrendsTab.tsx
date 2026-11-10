'use client';

import { useMemo } from 'react';
import dynamic from 'next/dynamic';
import { Card, ErrorState, Loading, Notice, Stat } from '@/components/ui/ui';
import { fmtNum } from '@/lib/format';
import { useApi } from '@/lib/swr';
import type { TrendStat, TrendsStatsResponse } from '@/lib/types';
import { fmtMin, signedUsd } from '../shared';
import styles from '../../pages.module.css';

const HBars = dynamic(() => import('@/components/charts/HistoryCharts').then((m) => m.HBars), {
  ssr: false,
  loading: () => <Loading label="Đang tải biểu đồ…" />,
});

const STRENGTH_LABELS: Record<string, string> = {
  strong: 'Mạnh',
  medium: 'Trung bình',
  weak: 'Yếu',
};

const STRENGTH_COLORS: Record<string, string> = {
  strong: '#22c55e',
  medium: '#f59e0b',
  weak: '#ef4444',
};

function TrendCard({ regime, stat }: { regime: string; stat: TrendStat }) {
  return (
    <Card title={regime} subtitle={`${fmtNum(stat.count, 0)} segments xu hướng`}>
      <div className={`${styles.grid} ${styles.cols2}`}>
        <Stat label="Tổng thời lượng" value={fmtNum(stat.total_minutes / 60, 1)} sub={`${fmtNum(stat.total_minutes, 0)} phút`} />
        <Stat label="Thời lượng trung bình" value={fmtMin(stat.mean_minutes)} />
        <Stat label="Trung vị" value={fmtMin(stat.median_minutes)} />
        <Stat label="Dài nhất" value={fmtMin(stat.longest_minutes)} />
        <Stat label="Ngắn nhất" value={fmtMin(stat.shortest_minutes)} />
        <Stat label="Tốc độ trung bình" value={fmtNum(stat.mean_speed_usd_per_min, 3)} sub="USD / phút" />
        <Stat
          label="Thay đổi ròng TB"
          value={signedUsd(stat.mean_net_change)}
          tone={stat.mean_net_change >= 0 ? 'up' : 'down'}
        />
        <Stat label="MFE trung bình" value={signedUsd(stat.mean_mfe)} tone="up" />
        <Stat label="MAE trung bình" value={signedUsd(stat.mean_mae)} tone="down" />
        <Stat label="ATR ratio TB" value={fmtNum(stat.mean_atr_ratio, 3)} />
        <Stat label="ADX chuẩn hóa TB" value={fmtNum(stat.mean_adx_norm, 3)} />
        <Stat label="Efficiency TB" value={fmtNum(stat.mean_efficiency, 3)} />
        <Stat label="Số nến TB" value={fmtNum(stat.mean_bar_count, 1)} />
      </div>
    </Card>
  );
}

export default function TrendsTab({ runId }: { runId: number }) {
  const { data, error, isLoading } = useApi<TrendsStatsResponse>(`/history/runs/${runId}/stats/trends`);

  const strengthRows = useMemo(() => {
    const dist = data?.strength?.distribution ?? {};
    const rows = Object.entries(dist)
      .map(([key, count]) => {
        const [regime, strength] = key.split('|');
        return { regime, strength, count };
      })
      .sort((a, b) => a.regime.localeCompare(b.regime) || b.count - a.count);
    return rows;
  }, [data]);

  const totalStrength = strengthRows.reduce((acc, r) => acc + r.count, 0);

  if (isLoading) return <Loading label="Đang tải phân tích xu hướng…" />;
  if (error) return <ErrorState error={error} />;
  if (!data) return <ErrorState title="Không có dữ liệu" error="Không nhận được thống kê trends." />;

  return (
    <div className={styles.stack}>
      {data.strength_note && (
        <Notice tone="info">
          <strong>Phương pháp phân cấp cường độ ({data.method}):</strong> {data.strength_note}
        </Notice>
      )}

      <div className={`${styles.grid} ${styles.cols2}`}>
        <TrendCard regime="TREND_UP" stat={data.TREND_UP} />
        <TrendCard regime="TREND_DOWN" stat={data.TREND_DOWN} />
      </div>

      <Card
        title="Phân bố cường độ xu hướng"
        subtitle={
          data.strength.score_formula
            ? `Công thức điểm: ${data.strength.score_formula} · ngưỡng phân vị q25=${fmtNum(data.strength.q25, 4)}, q75=${fmtNum(data.strength.q75, 4)}`
            : undefined
        }
      >
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Regime</th>
                <th>Cấp độ</th>
                <th className="num">Số segments</th>
                <th className="num">Tỷ trọng</th>
              </tr>
            </thead>
            <tbody>
              {strengthRows.map((r) => (
                <tr key={`${r.regime}|${r.strength}`}>
                  <td>{r.regime}</td>
                  <td>
                    <span
                      className="chip"
                      style={{
                        color: STRENGTH_COLORS[r.strength] ?? 'var(--gray)',
                        background: 'var(--bg-elev)',
                        border: `1px solid ${STRENGTH_COLORS[r.strength] ?? 'var(--border)'}`,
                        borderRadius: 999,
                        padding: '1px 8px',
                      }}
                    >
                      {STRENGTH_LABELS[r.strength] ?? r.strength}
                    </span>
                  </td>
                  <td className="num">{fmtNum(r.count, 0)}</td>
                  <td className="num">
                    {totalStrength > 0 ? `${((r.count / totalStrength) * 100).toFixed(1)}%` : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div style={{ marginTop: 12 }}>
          <HBars
            title="Số segments theo cấp độ cường độ"
            data={strengthRows.map((r) => ({
              label: `${r.regime} · ${STRENGTH_LABELS[r.strength] ?? r.strength}`,
              value: r.count,
              color: STRENGTH_COLORS[r.strength],
            }))}
            fmt={(v) => fmtNum(v, 0)}
            height={280}
          />
        </div>
        <div className={styles.muted} style={{ fontSize: 12, marginTop: 8 }}>
          Cường độ được phân loại theo phân vị của quần thể segment xu hướng (điểm = 0.5 ×
          efficiency + 0.5 × ADX): strong ≥ p75, weak ≤ p25, còn lại là medium.
        </div>
      </Card>
    </div>
  );
}
