'use client';

import { useMemo } from 'react';
import dynamic from 'next/dynamic';
import { Badge, Card, ErrorState, Loading, Notice, Stat } from '@/components/ui/ui';
import { fmtNum } from '@/lib/format';
import { regimeColor, regimeLabel } from '@/lib/regime';
import { useApi } from '@/lib/swr';
import type { TransitionsStatsResponse } from '@/lib/types';
import { fmtMin } from '../shared';
import styles from '../../pages.module.css';

const HHeatmap = dynamic(() => import('@/components/charts/HistoryCharts').then((m) => m.HHeatmap), {
  ssr: false,
  loading: () => <Loading label="Đang tải heatmap…" />,
});

export default function TransitionsTab({ runId }: { runId: number }) {
  const { data, error, isLoading } = useApi<TransitionsStatsResponse>(
    `/history/runs/${runId}/stats/transitions`
  );

  const regimes = useMemo(() => data?.regimes ?? [], [data]);

  const z = useMemo(
    () =>
      regimes.map((src) => regimes.map((dst) => data?.counts?.[src]?.[dst] ?? 0)),
    [data, regimes]
  );

  if (isLoading) return <Loading label="Đang tải ma trận chuyển trạng thái…" />;
  if (error) return <ErrorState error={error} />;
  if (!data) return <ErrorState title="Không có dữ liệu" error="Không nhận được thống kê transitions." />;

  return (
    <div className={styles.stack}>
      {data.note && (
        <Notice tone="info">
          <strong>Lưu ý:</strong> {data.note}
          <br />
          <span style={{ fontSize: 12 }}>
            Ma trận bên dưới đếm tần suất chuyển <em>regime vận hành</em> giữa các segment liền kề —
            khác với xác suất chuyển nội tại (intrinsic) của mô hình HMM (xem ma trận transmat trong
            artifact mô hình tại trang Kho mô hình).
          </span>
        </Notice>
      )}

      <div className={`${styles.grid} ${styles.cols3}`}>
        <Card title="Tổng số lần chuyển">
          <Stat label="Operational transitions" value={fmtNum(data.total_transitions, 0)} />
        </Card>
        <Card title="Thời lượng nguồn trung bình">
          <Stat
            label="TREND_UP"
            value={fmtMin(data.mean_source_duration_minutes?.TREND_UP)}
            tone="up"
          />
          <Stat
            label="TREND_DOWN"
            value={fmtMin(data.mean_source_duration_minutes?.TREND_DOWN)}
            tone="down"
          />
        </Card>
        <Card title="Thời lượng nguồn TB (tiếp)">
          <Stat label="SIDEWAYS" value={fmtMin(data.mean_source_duration_minutes?.SIDEWAYS)} />
          <Stat label="EARLY_TREND" value={fmtMin(data.mean_source_duration_minutes?.EARLY_TREND)} />
        </Card>
      </div>

      <Card title="Heatmap số lần chuyển" subtitle="Hàng = regime nguồn · Cột = regime đích">
        <HHeatmap
          xLabels={regimes.map((r) => regimeLabel(r))}
          yLabels={regimes.map((r) => regimeLabel(r))}
          z={z}
          zfmt={(v) => fmtNum(v, 0)}
          height={Math.max(300, regimes.length * 60 + 120)}
        />
      </Card>

      <Card title="Tỷ lệ chuyển theo nguồn" subtitle="Tổng mỗi hàng = 100% (làm tròn)">
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Nguồn → Đích</th>
                {regimes.map((r) => (
                  <th key={r} className="num">
                    <span style={{ color: regimeColor(r) }}>{regimeLabel(r)}</span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {regimes.map((src) => (
                <tr key={src}>
                  <td>
                    <Badge
                      tone="neutral"
                      style={{
                        color: regimeColor(src),
                        background: `${regimeColor(src)}1a`,
                        borderColor: `${regimeColor(src)}55`,
                      }}
                    >
                      {regimeLabel(src)}
                    </Badge>
                  </td>
                  {regimes.map((dst) => {
                    const rate = data.rates?.[src]?.[dst];
                    return (
                      <td key={dst} className="num">
                        {rate != null ? `${(rate * 100).toFixed(1)}%` : '—'}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className={styles.muted} style={{ fontSize: 12, marginTop: 8 }}>
          Đọc ví dụ: hàng SIDEWAYS, cột EARLY_TREND ={' '}
          {(() => {
            const v = data.rates?.SIDEWAYS?.EARLY_TREND;
            return v != null ? `${(v * 100).toFixed(1)}%` : '—';
          })()}{' '}
          — tức trong số các lần rời khỏi SIDEWAYS, tỷ lệ chuyển sang tín hiệu sớm là bao nhiêu.
        </div>
      </Card>
    </div>
  );
}
