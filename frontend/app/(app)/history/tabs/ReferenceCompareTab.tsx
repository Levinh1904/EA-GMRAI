'use client';

import { useMemo } from 'react';
import dynamic from 'next/dynamic';
import { Badge, Card, ErrorState, JsonBlock, Loading, Notice, Stat } from '@/components/ui/ui';
import { fmtNum, fmtPct } from '@/lib/format';
import { regimeColor, regimeLabel } from '@/lib/regime';
import { useApi } from '@/lib/swr';
import type { DurationDisagreement, VsReferenceStats } from '@/lib/types';
import styles from '../../pages.module.css';

const HHeatmap = dynamic(() => import('@/components/charts/HistoryCharts').then((m) => m.HHeatmap), {
  ssr: false,
  loading: () => <Loading label="Đang tải heatmap…" />,
});

const HBars = dynamic(() => import('@/components/charts/HistoryCharts').then((m) => m.HBars), {
  ssr: false,
  loading: () => <Loading label="Đang tải biểu đồ…" />,
});

function nn(v: number | null | undefined, digits = 4): string {
  return v == null || Number.isNaN(v) ? '—' : fmtNum(v, digits);
}

function durMean(v: number | DurationDisagreement | undefined): number | null {
  if (v == null) return null;
  if (typeof v === 'number') return v;
  return v.mean_abs_diff_minutes ?? null;
}

function durIntervals(v: number | DurationDisagreement | undefined): number | null {
  if (v == null) return null;
  if (typeof v === 'number') return null;
  return v.n_intervals ?? null;
}

export default function ReferenceCompareTab({ runId }: { runId: number }) {
  const { data, error, isLoading } = useApi<VsReferenceStats>(`/history/runs/${runId}/stats/vs_reference`);

  const classes = useMemo(() => data?.classes ?? [], [data]);

  const matrix = useMemo(() => {
    const counts = data?.confusion_counts ?? {};
    return classes.map((rowCls) => classes.map((colCls) => counts[rowCls]?.[colCls] ?? 0));
  }, [data, classes]);

  if (isLoading) return <Loading label="Đang tải báo cáo so sánh Reference…" />;
  if (error) return <ErrorState error={error} />;
  if (!data) return <ErrorState title="Không có dữ liệu" error="Không nhận được kết quả stats/vs_reference." />;

  const b = data.boundaries;
  const det = data.detection;

  const durEntries = Object.entries(data.duration_disagreement_minutes ?? {})
    .map(([regime, v]) => ({ regime, mean: durMean(v), n: durIntervals(v) }))
    .filter((e) => e.mean != null)
    .sort((a, z) => (z.mean ?? 0) - (a.mean ?? 0));

  return (
    <div className={styles.stack}>
      {data.note && (
        <Notice tone="warn">
          <strong>Lưu ý quan trọng:</strong> {data.note}
        </Notice>
      )}

      <div className={`${styles.grid} ${styles.cols4}`}>
        <Card title="Tỷ lệ đồng thuận">
          <Stat
            label="Agreement rate"
            value={fmtPct(data.agreement_rate, 1)}
            tone={data.agreement_rate >= 0.5 ? 'up' : 'warn'}
            sub={`${fmtNum(data.overlap_bars, 0)} nến chồng lấn`}
          />
        </Card>
        <Card title="Macro F1">
          <Stat label="Trung bình các lớp" value={nn(data.macro_f1)} sub="Thỏa thuận AI–Reference, không phải độ chính xác" />
        </Card>
        <Card title="Tỷ lệ xu hướng sai">
          <Stat label="False trend rate" value={fmtPct(data.false_trend_rate, 1)} tone="warn" />
          <Stat label="False sideways rate" value={fmtPct(data.false_sideways_rate, 1)} tone="warn" />
          <Stat label="Missed sideways rate" value={fmtPct(data.missed_sideways_rate, 1)} />
        </Card>
        <Card title="Biên regime (boundaries)">
          <Stat label="Khớp (matched)" value={fmtNum(b.matched, 0)} />
          <Stat label="Bỏ sót (missed)" value={fmtNum(b.missed, 0)} tone="warn" />
          <Stat label="Dư (extra)" value={fmtNum(b.extra, 0)} />
        </Card>
      </div>

      <Card
        title="Confusion matrix (AI vs Reference)"
        subtitle={`Hàng = Reference · Cột = AI · dung sai biên ±${b.tolerance_bars} nến · AI: ${fmtNum(b.ai_boundaries, 0)} biên · Reference: ${fmtNum(b.reference_boundaries, 0)} biên · khoảng cách TB ${nn(b.mean_abs_distance_bars, 2)} nến`}
      >
        <HHeatmap
          xLabels={classes.map((c) => regimeLabel(c))}
          yLabels={classes.map((c) => regimeLabel(c))}
          z={matrix}
          zfmt={(v) => fmtNum(v, 0)}
          height={Math.max(300, classes.length * 70 + 120)}
        />
        <div className={styles.muted} style={{ fontSize: 12, marginTop: 8 }}>
          Đây là ma trận <b>đồng thuận</b> giữa AI và bộ phân loại quy tắc Reference — không phải ma
          trận nhầm lẫn so với ground truth. Ô chéo lớn chỉ mức đồng thuận cao giữa hai hệ thống.
        </div>
      </Card>

      <Card
        title="Precision / Recall / F1 theo lớp (so với Reference)"
        subtitle={data.reference_version ? `Reference ${data.reference_version} — support = số nến Reference gán nhãn lớp đó` : undefined}
      >
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Lớp</th>
                <th className="num">Precision</th>
                <th className="num">Recall</th>
                <th className="num">F1</th>
                <th className="num">Support (nến)</th>
              </tr>
            </thead>
            <tbody>
              {classes.map((k) => {
                const v = data.per_class[k];
                if (!v) return null;
                return (
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
                    <td className="num">{nn(v.precision)}</td>
                    <td className="num">{nn(v.recall)}</td>
                    <td className="num">{nn(v.f1)}</td>
                    <td className="num">{fmtNum(v.support, 0)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <div className={styles.muted} style={{ fontSize: 12, marginTop: 8 }}>
          Các chỉ số trên đo <b>mức độ thỏa thuận</b> với bộ phân loại quy tắc Reference (ngưỡng
          nghiên cứu) — đây không phải độ chính xác dự đoán và Reference không phải ground truth.
        </div>
      </Card>

      <Card title="Độ trễ phát hiện xu hướng" subtitle="Cửa sổ tham chiếu theo hướng (reference tạo cửa sổ, AI đối chiếu)">
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
                  <td>
                    <Badge
                      tone="neutral"
                      style={{
                        color: regimeColor(k === 'trend_up' ? 'TREND_UP' : 'TREND_DOWN'),
                        background: `${regimeColor(k === 'trend_up' ? 'TREND_UP' : 'TREND_DOWN')}1a`,
                        borderColor: `${regimeColor(k === 'trend_up' ? 'TREND_UP' : 'TREND_DOWN')}55`,
                      }}
                    >
                      {k === 'trend_up' ? 'TREND_UP' : 'TREND_DOWN'}
                    </Badge>
                  </td>
                  <td className="num">{fmtNum(det[k].windows, 0)}</td>
                  <td className="num">{fmtNum(det[k].missed, 0)}</td>
                  <td className="num">{nn(det[k].mean_delay_bars, 2)}</td>
                  <td className="num">{nn(det[k].max_delay_bars, 0)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <Card
        title="Chênh lệch thời lượng regime (phút)"
        subtitle="Trung bình |thời lượng AI − thời lượng Reference| trên các khoảng liên tục cùng regime"
      >
        {durEntries.length === 0 ? (
          <div className={styles.muted} style={{ fontSize: 13 }}>
            Không có dữ liệu chênh lệch thời lượng.
          </div>
        ) : (
          <HBars
            horizontal
            height={Math.max(260, durEntries.length * 44 + 80)}
            fmt={(v) => fmtNum(v, 1)}
            data={durEntries.map((e) => ({
              label: e.n != null ? `${regimeLabel(e.regime)} (${e.n} khoảng)` : regimeLabel(e.regime),
              value: e.mean ?? 0,
              color: regimeColor(e.regime),
            }))}
          />
        )}
      </Card>

      <details style={{ marginTop: 4 }}>
        <summary
          style={{
            cursor: 'pointer',
            fontSize: 13,
            color: 'var(--text-muted)',
            padding: '8px 0',
            userSelect: 'none',
          }}
        >
          Cấu hình Reference {data.reference_version ?? '—'} (ngưỡng quy tắc)
        </summary>
        <JsonBlock
          maxHeight={420}
          data={{
            reference_version: data.reference_version,
            reference_config: data.reference_config,
          }}
        />
      </details>
    </div>
  );
}
