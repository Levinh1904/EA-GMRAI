'use client';

// Direction accuracy — "when the model called a trend, did price actually go
// that way?" Two independent views, both from real stored data:
//
//   per segment : start of signal -> end of segment (the honest "did the call
//                 work" number; a short run that reverses counts as wrong)
//   per bar     : did the NEXT closed bar follow the direction
//
// Nothing is estimated client-side; all numbers come from
// GET /history/runs/{id}/stats/direction_accuracy.

import dynamic from 'next/dynamic';
import { useMemo } from 'react';
import { Badge, Card, EmptyState, ErrorState, Loading, Notice, Stat } from '@/components/ui/ui';
import { fmtNum } from '@/lib/format';
import { regimeLabel } from '@/lib/regime';
import { useApi } from '@/lib/swr';
import type {
  DirectionAccuracyResponse,
  HistoryRun,
  WrongDirectionResponse,
} from '@/lib/types';
import styles from '../../pages.module.css';

const HGroupedBars = dynamic(
  () => import('@/components/charts/HistoryCharts').then((m) => m.HGroupedBars),
  { ssr: false, loading: () => <Loading label="Đang tải biểu đồ…" /> }
);

function pctTone(pct: number | null | undefined): 'success' | 'warning' | 'danger' | 'neutral' {
  if (pct == null) return 'neutral';
  if (pct >= 60) return 'success';
  if (pct >= 45) return 'warning';
  return 'danger';
}

export default function DirectionAccuracyTab({ run }: { run: HistoryRun }) {
  const runId = run.id;
  const { data, error, isLoading, mutate } = useApi<DirectionAccuracyResponse>(
    `/history/runs/${runId}/stats/direction_accuracy`,
    { revalidateOnFocus: false, refreshInterval: 0 }
  );
  const wrong = useApi<WrongDirectionResponse>(
    `/history/runs/${runId}/stats/wrong_direction`,
    { revalidateOnFocus: false, refreshInterval: 0 }
  );

  // Two views of the same population: % correct vs % wrong per direction, plus
  // raw segment counts so a 100%/0% split on 3 samples cannot look meaningful.
  const chartLabels = useMemo(
    () => (['TREND_UP', 'TREND_DOWN'] as const).map((r) => regimeLabel(r)),
    []
  );
  const chartSeries = useMemo(() => {
    if (!data) return [];
    const pctCorrect = (['TREND_UP', 'TREND_DOWN'] as const).map(
      (r) => data.per_segment.by_regime[r]?.accuracy_pct ?? 0
    );
    const pctWrong = (['TREND_UP', 'TREND_DOWN'] as const).map(
      (r) => {
        const s = data.per_segment.by_regime[r];
        if (!s || !s.total) return 0;
        return 100 - (s.accuracy_pct ?? 0);
      }
    );
    return [
      { name: 'Đúng hướng', values: pctCorrect, color: '#22c55e' },
      { name: 'Sai hướng', values: pctWrong, color: '#ef4444' },
    ];
  }, [data]);

  const countLabels = useMemo(
    () => (['TREND_UP', 'TREND_DOWN'] as const).map((r) => regimeLabel(r)),
    []
  );
  const countSeries = useMemo(() => {
    if (!data) return [];
    return [
      {
        name: 'Đúng',
        values: (['TREND_UP', 'TREND_DOWN'] as const).map(
          (r) => data.per_segment.by_regime[r]?.correct ?? 0
        ),
        color: '#22c55e',
      },
      {
        name: 'Sai',
        values: (['TREND_UP', 'TREND_DOWN'] as const).map(
          (r) => data.per_segment.by_regime[r]?.wrong ?? 0
        ),
        color: '#ef4444',
      },
    ];
  }, [data]);

  if (isLoading) return <Loading label="Đang tính độ chính xác hướng…" />;
  if (error) return <ErrorState error={error} onRetry={() => void mutate()} />;
  if (!data) return <EmptyState title="Không có dữ liệu" />;

  const seg = data.per_segment.by_regime;
  const overall = data.per_segment.overall;
  const trade = data.per_segment_tradeable;
  const hasData = (seg.TREND_UP?.total ?? 0) + (seg.TREND_DOWN?.total ?? 0) > 0;

  return (
    <div className={styles.stack}>
      <Notice tone="info">
        <strong>Cách đo:</strong> {data.definition}{' '}
        Số liệu tổng hợp phía trên có tính cả <code>EARLY_TREND</code> (chỉ cảnh báo,
        <strong> NO_TRADE</strong>). Chỉ số <strong>tradeable</strong> bên dưới mới chỉ gồm
        <code> TREND_UP/TREND_DOWN</code> thực sự vào lệnh.
      </Notice>

      {trade && (
        <Notice tone="warn">
          <strong>Chỉ TREND tradeable (loại EARLY_TREND):</strong>{' '}
          Tăng {fmtNum(trade.by_regime.TREND_UP?.accuracy_pct, 1)}% (
          {fmtNum(trade.by_regime.TREND_UP?.correct, 0)}/
          {fmtNum(trade.by_regime.TREND_UP?.total, 0)}) · Giảm{' '}
          {fmtNum(trade.by_regime.TREND_DOWN?.accuracy_pct, 1)}% (
          {fmtNum(trade.by_regime.TREND_DOWN?.correct, 0)}/
          {fmtNum(trade.by_regime.TREND_DOWN?.total, 0)}) · Tổng thể{' '}
          <strong>{fmtNum(trade.overall.accuracy_pct, 1)}%</strong> (
          {fmtNum(trade.overall.correct, 0)}/{fmtNum(trade.overall.total, 0)} đoạn).
        </Notice>
      )}

      <div className={`${styles.grid} ${styles.cols4}`}>
        <Stat
          label="Tổng đoạn xu hướng"
          value={fmtNum(overall.total, 0)}
          sub={`${fmtNum(overall.correct, 0)} đúng hướng`}
        />
        <Stat
          label="Tăng đúng hướng"
          value={`${fmtNum(seg.TREND_UP?.accuracy_pct, 1)}%`}
          sub={`${fmtNum(seg.TREND_UP?.correct, 0)}/${fmtNum(seg.TREND_UP?.total, 0)} đoạn`}
          tone={(seg.TREND_UP?.accuracy_pct ?? 0) >= 50 ? 'up' : 'down'}
        />
        <Stat
          label="Giảm đúng hướng"
          value={`${fmtNum(seg.TREND_DOWN?.accuracy_pct, 1)}%`}
          sub={`${fmtNum(seg.TREND_DOWN?.correct, 0)}/${fmtNum(seg.TREND_DOWN?.total, 0)} đoạn`}
          tone={(seg.TREND_DOWN?.accuracy_pct ?? 0) >= 50 ? 'up' : 'down'}
        />
        <Stat
          label="Tổng thể"
          value={`${fmtNum(overall.accuracy_pct, 1)}%`}
          sub="cả hai hướng"
          tone={(overall.accuracy_pct ?? 0) >= 50 ? 'up' : 'down'}
        />
      </div>

      {!hasData && (
        <EmptyState
          title="Run này không có đoạn xu hướng nào"
          hint="Chọn run khác hoặc chạy phân tích mới."
        />
      )}

      {hasData && (
        <>
          {chartSeries.length > 0 && (
            <Card
              title="So sánh độ chính xác theo hướng"
              subtitle="% đoạn ĐÚNG hướng và % đoạn SAI hướng, trên cùng thang 100%"
            >
              <HGroupedBars
                labels={chartLabels}
                series={chartSeries}
                height={280}
                fmt={(v) => `${v.toFixed(1)}%`}
              />
              <div style={{ marginTop: 6, fontSize: 12, color: 'var(--text-tertiary)' }}>
                Hai cột cộng lại = 100%. Nhìn cặp cột để thấy ngay hướng nào đáng tin hơn.
              </div>
            </Card>
          )}

          {countSeries.length > 0 && (
            <Card
              title="Số lượng đoạn đúng / sai"
              subtitle="giá trị tuyệt đối — tránh hiểu nhầm khi mẫu quá nhỏ"
            >
              <HGroupedBars
                labels={countLabels}
                series={countSeries}
                height={260}
                fmt={(v) => String(Math.round(v))}
              />
            </Card>
          )}

          <Card title="Chi tiết theo hướng" subtitle="so sánh đoạn đúng và đoạn sai">
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Hướng</th>
                    <th className="num">Tổng đoạn</th>
                    <th className="num">Đúng</th>
                    <th className="num">Sai</th>
                    <th className="num">Chính xác</th>
                    <th className="num">Biên độ TB khi đúng</th>
                    <th className="num">Biên độ TB khi sai</th>
                    <th className="num">Nến TB khi đúng</th>
                    <th className="num">Nến TB khi sai</th>
                  </tr>
                </thead>
                <tbody>
                  {(['TREND_UP', 'TREND_DOWN'] as const).map((r) => {
                    const s = seg[r];
                    if (!s || s.total === 0) {
                      return (
                        <tr key={r}>
                          <td>{regimeLabel(r)}</td>
                          <td colSpan={8} className={styles.muted}>
                            không có đoạn nào
                          </td>
                        </tr>
                      );
                    }
                    return (
                      <tr key={r}>
                        <td>
                          <Badge tone={r === 'TREND_UP' ? 'success' : 'danger'}>
                            {regimeLabel(r)}
                          </Badge>
                        </td>
                        <td className="num">{fmtNum(s.total, 0)}</td>
                        <td className="num" style={{ color: 'var(--status-ok)' }}>
                          {fmtNum(s.correct, 0)}
                        </td>
                        <td className="num" style={{ color: 'var(--status-danger)' }}>
                          {fmtNum(s.wrong, 0)}
                        </td>
                        <td className="num">
                          <Badge tone={pctTone(s.accuracy_pct)}>
                            {fmtNum(s.accuracy_pct, 1)}%
                          </Badge>
                        </td>
                        <td className="num">{fmtNum(s.mean_move_pct_correct, 3)}%</td>
                        <td className="num">{fmtNum(s.mean_move_pct_wrong, 3)}%</td>
                        <td className="num">{fmtNum(s.mean_bars_correct, 1)}</td>
                        <td className="num">{fmtNum(s.mean_bars_wrong, 1)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </Card>

          {data.per_bar && (
            <Card
              title="Độ chính xác theo từng nến"
              subtitle={data.per_bar.note}
            >
              <div className="table-wrap">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Chế độ</th>
                      <th className="num">Số nến</th>
                      <th className="num">Đúng hướng nến kế tiếp</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(['TREND_UP', 'TREND_DOWN', 'SIDEWAYS'] as const).map((r) => {
                      const b = data.per_bar?.by_regime[r];
                      if (!b || !b.bars) return null;
                      return (
                        <tr key={r}>
                          <td>{regimeLabel(r)}</td>
                          <td className="num">{fmtNum(b.bars, 0)}</td>
                          <td className="num">
                            <Badge tone={pctTone(b.accuracy_pct)}>
                              {fmtNum(b.accuracy_pct, 1)}%
                            </Badge>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              <div className={styles.muted} style={{ fontSize: 12, marginTop: 10 }}>
                Con số này thấp hơn nhiều so với “theo đoạn” vì nó khắt khe hơn: một xu hướng
                kéo dài 20 nến vẫn có thể có nhiều nến đơn lẻ đi ngược trong lúc hồi. Dùng “theo
                đoạn” để đánh giá tín hiệu, dùng “theo nến” để thấy mức nhiễu bên trong.
              </div>
            </Card>
          )}

          {/* ---------------- WRONG direction deep-dive ---------------- */}
          {wrong.data && wrong.data.wrong_total > 0 && (
            <>
              <Card
                title="Thống kê SAI hướng — mức độ và nguyên nhân"
                subtitle={`${fmtNum(wrong.data.wrong_total, 0)}/${fmtNum(wrong.data.total, 0)} đoạn đi ngược tín hiệu (${fmtNum(wrong.data.wrong_pct, 1)}%)`}
                tone="warn"
              >
                <div className={`${styles.grid} ${styles.cols4}`}>
                  <Stat
                    label="Đi ngược trung bình"
                    value={`${fmtNum(wrong.data.loss?.mean_adverse_pct, 3)}%`}
                    sub={`trung vị ${fmtNum(wrong.data.loss?.median_adverse_pct, 3)}%`}
                    tone="down"
                  />
                  <Stat
                    label="Tệ nhất"
                    value={`${fmtNum(wrong.data.loss?.worst_adverse_pct, 3)}%`}
                    sub={`P90 ${fmtNum(wrong.data.loss?.p90_adverse_pct, 3)}%`}
                    tone="down"
                  />
                  <Stat
                    label="Lỗ TB / lệnh"
                    value={`$${fmtNum(wrong.data.loss?.mean_adverse_usd, 2)}`}
                    sub="1 lot, quy đổi"
                  />
                  <Stat
                    label="Tổng số đoạn"
                    value={fmtNum(wrong.data.total, 0)}
                    sub={`${fmtNum(wrong.data.total - wrong.data.wrong_total, 0)} đúng`}
                  />
                </div>

                {wrong.data.loss_distribution && (
                  <div style={{ marginTop: 14 }}>
                    <div className={styles.probTitle}>Phân bố mức đi ngược</div>
                    <div className="table-wrap">
                      <table className="table">
                        <thead>
                          <tr>
                            <th>Mức đi ngược</th>
                            <th className="num">Số đoạn</th>
                            <th className="num">Tỷ lệ trong số sai</th>
                          </tr>
                        </thead>
                        <tbody>
                          {Object.entries(wrong.data.loss_distribution).map(([k, v]) => (
                            <tr key={k}>
                              <td className="mono">{k}</td>
                              <td className="num">{fmtNum(v, 0)}</td>
                              <td className="num">
                                {fmtNum((100 * v) / Math.max(wrong.data!.wrong_total, 1), 1)}%
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </Card>

              {wrong.data.failure_type && (
                <Card title="Kiểu sai" subtitle={wrong.data.failure_type.note}>
                  <div className={`${styles.grid} ${styles.cols3}`}>
                    <Stat
                      label="Đảo chiều sau khi đã đi đúng"
                      value={fmtNum(wrong.data.failure_type.reversed_after_favourable_move, 0)}
                      sub={`${fmtNum(
                        (100 * wrong.data.failure_type.reversed_after_favourable_move) /
                          Math.max(wrong.data.wrong_total, 1),
                        1
                      )}% số lần sai — “đúng nhưng hết hơi”`}
                      tone="warn"
                    />
                    <Stat
                      label="Không hề đi đúng hướng"
                      value={fmtNum(wrong.data.failure_type.never_moved_favourably, 0)}
                      sub="tín hiệu sai ngay từ đầu"
                      tone="down"
                    />
                    <Stat
                      label="Đóng cửa không đổi"
                      value={fmtNum(wrong.data.failure_type.closed_flat, 0)}
                      sub="net change = 0"
                    />
                  </div>
                </Card>
              )}

              {wrong.data.by_length && (
                <Card
                  title="Sai theo độ dài đoạn"
                  subtitle="ngưỡng nến tối thiểu nên lọc — dưới ngưỡng này tín hiệu hay bị đảo"
                >
                  <div className="table-wrap">
                    <table className="table">
                      <thead>
                        <tr>
                          <th>Độ dài</th>
                          <th className="num">Tổng</th>
                          <th className="num">Sai</th>
                          <th className="num">Tỷ lệ sai</th>
                          <th className="num">Đi ngược TB</th>
                        </tr>
                      </thead>
                      <tbody>
                        {Object.entries(wrong.data.by_length).map(([k, v]) => (
                          <tr key={k}>
                            <td>{k}</td>
                            <td className="num">{fmtNum(v.total, 0)}</td>
                            <td className="num">{fmtNum(v.wrong, 0)}</td>
                            <td className="num">
                              <Badge
                                tone={
                                  v.wrong_pct <= 10
                                    ? 'success'
                                    : v.wrong_pct <= 30
                                      ? 'warning'
                                      : 'danger'
                                }
                              >
                                {fmtNum(v.wrong_pct, 1)}%
                              </Badge>
                            </td>
                            <td className="num">{fmtNum(v.mean_adverse_pct, 3)}%</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </Card>
              )}

              {wrong.data.profile && (
                <Card title="Hồ sơ đoạn đúng vs sai" subtitle="đâu là khác biệt hệ thống">
                  <div className="table-wrap">
                    <table className="table">
                      <thead>
                        <tr>
                          <th>Thuộc tính</th>
                          <th className="num">Khi ĐÚNG</th>
                          <th className="num">Khi SAI</th>
                          <th className="num">Chênh lệch</th>
                        </tr>
                      </thead>
                      <tbody>
                        {(
                          [
                            ['Số nến', 'bars', 1],
                            ['Thời lượng (phút)', 'duration_min', 1],
                            ['ADX', 'adx', 4],
                            ['ATR ratio', 'atr', 4],
                          ] as const
                        ).map(([label, key, digits]) => {
                          const row = wrong.data!.profile![key];
                          const diff = row.wrong_mean - row.correct_mean;
                          return (
                            <tr key={key}>
                              <td>{label}</td>
                              <td className="num">{fmtNum(row.correct_mean, digits)}</td>
                              <td className="num">{fmtNum(row.wrong_mean, digits)}</td>
                              <td
                                className="num"
                                style={{
                                  color:
                                    diff < 0 ? 'var(--status-danger)' : 'var(--status-ok)',
                                }}
                              >
                                {diff > 0 ? '+' : ''}
                                {fmtNum(diff, digits)}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </Card>
              )}

              {wrong.data.worst_hours && wrong.data.worst_hours.length > 0 && (
                <Card
                  title="Giờ tệ nhất (UTC)"
                  subtitle="khung giờ có tỷ lệ sai cao nhất — cân nhắc lọc theo phiên"
                >
                  <div className={`${styles.grid} ${styles.cols3}`}>
                    {wrong.data.worst_hours.map((h) => (
                      <Stat
                        key={h.hour}
                        label={h.hour}
                        value={`${fmtNum(h.wrong_pct, 1)}% sai`}
                        sub={`${fmtNum(h.samples, 0)} đoạn`}
                        tone="warn"
                      />
                    ))}
                  </div>
                </Card>
              )}

              {wrong.data.worst_calls && wrong.data.worst_calls.length > 0 && (
                <Card title="Các lần sai nặng nhất" subtitle="để soi lại trên biểu đồ">
                  <div className="table-wrap">
                    <table className="table">
                      <thead>
                        <tr>
                          <th>Tín hiệu</th>
                          <th className="num">Đi ngược</th>
                          <th className="num">Giá di chuyển</th>
                          <th className="num">Số nến</th>
                          <th className="num">ADX</th>
                        </tr>
                      </thead>
                      <tbody>
                        {wrong.data.worst_calls.map((c, i) => (
                          <tr key={i}>
                            <td>
                              <Badge tone={c.regime === 'TREND_UP' ? 'success' : 'danger'}>
                                {regimeLabel(c.regime)}
                              </Badge>
                            </td>
                            <td className="num" style={{ color: 'var(--status-danger)' }}>
                              {fmtNum(c.adverse_pct, 3)}%
                            </td>
                            <td className="num">{fmtNum(c.move_pct, 3)}%</td>
                            <td className="num">{fmtNum(c.bars, 0)}</td>
                            <td className="num">{fmtNum(c.adx, 3)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </Card>
              )}
            </>
          )}
        </>
      )}

      <div className={styles.muted} style={{ fontSize: 12 }}>
        Run #{runId} · nguồn {run.data_source ?? '—'} · {fmtNum(run.bar_count, 0)} nến ·{' '}
        độ chính xác đo trên chính các đoạn đã lưu trong CSDL, không phải số ước lượng.
      </div>
    </div>
  );
}
