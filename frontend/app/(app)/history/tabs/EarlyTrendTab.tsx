'use client';

import dynamic from 'next/dynamic';
import { Card, ErrorState, Loading, Notice, Stat } from '@/components/ui/ui';
import { fmtNum } from '@/lib/format';
import { useApi } from '@/lib/swr';
import type { EarlyTrendStat, EarlyTrendStatsResponse } from '@/lib/types';
import styles from '../../pages.module.css';

const HBars = dynamic(() => import('@/components/charts/HistoryCharts').then((m) => m.HBars), {
  ssr: false,
  loading: () => <Loading label="Đang tải biểu đồ…" />,
});

function EarlyCard({ regime, stat }: { regime: string; stat: EarlyTrendStat }) {
  const confirmedPct = stat.signals > 0 ? (stat.confirmed / stat.signals) * 100 : 0;
  const wrongPct = stat.signals > 0 ? (stat.wrong_direction / stat.signals) * 100 : 0;
  return (
    <Card title={regime} subtitle={`Cửa sổ đánh giá: ${stat.window_bars} nến phía trước`}>
      <div className={`${styles.grid} ${styles.cols2}`}>
        <Stat label="Số tín hiệu" value={fmtNum(stat.signals, 0)} />
        <Stat
          label="Tỷ lệ thành công"
          value={`${fmtNum(stat.success_rate_pct, 1)}%`}
          tone={stat.success_rate_pct >= 50 ? 'up' : 'warn'}
        />
        <Stat
          label="Tỷ lệ sai hướng"
          value={`${fmtNum(stat.false_rate_pct, 1)}%`}
          tone={stat.false_rate_pct > 30 ? 'warn' : 'neutral'}
        />
        <Stat
          label="Độ trễ phát hiện TB"
          value={`${fmtNum(stat.mean_detection_delay_bars, 1)} nến`}
          sub={`sau khi tín hiệu xuất hiện`}
        />
        <Stat label="Đã xác nhận" value={`${fmtNum(stat.confirmed, 0)} (${fmtNum(confirmedPct, 1)}%)`} tone="up" />
        <Stat label="Sai hướng" value={`${fmtNum(stat.wrong_direction, 0)} (${fmtNum(wrongPct, 1)}%)`} tone="down" />
        <Stat label="Không có xu hướng" value={fmtNum(stat.no_trend, 0)} />
        <Stat label="Không đủ dữ liệu" value={fmtNum(stat.no_data, 0)} />
      </div>
    </Card>
  );
}

export default function EarlyTrendTab({ runId }: { runId: number }) {
  const { data, error, isLoading } = useApi<EarlyTrendStatsResponse>(
    `/history/runs/${runId}/stats/early_trend?window=12`
  );

  if (isLoading) return <Loading label="Đang tải đánh giá Early Trend…" />;
  if (error) return <ErrorState error={error} />;
  if (!data) return <ErrorState title="Không có dữ liệu" error="Không nhận được thống kê early trend." />;

  return (
    <div className={styles.stack}>
      <Notice tone="info">
        <strong>Phương pháp đánh giá (nhãn tham chiếu):</strong>{' '}
        {data.note ?? 'Nhãn tham chiếu được tính từ lợi nhuận thực tế phía trước.'}
        <br />
        <span style={{ fontSize: 12 }}>
          Tín hiệu EARLY_TREND_UP/DOWN được đối chiếu với biến động giá <em>đã xảy ra sau đó</em>{' '}
          ({data.EARLY_TREND_UP.window_bars} nến so với ngưỡng ATR). Phương pháp này chỉ dùng để{' '}
          <strong>đánh giá chất lượng</strong> tín hiệu — bản thân tín hiệu vẫn là causal (không
          nhìn tương lai). Tỷ lệ thành công ở đây không phải là dự báo lợi nhuận giao dịch.
        </span>
      </Notice>

      <div className={`${styles.grid} ${styles.cols2}`}>
        <EarlyCard regime="EARLY_TREND_UP" stat={data.EARLY_TREND_UP} />
        <EarlyCard regime="EARLY_TREND_DOWN" stat={data.EARLY_TREND_DOWN} />
      </div>

      <Card title="So sánh kết quả theo hướng" subtitle="Số tín hiệu được xác nhận vs sai hướng">
        <HBars
          data={[
            {
              label: 'UP · xác nhận',
              value: data.EARLY_TREND_UP.confirmed,
              color: '#22c55e',
            },
            { label: 'UP · sai hướng', value: data.EARLY_TREND_UP.wrong_direction, color: '#f59e0b' },
            {
              label: 'DOWN · xác nhận',
              value: data.EARLY_TREND_DOWN.confirmed,
              color: '#14b8a6',
            },
            { label: 'DOWN · sai hướng', value: data.EARLY_TREND_DOWN.wrong_direction, color: '#a855f7' },
          ]}
          fmt={(v) => fmtNum(v, 0)}
          height={300}
        />
        <div className={styles.muted} style={{ fontSize: 12, marginTop: 8 }}>
          Độ trễ phát hiện trung bình: UP {fmtNum(data.EARLY_TREND_UP.mean_detection_delay_bars, 1)}{' '}
          nến · DOWN {fmtNum(data.EARLY_TREND_DOWN.mean_detection_delay_bars, 1)} nến (số nến từ khi
          tín hiệu xuất hiện đến khi xu hướng thực sự xác nhận theo nhãn tham chiếu).
        </div>
      </Card>
    </div>
  );
}
