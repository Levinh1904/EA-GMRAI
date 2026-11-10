'use client';

import { useState } from 'react';
import dynamic from 'next/dynamic';
import { Badge, Button, Card, ErrorState, Loading, Notice, RegimeBadge, Segmented } from '@/components/ui/ui';
import { api } from '@/lib/api';
import { fmtNum, fmtUtc } from '@/lib/format';
import { useApi } from '@/lib/swr';
import type { HistoryRun, PeriodsStatsResponse } from '@/lib/types';
import styles from '../../pages.module.css';

const PeriodsChart = dynamic(() => import('@/components/charts/HistoryCharts').then((m) => m.PeriodsChart), {
  ssr: false,
  loading: () => <Loading label="Đang tải biểu đồ giai đoạn…" />,
});

const PERIOD_OPTIONS = [
  { value: 'day', label: 'Ngày' },
  { value: 'week', label: 'Tuần' },
  { value: 'month', label: 'Tháng' },
  { value: 'quarter', label: 'Quý' },
  { value: 'year', label: 'Năm' },
];

const EXPORTS: Array<{
  key: string;
  label: string;
  format: string;
  scope: string;
  filename: (runId: number) => string;
  note?: string;
}> = [
  {
    key: 'csv-segments',
    label: 'CSV · Segments',
    format: 'csv',
    scope: 'segments',
    filename: (id) => `history_run_${id}_segments.csv`,
  },
  {
    key: 'csv-bars',
    label: 'CSV · Bars',
    format: 'csv',
    scope: 'bars',
    filename: (id) => `history_run_${id}_bars.csv`,
  },
  {
    key: 'xlsx-segments',
    label: 'XLSX · Segments',
    format: 'xlsx',
    scope: 'segments',
    filename: (id) => `history_run_${id}_segments.xlsx`,
  },
  {
    key: 'xlsx-bars',
    label: 'XLSX · Bars',
    format: 'xlsx',
    scope: 'bars',
    filename: (id) => `history_run_${id}_bars.xlsx`,
  },
  {
    key: 'pdf-report',
    label: 'PDF · Báo cáo tổng hợp',
    format: 'pdf',
    scope: 'report',
    filename: (id) => `history_run_${id}_report.pdf`,
  },
];

export default function ReportsTab({ run, runId }: { run: HistoryRun; runId: number }) {
  const [period, setPeriod] = useState('day');
  const [busy, setBusy] = useState<string | null>(null);
  const [dlError, setDlError] = useState<string | null>(null);

  const periods = useApi<PeriodsStatsResponse>(`/history/runs/${runId}/stats/periods?period=${period}`);

  async function handleExport(item: (typeof EXPORTS)[number]) {
    setBusy(item.key);
    setDlError(null);
    try {
      await api.exportHistory(runId, item.format, item.scope, item.filename(runId));
    } catch (e) {
      setDlError(e instanceof Error ? e.message : 'Tải xuống thất bại');
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className={styles.stack}>
      <Card
        title="Xuất dữ liệu"
        subtitle="Tải qua trình duyệt với Bearer token (fetch → blob → download). Định dạng do backend sinh ra."
      >
        <div className={styles.toolbar}>
          {EXPORTS.map((item) => (
            <Button key={item.key} onClick={() => handleExport(item)} disabled={busy != null}>
              {busy === item.key ? 'Đang tải…' : item.label}
            </Button>
          ))}
        </div>
        <div className={styles.muted} style={{ fontSize: 12 }}>
          CSV/XLSX xuất nội dung segments hoặc bars của run #{runId}. PDF là báo cáo tổng hợp phân
          tích (scope=report). Dữ liệu xuất dựa trên dữ liệu đã lưu của run — cố định tại thời điểm
          chạy.
        </div>
        {dlError && (
          <div style={{ marginTop: 10 }}>
            <Notice tone="danger">
              {dlError} — hãy thử định dạng khác (vd. XLSX bars có thể chưa được backend hỗ trợ, hãy
              dùng CSV bars thay thế).
            </Notice>
          </div>
        )}
      </Card>

      <Card
        title="Thống kê theo giai đoạn (stats/periods)"
        subtitle="Số phút mỗi regime + biên độ giá USD theo ngày/tuần/tháng/quý/năm"
        right={<Segmented options={PERIOD_OPTIONS} value={period} onChange={setPeriod} />}
      >
        {periods.isLoading && <Loading label="Đang tải thống kê giai đoạn…" />}
        {periods.error && (
          <ErrorState
            error={periods.error}
            title={`Không tải được thống kê period="${period}"`}
          />
        )}
        {periods.data && (
          <>
            <div className={styles.chartBox}>
              <PeriodsChart rows={periods.data.rows} height={380} />
            </div>
            <div className={styles.muted} style={{ fontSize: 12, marginTop: 8 }}>
              {fmtNum(periods.data.rows.length, 0)} giai đoạn ({periods.data.period}) · cột màu = số
              phút theo regime · đường vàng = biên độ USD trong kỳ.
            </div>
            <div className="table-wrap" style={{ marginTop: 10 }}>
              <table className="table">
                <thead>
                  <tr>
                    <th>Bắt đầu kỳ</th>
                    <th>Regime chiếm ưu thế</th>
                    <th className="num">Segments</th>
                    <th className="num">Tăng (phút)</th>
                    <th className="num">Giảm (phút)</th>
                    <th className="num">Đi ngang (phút)</th>
                    <th className="num">Sớm (phút)</th>
                    <th className="num">Chuyển tiếp</th>
                    <th className="num">Biến động cao</th>
                    <th className="num">Biên độ USD</th>
                  </tr>
                </thead>
                <tbody>
                  {periods.data.rows.slice(0, 60).map((row, i) => (
                    <tr key={`${row.period_start}-${i}`}>
                      <td className="mono">{fmtUtc(row.period_start)}</td>
                      <td>
                        {row.dominant_regime ? <RegimeBadge regime={row.dominant_regime} /> : '—'}
                      </td>
                      <td className="num">{fmtNum(row.segments, 0)}</td>
                      <td className="num">{fmtNum(row.trend_up_minutes, 0)}</td>
                      <td className="num">{fmtNum(row.trend_down_minutes, 0)}</td>
                      <td className="num">{fmtNum(row.sideways_minutes, 0)}</td>
                      <td className="num">{fmtNum(row.early_trend_minutes, 0)}</td>
                      <td className="num">{fmtNum(row.transition_minutes, 0)}</td>
                      <td className="num">{fmtNum(row.high_volatility_minutes, 0)}</td>
                      <td className="num">{fmtNum(row.range_usd, 2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {periods.data.rows.length > 60 && (
              <div className={styles.muted} style={{ fontSize: 12, marginTop: 6 }}>
                Hiển thị 60 giai đoạn đầu trong tổng số {fmtNum(periods.data.rows.length, 0)} — biểu
                đồ phía trên hiển thị toàn bộ.
              </div>
            )}
          </>
        )}
      </Card>

      <Card title="Thông tin dữ liệu & freshness">
        <div className={styles.toolbar}>
          <Badge tone="neutral">
            Kết thúc dữ liệu: <span className="mono">{fmtUtc(run.data_end)}</span>
          </Badge>
          <Badge tone={run.status === 'done' ? 'success' : 'info'}>Run #{run.id}: {run.status}</Badge>
          <Badge tone="neutral">
            <span className="mono">{run.symbol} · {run.timeframe}</span>
          </Badge>
        </div>
        <div className={styles.muted} style={{ fontSize: 12 }}>
          Toàn bộ phân tích lịch sử là ảnh chụp cố định của run #{runId} (nguồn{' '}
          <code>{run.data_source ?? '—'}</code>, {fmtNum(run.bar_count, 0)} nến,{' '}
          {fmtNum(run.segment_count, 0)} segments). Báo cáo và file xuất được sinh từ chính dữ liệu
          này.
        </div>
      </Card>
    </div>
  );
}
