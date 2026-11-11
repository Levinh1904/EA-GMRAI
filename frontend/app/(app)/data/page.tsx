'use client';

import { useState } from 'react';
import { useAuth } from '@/components/AuthProvider';
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorState,
  FreshnessPill,
  JsonBlock,
  Loading,
  Notice,
  PageHeader,
  Stat,
  StatusPill,
} from '@/components/ui/ui';
import { ApiError, api } from '@/lib/api';
import { fmtNum, fmtUtc, fmtUtcSec } from '@/lib/format';
import { useApi } from '@/lib/swr';
import type {
  DashboardStats,
  IngestStatusResponse,
  QualityReportResponse,
  QualityRunResponse,
  Timeframe,
} from '@/lib/types';
import styles from '../pages.module.css';

const TIMEFRAMES: Timeframe[] = ['M5', 'M15', 'H1'];

export default function DataPage() {
  const { isAdmin } = useAuth();
  const [running, setRunning] = useState(false);
  const [qualityResult, setQualityResult] = useState<QualityRunResponse | null>(null);
  const [qualityError, setQualityError] = useState<string | null>(null);

  const dashboard = useApi<DashboardStats>('/stats/dashboard', { refreshInterval: 15000 });
  const syncs = useApi<IngestStatusResponse>('/ingest/status?limit=20', { refreshInterval: 10000 });
  const reports = useApi<QualityReportResponse>('/quality/reports?limit=20', {
    refreshInterval: 60000,
  });

  async function runQualityCheck() {
    if (running) return;
    setRunning(true);
    setQualityResult(null);
    setQualityError(null);
    try {
      const res = await api.runQuality();
      setQualityResult(res);
      await Promise.all([reports.mutate(), dashboard.mutate()]);
    } catch (e) {
      setQualityError(e instanceof ApiError ? e.message : 'Chạy kiểm tra chất lượng thất bại');
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className={styles.stack}>
      <PageHeader
        title="Trung tâm dữ liệu"
        subtitle="Số lượng nến, độ tươi dữ liệu, lịch sử đồng bộ và báo cáo chất lượng"
      />

      {qualityResult && (
        <Notice tone="info">
          Kiểm tra chất lượng hoàn tất (status: {qualityResult.status}).
        </Notice>
      )}
      {qualityError && <Notice tone="danger">{qualityError}</Notice>}

      <div className={`${styles.grid} ${styles.cols3}`}>
        {TIMEFRAMES.map((tf) => {
          const st = dashboard.data?.candles[tf];
          const f = dashboard.data?.data_freshness[tf];
          return (
            <Card key={tf} title={`Nến ${tf}`}>
              {dashboard.isLoading && <Loading />}
              {dashboard.data && (
                <>
                  <Stat
                    label="Số lượng"
                    value={fmtNum(st?.count ?? 0, 0)}
                    sub={st?.latest_ts ? `mới nhất ${fmtUtc(st.latest_ts)}` : '—'}
                  />
                  <div style={{ marginTop: 10 }}>
                    <FreshnessPill
                      ageMinutes={f?.age_minutes}
                      stale={f?.stale}
                      thresholdMinutes={f?.threshold_minutes}
                    />
                  </div>
                </>
              )}
            </Card>
          );
        })}
      </div>

      <Card
        title="Kiểm tra chất lượng dữ liệu"
        subtitle="POST /quality/run — quét missing/duplicate/gap/bad candle cho cả 3 timeframe"
      >
        <div className={styles.formActions}>
          <Button variant="primary" onClick={runQualityCheck} disabled={!isAdmin || running}>
            {running ? 'Đang chạy kiểm tra…' : 'Chạy kiểm tra chất lượng (admin)'}
          </Button>
          {!isAdmin && (
            <Notice tone="warn">Cần quyền <strong>admin</strong> để chạy kiểm tra chất lượng.</Notice>
          )}
        </div>
        {qualityResult && (
          <div style={{ marginTop: 12 }}>
            <div className={styles.probTitle}>Kết quả</div>
            <JsonBlock data={qualityResult.results} maxHeight={300} />
          </div>
        )}
      </Card>

      <Card title="Lịch sử đồng bộ dữ liệu" subtitle="/ingest/status — các lần sync gần nhất">
        {syncs.isLoading && <Loading />}
        {syncs.error && <ErrorState error={syncs.error} />}
        {syncs.data && syncs.data.recent_syncs.length === 0 && (
          <EmptyState title="Chưa có log đồng bộ" />
        )}
        {syncs.data && syncs.data.recent_syncs.length > 0 && (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Collector</th>
                  <th>TF</th>
                  <th>Hoàn tất (UTC)</th>
                  <th>Trạng thái</th>
                  <th className="num">Nhận</th>
                  <th className="num">Thêm mới</th>
                  <th className="num">Cập nhật</th>
                  <th>Ghi chú</th>
                </tr>
              </thead>
              <tbody>
                {syncs.data.recent_syncs.map((s) => (
                  <tr key={s.id}>
                    <td className="mono">{s.id}</td>
                    <td className="mono">{s.collector_id}</td>
                    <td>{s.timeframe}</td>
                    <td className="mono">{fmtUtc(s.finished_at)}</td>
                    <td>
                      <StatusPill status={s.status} />
                    </td>
                    <td className="num">{fmtNum(s.received ?? s.inserted, 0)}</td>
                    <td className="num">{fmtNum(s.inserted, 0)}</td>
                    <td className="num">{fmtNum(s.updated, 0)}</td>
                    <td className="mono" style={{ whiteSpace: 'normal', fontSize: 12 }}>
                      {s.message ?? '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card title="Báo cáo chất lượng dữ liệu" subtitle="/quality/reports — kiểm tra định kỳ">
        {reports.isLoading && <Loading />}
        {reports.error && <ErrorState error={reports.error} />}
        {reports.data && reports.data.reports.length === 0 && (
          <EmptyState title="Chưa có báo cáo chất lượng" hint="Chạy kiểm tra chất lượng để tạo báo cáo" />
        )}
        {reports.data && reports.data.reports.length > 0 && (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>TF</th>
                  <th>Kiểm tra lúc (UTC)</th>
                  <th className="num">Tổng nến</th>
                  <th className="num">Thiếu</th>
                  <th className="num">Trùng</th>
                  <th className="num">Gap</th>
                  <th className="num">Nến lỗi</th>
                  <th>Nến mới nhất (UTC)</th>
                  <th>Trạng thái</th>
                </tr>
              </thead>
              <tbody>
                {reports.data.reports.map((q) => (
                  <tr key={q.id}>
                    <td className="mono">{q.id}</td>
                    <td>{q.timeframe}</td>
                    <td className="mono">{fmtUtcSec(q.checked_at)}</td>
                    <td className="num">{fmtNum(q.total_candles, 0)}</td>
                    <td className="num">{q.missing_count}</td>
                    <td className="num">{q.duplicate_count}</td>
                    <td className="num">{q.gap_count}</td>
                    <td className="num">{q.bad_candle_count}</td>
                    <td className="mono">{fmtUtc(q.stale_ts)}</td>
                    <td>{q.stale ? <Badge tone="danger">Cũ</Badge> : <Badge tone="success">OK</Badge>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
