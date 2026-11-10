'use client';

import { useMemo } from 'react';
import dynamic from 'next/dynamic';
import { Card, ErrorState, KV, Loading, Notice, RegimeBadge } from '@/components/ui/ui';
import { fmtNum, fmtUtc } from '@/lib/format';
import { agreementColor, agreementLabel, TF_SIGNAL_COLORS } from '@/lib/regime';
import { useApi } from '@/lib/swr';
import type { MultiTfStatsResponse } from '@/lib/types';
import { fmtMin } from '../shared';
import styles from '../../pages.module.css';
import hstyles from '../history.module.css';

const HBars = dynamic(() => import('@/components/charts/HistoryCharts').then((m) => m.HBars), {
  ssr: false,
  loading: () => <Loading label="Đang tải biểu đồ…" />,
});

const AGREEMENT_ORDER = [
  'CONSENSUS_UP',
  'CONSENSUS_DOWN',
  'CONFLICT_M5',
  'CONFLICT_H1',
  'CONFLICT_BOTH',
  'NEUTRAL',
];

function tfChip(value: string) {
  const cls =
    value === 'UP'
      ? hstyles.signalUp
      : value === 'DOWN'
        ? hstyles.signalDown
        : value === 'SIDEWAYS'
          ? hstyles.signalSide
          : hstyles.signalNo;
  return (
    <span className={`${hstyles.chip} ${cls}`} style={{ borderColor: `${TF_SIGNAL_COLORS[value] ?? '#4b5563'}55`, color: TF_SIGNAL_COLORS[value] ?? 'var(--text-faint)' }}>
      {value}
    </span>
  );
}

export default function MultiTfTab({ runId }: { runId: number }) {
  const { data, error, isLoading } = useApi<MultiTfStatsResponse>(
    `/history/runs/${runId}/stats/multi_tf`
  );

  const countRows = useMemo(
    () =>
      AGREEMENT_ORDER.filter((k) => (data?.counts?.[k] ?? 0) > 0).map((k) => ({
        key: k,
        label: agreementLabel(k),
        value: data?.counts?.[k] ?? 0,
        color: agreementColor(k),
      })),
    [data]
  );

  if (isLoading) return <Loading label="Đang tải phân tích đa khung thời gian…" />;
  if (error) return <ErrorState error={error} />;
  if (!data) return <ErrorState title="Không có dữ liệu" error="Không nhận được thống kê multi-TF." />;

  return (
    <div className={styles.stack}>
      <Notice tone="warn">
        {data.note ??
          'Các cột M5/H1 là tín hiệu dựa trên FEATURE (đặc trưng giá), không phải regime AI.'}{' '}
        Ngưỡng phân loại: H1 trend context {fmtNum(data.thresholds?.h1_trend_context, 3)}, M5
        momentum {fmtNum(data.thresholds?.m5_momentum, 3)}.
      </Notice>

      <div className={`${styles.grid} ${styles.cols2}`}>
        <Card
          title="Số nến theo trạng thái đồng thuận"
          subtitle="CONSENSUS = M15 regime cùng hướng tín hiệu timing · CONFLICT = trái hướng · NEUTRAL = không đủ tín hiệu"
        >
          <HBars
            data={countRows.map((r) => ({ label: r.label, value: r.value, color: r.color }))}
            fmt={(v) => fmtNum(v, 0)}
            height={300}
          />
        </Card>
        <Card title="Tỷ trọng thời gian (%) & thời lượng trung bình">
          <HBars
            data={countRows.map((r) => ({
              label: r.label,
              value: data.occupancy_pct?.[r.key] ?? 0,
              color: r.color,
            }))}
            fmt={(v) => `${v.toFixed(2)}%`}
            height={220}
          />
          <KV
            columns={2}
            items={countRows.map((r) => ({
              label: `TB ${r.label}`,
              value: fmtMin(data.mean_duration_minutes?.[r.key]),
            }))}
          />
        </Card>
      </div>

      <Card
        title="Mẫu 200 nến gần nhất"
        subtitle="M15 regime (AI) + M5 timing & H1 context (tín hiệu feature-based) + trạng thái đồng thuận"
      >
        <div className={hstyles.scrollBox} style={{ maxHeight: 420, overflowY: 'auto' }}>
          <table className={`table ${hstyles.stickyHead}`}>
            <thead>
              <tr>
                <th>Thời gian (UTC)</th>
                <th>M15 regime</th>
                <th>M5 timing</th>
                <th>H1 context</th>
                <th>Đồng thuận</th>
              </tr>
            </thead>
            <tbody>
              {data.sample.map((row, i) => (
                <tr key={`${row.ts}-${i}`}>
                  <td className="mono">{fmtUtc(row.ts)}</td>
                  <td>
                    <RegimeBadge regime={row.m15_regime} />
                  </td>
                  <td>{tfChip(row.m5_timing)}</td>
                  <td>{tfChip(row.h1_context)}</td>
                  <td>
                    <span
                      className={hstyles.chip}
                      style={{
                        color: agreementColor(row.agreement),
                        background: `${agreementColor(row.agreement)}1a`,
                        borderColor: `${agreementColor(row.agreement)}55`,
                      }}
                    >
                      {agreementLabel(row.agreement)}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className={styles.muted} style={{ fontSize: 12, marginTop: 8 }}>
          M5 timing là hướng momentum M5 hiện tại (UP/DOWN/SIDEWAYS/NODATA), H1 context là hướng xu
          hướng H1 — cả hai đều là tín hiệu từ đặc trưng giá, được so sánh với regime M15 để suy ra
          CONSENSUS/CONFLICT.
        </div>
      </Card>
    </div>
  );
}
