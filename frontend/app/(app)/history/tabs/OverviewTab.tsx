'use client';

import { useMemo } from 'react';
import dynamic from 'next/dynamic';
import { Badge, Card, EmptyState, ErrorState, KV, Loading, Notice, Stat, StatusPill } from '@/components/ui/ui';
import { fmtDuration, fmtNum, fmtUtc } from '@/lib/format';
import { useApi } from '@/lib/swr';
import type { DurationStatsResponse, HistoryRun, HistoryRunDetail } from '@/lib/types';
import { REGIME_ORDER, fmtMin, fmtPerDay } from '../shared';
import styles from '../../pages.module.css';

const HBars = dynamic(() => import('@/components/charts/HistoryCharts').then((m) => m.HBars), {
  ssr: false,
  loading: () => <Loading label="Đang tải biểu đồ…" />,
});

export default function OverviewTab({ run, runId }: { run: HistoryRun; runId: number }) {
  const detail = useApi<HistoryRunDetail>(`/history/runs/${runId}`, {
    refreshInterval: run.status === 'running' || run.status === 'pending' ? 4000 : 0,
  });
  const duration = useApi<DurationStatsResponse>(`/history/runs/${runId}/stats/duration`);

  const dataEndMinutesAgo = useMemo(() => {
    const end = detail.data?.data_end;
    if (!end) return null;
    const ms = Date.now() - new Date(end).getTime();
    if (Number.isNaN(ms)) return null;
    return Math.max(0, Math.round(ms / 60000));
  }, [detail.data]);

  const durationRows = useMemo(() => {
    const regimes = duration.data?.regimes ?? {};
    const seen = new Set<string>();
    const rows: Array<{ key: string; stat: DurationStatsResponse['regimes'][string] }> = [];
    for (const def of REGIME_ORDER) {
      if (regimes[def.key] && regimes[def.key].occurrences > 0) {
        rows.push({ key: def.key, stat: regimes[def.key] });
        seen.add(def.key);
      }
    }
    for (const [k, v] of Object.entries(regimes)) {
      if (!seen.has(k) && v && v.occurrences > 0) rows.push({ key: k, stat: v });
    }
    return rows;
  }, [duration.data]);

  if (detail.isLoading && !detail.data) return <Loading label="Đang tải thông tin run…" />;
  if (detail.error && !detail.data) return <ErrorState error={detail.error} />;

  const d = detail.data;

  return (
    <div className={styles.stack}>
      {run.status === 'running' || run.status === 'pending' ? (
        <Notice tone="warn">
          Run #{run.id} đang được xử lý — số liệu bên dưới sẽ được cập nhật tự động mỗi 4 giây.
        </Notice>
      ) : null}

      {dataEndMinutesAgo != null && (
        <Notice tone="info">
          Dữ liệu mới nhất của run kết thúc lúc <code>{fmtUtc(detail.data?.data_end)}</code> — cách
          hiện tại <code>{fmtNum(dataEndMinutesAgo, 0)} phút</code> (≈{' '}
          {fmtNum(dataEndMinutesAgo / 60 / 24, 1)} ngày). Phân tích là ảnh chụp lịch sử tại thời
          điểm chạy, không cập nhật theo thời gian thực.
        </Notice>
      )}

      <Card title="Thông tin run" subtitle={`Run #${runId} · ${run.symbol} · ${run.timeframe}`}>
        {detail.isLoading && !d && <Loading />}
        {d && (
          <KV
            columns={2}
            items={[
              { label: 'Trạng thái', value: <StatusPill status={d.status} /> },
              { label: 'Nguồn dữ liệu', value: d.data_source ?? '—' },
              { label: 'Bắt đầu dữ liệu (UTC)', value: fmtUtc(d.data_start) },
              { label: 'Kết thúc dữ liệu (UTC)', value: fmtUtc(d.data_end) },
              { label: 'Số nến (bars)', value: fmtNum(d.bar_count, 0) },
              { label: 'Số segments', value: fmtNum(d.segment_count, 0) },
              { label: 'HMM model version', value: d.hmm_model_version_id ?? '—' },
              { label: 'RF model version', value: d.rf_model_version_id ?? '—' },
              { label: 'Feature version', value: d.feature_version ?? '—' },
              { label: 'Tạo lúc', value: fmtUtc(d.created_at) },
              { label: 'Hoàn tất lúc', value: fmtUtc(d.finished_at) },
              { label: 'Thời lượng xử lý', value: fmtDuration(d.created_at, d.finished_at) },
              ...(d.config
                ? Object.entries(d.config).map(([k, v]) => ({
                    label: `config.${k}`,
                    value: typeof v === 'number' ? fmtNum(v, 3) : String(v ?? '—'),
                  }))
                : []),
            ]}
          />
        )}
        {d?.error && <Notice tone="danger">{d.error}</Notice>}
      </Card>

      <Card title="Thống kê thời lượng theo regime (top-line)" subtitle="Tổng hợp từ toàn bộ segments của run">
        {duration.isLoading && <Loading />}
        {duration.error && <ErrorState error={duration.error} />}
        {duration.data && durationRows.length === 0 && (
          <EmptyState title="Chưa có thống kê thời lượng" hint="Run này có thể chưa có segments." />
        )}
        {durationRows.length > 0 && (
          <>
            <div className={`${styles.grid} ${styles.cols3}`}>
              {durationRows.map(({ key, stat }) => (
                <Card key={key} title={key}>
                  <div className={styles.grid} style={{ gap: 10 }}>
                    <div className={styles.grid} style={{ gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                      <Stat label="Số lần xuất hiện" value={fmtNum(stat.occurrences, 0)} />
                      <Stat
                        label="Tỷ trọng thời gian"
                        value={stat.occupancy_pct != null ? `${fmtNum(stat.occupancy_pct, 2)}%` : '—'}
                      />
                      <Stat label="Tổng thời lượng" value={fmtNum(stat.total_minutes / 60, 1)} sub={`${fmtNum(stat.total_minutes, 0)} phút`} />
                      <Stat label="TB mỗi ngày" value={fmtPerDay(stat.avg_per_day)} />
                    </div>
                    <KV
                      items={[
                        { label: 'Trung bình', value: fmtMin(stat.mean_minutes) },
                        { label: 'Trung vị', value: fmtMin(stat.median_minutes) },
                        { label: 'Dài nhất', value: fmtMin(stat.longest_minutes) },
                        { label: 'Ngắn nhất', value: fmtMin(stat.shortest_minutes) },
                        { label: 'p25', value: fmtMin(stat.p25) },
                        { label: 'p75', value: fmtMin(stat.p75) },
                        { label: 'p90', value: fmtMin(stat.p90) },
                      ]}
                    />
                  </div>
                </Card>
              ))}
            </div>
            <div style={{ marginTop: 12 }}>
              <HBars
                title="Tỷ trọng thời gian theo regime (%)"
                data={durationRows.map(({ key, stat }) => ({
                  label: key,
                  value: stat.occupancy_pct ?? 0,
                }))}
                fmt={(v) => `${v.toFixed(2)}%`}
                height={280}
              />
            </div>
            <div className={styles.toolbar} style={{ marginTop: 12, marginBottom: 0 }}>
              <Badge tone="info">Tổng số lần chuyển regime: {fmtNum(duration.data?.total_transitions, 0)}</Badge>
              <span className={styles.muted}>
                Regime vận hành: TREND_UP, TREND_DOWN, SIDEWAYS, EARLY_TREND (gộp EARLY_TREND_UP/DOWN), TRANSITION,
                HIGH_VOLATILITY, UNKNOWN — regimes không xuất hiện trong dữ liệu có giá trị null.
              </span>
            </div>
          </>
        )}
      </Card>
    </div>
  );
}
