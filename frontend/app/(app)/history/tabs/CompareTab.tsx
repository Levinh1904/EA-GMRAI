'use client';

import { useMemo, useState } from 'react';
import dynamic from 'next/dynamic';
import { Badge, Card, ErrorState, KV, Loading, Notice, Stat } from '@/components/ui/ui';
import { fmtNum } from '@/lib/format';
import { regimeColor, regimeLabel } from '@/lib/regime';
import { useApi } from '@/lib/swr';
import type { CompareVsReferenceResponse, CompareVsRunResponse, HistoryRun } from '@/lib/types';
import styles from '../../pages.module.css';
import hstyles from '../history.module.css';

const HHeatmap = dynamic(() => import('@/components/charts/HistoryCharts').then((m) => m.HHeatmap), {
  ssr: false,
  loading: () => <Loading label="Đang tải heatmap…" />,
});

function VsReference({ runId }: { runId: number }) {
  const { data, error, isLoading } = useApi<CompareVsReferenceResponse>(
    `/history/runs/${runId}/compare?vs_reference=true`
  );

  const z = useMemo(() => data?.classification?.confusion_matrix ?? [], [data]);
  const classes = useMemo(() => data?.classification?.classes ?? [], [data]);

  if (isLoading) return <Loading label="Đang so sánh với nhãn tham chiếu…" />;
  if (error) return <ErrorState error={error} />;
  if (!data) return <ErrorState title="Không có dữ liệu" error="Không nhận được kết quả so sánh." />;

  const cls = data.classification;
  const det = data.detection;

  return (
    <div className={styles.stack}>
      {data.reference_note && (
        <Notice tone="warn">
          <strong>Nhãn tham chiếu:</strong> {data.reference_note}
        </Notice>
      )}

      <div className={`${styles.grid} ${styles.cols4}`}>
        <Card title="Accuracy">
          <Stat label="Tổng thể" value={`${(cls.accuracy * 100).toFixed(1)}%`} tone={cls.accuracy >= 0.5 ? 'up' : 'warn'} />
        </Card>
        <Card title="Macro F1">
          <Stat label="Trung bình 3 lớp" value={fmtNum(cls.macro_f1, 4)} />
        </Card>
        <Card title="False trend rate">
          <Stat
            label="Tín hiệu xu hướng sai"
            value={`${(data.false_trend_rate * 100).toFixed(1)}%`}
            tone="warn"
          />
        </Card>
        <Card title="Phát hiện xu hướng">
          <Stat label="UP delay TB" value={`${fmtNum(det.trend_up.mean_delay_bars, 2)} nến`} />
          <Stat label="DOWN delay TB" value={`${fmtNum(det.trend_down.mean_delay_bars, 2)} nến`} />
        </Card>
      </div>

      <Card title="Precision / Recall / F1 theo lớp" subtitle="Nhãn tham chiếu = lợi nhuận thực tế phía trước (đánh giá, không phải ground truth)">
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Lớp</th>
                <th className="num">Precision</th>
                <th className="num">Recall</th>
                <th className="num">F1</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(cls.per_class ?? {}).map(([k, v]) => (
                <tr key={k}>
                  <td>
                    <Badge
                      tone="neutral"
                      style={{
                        color: regimeColor(k),
                        background: `${regimeColor(k)}1a`,
                        borderColor: `${regimeColor(k)}55`,
                      }}
                    >
                      {regimeLabel(k)}
                    </Badge>
                  </td>
                  <td className="num">{fmtNum(v.precision, 4)}</td>
                  <td className="num">{fmtNum(v.recall, 4)}</td>
                  <td className="num">{fmtNum(v.f1, 4)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className={styles.muted} style={{ fontSize: 12, marginTop: 8 }}>
          Recall thấp ở TREND_UP/TREND_DOWN là bình thường: nhãn tham chiếu đếm mọi cây nến có biến
          động mạnh phía trước, trong khi hệ thống chỉ gán nhãn xu hướng khi đủ tin cậy. Đây là đánh
          giá độ nhạy, không phải hiệu năng giao dịch.
        </div>
      </Card>

      <Card title="Confusion matrix" subtitle={`Hàng = nhãn tham chiếu · Cột = dự đoán hệ thống · ${classes.join(' / ')}`}>
        <HHeatmap
          xLabels={classes.map((c) => regimeLabel(c))}
          yLabels={classes.map((c) => regimeLabel(c))}
          z={z}
          zfmt={(v) => fmtNum(v, 0)}
          height={Math.max(300, classes.length * 70 + 120)}
        />
      </Card>

      <Card title="Độ trễ phát hiện xu hướng" subtitle="Cửa sổ tham chiếu theo hướng">
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Hướng</th>
                <th className="num">Số cửa sổ</th>
                <th className="num">Bỏ sót (missed)</th>
                <th className="num">Delay TB (nến)</th>
                <th className="num">Delay tối đa (nến)</th>
              </tr>
            </thead>
            <tbody>
              {(['trend_up', 'trend_down'] as const).map((k) => (
                <tr key={k}>
                  <td>{k === 'trend_up' ? 'TREND_UP' : 'TREND_DOWN'}</td>
                  <td className="num">{fmtNum(det[k].windows, 0)}</td>
                  <td className="num">{fmtNum(det[k].missed, 0)}</td>
                  <td className="num">{fmtNum(det[k].mean_delay_bars, 2)}</td>
                  <td className="num">{fmtNum(det[k].max_delay_bars, 0)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

function VsRun({ runId, runs }: { runId: number; runs: HistoryRun[] }) {
  const others = useMemo(() => runs.filter((r) => r.id !== runId), [runs, runId]);
  const [vsId, setVsId] = useState<number | null>(null);

  const { data, error, isLoading } = useApi<CompareVsRunResponse>(
    vsId != null ? `/history/runs/${runId}/compare?vs_run_id=${vsId}` : null
  );

  if (others.length === 0) {
    return (
      <Card title="So sánh run vs run">
        <Notice tone="info">
          Chỉ có một run duy nhất trong hệ thống — chưa thể so sánh giữa hai run. Chạy thêm một run
          phân tích (nút “Chạy phân tích mới” ở đầu trang) để mở khóa phần này.
        </Notice>
      </Card>
    );
  }

  const regimeKeys = useMemo(() => {
    const set = new Set<string>();
    for (const row of Object.values(data?.confusion_counts ?? {})) {
      for (const k of Object.keys(row)) set.add(k);
    }
    return [...set].sort();
  }, [data]);

  return (
    <div className={styles.stack}>
      <div className={styles.toolbar}>
        <label className={styles.small} style={{ color: 'var(--text-muted)' }}>
          So sánh với run:
        </label>
        <select
          className={hstyles.select}
          value={vsId ?? ''}
          onChange={(e) => setVsId(e.target.value ? Number(e.target.value) : null)}
        >
          <option value="">— chọn run —</option>
          {others.map((r) => (
            <option key={r.id} value={r.id}>
              run #{r.id} · {r.symbol} {r.timeframe} · {r.status}
            </option>
          ))}
        </select>
      </div>

      {vsId == null && <Notice tone="info">Chọn một run khác để xem tỷ lệ đồng thuận và ma trận nhầm lẫn.</Notice>}
      {isLoading && <Loading label="Đang so sánh hai run…" />}
      {error && <ErrorState error={error} />}
      {data && (
        <>
          <div className={`${styles.grid} ${styles.cols3}`}>
            <Card title="Độ đồng thuận">
              <Stat label="Agreement rate" value={`${(data.agreement_rate * 100).toFixed(1)}%`} />
              <Stat label="Nến chồng lấn" value={fmtNum(data.overlap_bars, 0)} />
            </Card>
            <Card title="Số segments mỗi run">
              <KV
                columns={1}
                items={data.names.map((n, i) => ({
                  label: n,
                  value: fmtNum(data.segment_counts?.[n], 0),
                })).filter((it, i) => i < 2)}
              />
            </Card>
            <Card title="Thời lượng theo regime (phút)">
              <KV
                columns={1}
                items={Object.entries(data.duration_minutes ?? {}).flatMap(([name, byRegime]) =>
                  Object.entries(byRegime).map(([r, v]) => ({ label: `${name} · ${regimeLabel(r)}`, value: fmtNum(v, 0) }))
                )}
              />
            </Card>
          </div>

          <Card title="Confusion counts (bar-level)" subtitle="Hàng = run A · Cột = run B (theo thứ tự names)">
            <HHeatmap
              xLabels={regimeKeys.map((r) => regimeLabel(r))}
              yLabels={regimeKeys.map((r) => regimeLabel(r))}
              z={regimeKeys.map((a) => regimeKeys.map((b) => data.confusion_counts?.[a]?.[b] ?? 0))}
              zfmt={(v) => fmtNum(v, 0)}
              height={Math.max(300, regimeKeys.length * 70 + 120)}
            />
            <div className={styles.muted} style={{ fontSize: 12, marginTop: 8 }}>
              Đồng thuận = tổng đường chéo / tổng nến chồng lấn. Hai run khác phiên bản mô hình sẽ có
              những vùng phân kỳ regime khác nhau.
            </div>
          </Card>
        </>
      )}
    </div>
  );
}

export default function CompareTab({ runId, runs }: { runId: number; runs: HistoryRun[] }) {
  return (
    <div className={styles.stack}>
      <Card
        title="So sánh với nhãn tham chiếu (reference labels)"
        subtitle="Đánh giá phân loại regime so với lợi nhuận thực tế phía trước"
      >
        <VsReference runId={runId} />
      </Card>
      <VsRun runId={runId} runs={runs} />
    </div>
  );
}
