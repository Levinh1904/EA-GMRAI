'use client';

import { useMemo } from 'react';
import dynamic from 'next/dynamic';
import { Card, ErrorState, Loading, Notice, Stat } from '@/components/ui/ui';
import { fmtNum } from '@/lib/format';
import { regimeColor, regimeLabel } from '@/lib/regime';
import { useApi } from '@/lib/swr';
import type { SidewaysStatsResponse } from '@/lib/types';
import { fmtMin, fmtMinHours } from '../shared';
import styles from '../../pages.module.css';

const HBars = dynamic(() => import('@/components/charts/HistoryCharts').then((m) => m.HBars), {
  ssr: false,
  loading: () => <Loading label="Đang tải biểu đồ…" />,
});

const HPie = dynamic(() => import('@/components/charts/HistoryCharts').then((m) => m.HPie), {
  ssr: false,
  loading: () => <Loading label="Đang tải biểu đồ…" />,
});

const BUCKET_ORDER = ['<30m', '30m-1h', '1h-2h', '2h-4h', '4h-8h', '>8h'];

export default function SidewaysTab({ runId }: { runId: number }) {
  const { data, error, isLoading } = useApi<SidewaysStatsResponse>(
    `/history/runs/${runId}/stats/sideways`
  );

  const bucketRows = useMemo(
    () =>
      BUCKET_ORDER.map((b) => ({
        label: b,
        value: data?.buckets?.[b] ?? 0,
      })).filter((r) => r.value > 0 || (data != null && Object.keys(data.buckets ?? {}).length === 0)),
    [data]
  );

  const nextRows = useMemo(
    () =>
      Object.entries(data?.next_regime_distribution ?? {})
        .map(([k, v]) => ({ label: regimeLabel(k), value: v, color: regimeColor(k) }))
        .sort((a, b) => b.value - a.value),
    [data]
  );

  if (isLoading) return <Loading label="Đang tải phân tích Sideways…" />;
  if (error) return <ErrorState error={error} />;
  if (!data) return <ErrorState title="Không có dữ liệu" error="Không nhận được thống kê sideways." />;

  const totalBars = BUCKET_ORDER.reduce((acc, b) => acc + (data.buckets?.[b] ?? 0), 0);

  return (
    <div className={styles.stack}>
      {data.bucket_note && <Notice tone="info">{data.bucket_note}</Notice>}

      <div className={`${styles.grid} ${styles.cols4}`}>
        <Card title="Số segments đi ngang">
          <Stat label="Count" value={fmtNum(data.count, 0)} sub={`${fmtNum(data.total_minutes / 60, 1)} giờ tổng cộng`} />
        </Card>
        <Card title="Thời lượng">
          <Stat label="Trung bình" value={fmtMin(data.mean_minutes)} />
          <Stat label="Trung vị" value={fmtMin(data.median_minutes)} />
        </Card>
        <Card title="Cực trị thời lượng">
          <Stat label="Dài nhất" value={fmtMin(data.longest_minutes)} />
          <Stat label="Ngắn nhất" value={fmtMin(data.shortest_minutes)} />
        </Card>
        <Card title="Phá vỡ vùng (breakouts)">
          <Stat label="Breakouts" value={fmtNum(data.breakouts, 0)} tone="up" />
          <Stat label="False breakouts" value={fmtNum(data.false_breakouts, 0)} tone="warn" />
        </Card>
      </div>

      <div className={`${styles.grid} ${styles.cols3}`}>
        <Card title="Biên độ vùng giá">
          <Stat label="Độ rộng trung bình" value={`${fmtNum(data.mean_range_width, 2)} USD`} />
          <Stat label="Cận trên TB" value={fmtNum(data.mean_range_high, 2)} />
          <Stat label="Cận dưới TB" value={fmtNum(data.mean_range_low, 2)} />
        </Card>
        <Card title="Chất lượng đi ngang">
          <Stat label="ATR ratio TB" value={fmtNum(data.mean_atr_ratio, 3)} />
          <Stat label="ADX chuẩn hóa TB" value={fmtNum(data.mean_adx_norm, 3)} />
          <Stat label="Efficiency TB" value={fmtNum(data.mean_efficiency, 3)} />
        </Card>
        <Card title="Chạm biên">
          <Stat label="Chạm cận trên TB" value={fmtNum(data.mean_touches_high, 1)} sub="lần / segment" />
          <Stat label="Chạm cận dưới TB" value={fmtNum(data.mean_touches_low, 1)} sub="lần / segment" />
        </Card>
      </div>

      {data.false_breakout_rule && (
        <Notice tone="warn">
          <strong>Quy tắc false breakout:</strong> {data.false_breakout_rule}. Đã ghi nhận{' '}
          {fmtNum(data.false_breakouts, 0)} trường hợp trong số {fmtNum(data.breakouts, 0)} lần phá
          vỡ.
        </Notice>
      )}

      <div className={`${styles.grid} ${styles.cols2}`}>
        <Card
          title="Phân bố thời lượng (buckets)"
          subtitle={`Tổng ${fmtNum(totalBars, 0)} segments · bucket ngắn <30m, dài >8h`}
        >
          <HBars
            data={bucketRows.map((r) => ({
              label: r.label,
              value: r.value,
              color: '#8b98a9',
            }))}
            fmt={(v) => fmtNum(v, 0)}
            height={300}
          />
        </Card>
        <Card title="Regime tiếp theo sau Sideways" subtitle="Phân phối regime ngay sau mỗi segment đi ngang">
          <HPie
            data={nextRows}
            fmt={(v) => fmtNum(v, 0)}
            height={300}
          />
          <div className={styles.muted} style={{ fontSize: 12, marginTop: 6 }}>
            Ví dụ dài nhất: {fmtMinHours(data.longest_minutes)}. Các bucket được cấu hình qua query{' '}
            <code>?buckets</code>.
          </div>
        </Card>
      </div>
    </div>
  );
}
