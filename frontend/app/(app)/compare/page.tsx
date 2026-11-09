'use client';

import dynamic from 'next/dynamic';
import { useMemo } from 'react';
import {
  Badge,
  Card,
  EmptyState,
  ErrorState,
  Loading,
  PageHeader,
  ProbRow,
  StatusPill,
} from '@/components/ui/ui';
import { fmtNum, fmtUtcSec, variantName } from '@/lib/format';
import { useApi } from '@/lib/swr';
import type {
  BacktestListResponse,
  BacktestRun,
  ModelListResponse,
  ModelRow,
  TrainingRunListResponse,
  VariantComparison,
} from '@/lib/types';
import styles from '../pages.module.css';

const VariantCompareChart = dynamic(() => import('@/components/charts/VariantCompareChart'), {
  ssr: false,
  loading: () => <Loading label="Đang tải biểu đồ so sánh…" />,
});

const VARIANTS = ['hmm_only', 'rf_only', 'combined'] as const;

function f1Of(v: VariantComparison | undefined): string {
  const m = v?.macro_f1;
  return m ? `${fmtNum(m.mean, 3)} ± ${fmtNum(m.std, 3)}` : '—';
}

function ftrOf(v: VariantComparison | undefined): string {
  const m = v?.false_trend_rate;
  return m ? `${fmtNum(m.mean, 3)} ± ${fmtNum(m.std, 3)}` : '—';
}

function modelF1(row: ModelRow): number | null {
  const m = row.metrics;
  if (typeof m?.test_macro_f1 === 'number') return m.test_macro_f1;
  const combined = m?.variant_results?.combined;
  if (typeof combined?.test_macro_f1 === 'number') return combined.test_macro_f1;
  const hmm = m?.variant_results?.hmm_only;
  if (typeof hmm?.test_macro_f1 === 'number') return hmm.test_macro_f1;
  return null;
}

export default function ComparePage() {
  const backtests = useApi<BacktestListResponse>('/backtests?limit=20');
  const training = useApi<TrainingRunListResponse>('/training/runs?limit=20');
  const models = useApi<ModelListResponse>('/models?limit=100');

  const doneBacktests = useMemo<BacktestRun[]>(
    () =>
      (backtests.data?.runs ?? []).filter(
        (r) => r.status === 'done' && r.metrics?.variant_comparison
      ),
    [backtests.data]
  );

  const chartRows = useMemo(() => {
    const vc = doneBacktests[0]?.metrics?.variant_comparison;
    if (!vc) return [];
    return Object.entries(vc).map(([variant, v]) => ({
      variant,
      f1Mean: v.macro_f1?.mean ?? 0,
      f1Std: v.macro_f1?.std ?? 0,
      ftrMean: v.false_trend_rate?.mean ?? 0,
      ftrStd: v.false_trend_rate?.std ?? 0,
    }));
  }, [doneBacktests]);

  const trainRows = useMemo(
    () =>
      (training.data?.runs ?? []).filter(
        (r) => r.metrics?.variant_results && Object.keys(r.metrics.variant_results).length > 0
      ),
    [training.data]
  );

  const modelRows = useMemo(
    () =>
      (models.data?.models ?? [])
        .map((row) => ({ row, f1: modelF1(row) }))
        .filter((x): x is { row: ModelRow; f1: number } => x.f1 != null),
    [models.data]
  );

  return (
    <div className={styles.stack}>
      <PageHeader
        title="So sánh mô hình"
        subtitle="HMM-only vs RF-only vs HMM+RF (combined) — từ backtest walk-forward và huấn luyện"
      />

      <Card
        title="So sánh biến thể — Backtest walk-forward"
        subtitle={
          doneBacktests[0]
            ? `Backtest #${doneBacktests[0].id} «${doneBacktests[0].name}» · ${doneBacktests[0].metrics?.n_folds ?? '—'} folds`
            : 'chưa có backtest hoàn tất'
        }
      >
        {backtests.isLoading && <Loading />}
        {backtests.error && <ErrorState error={backtests.error} />}
        {!backtests.isLoading && chartRows.length === 0 && (
          <EmptyState
            title="Chưa có dữ liệu so sánh"
            hint="Chạy backtest hoàn tất để có variant_comparison"
          />
        )}
        {chartRows.length > 0 && (
          <>
            <div className={styles.chartBox}>
              <VariantCompareChart rows={chartRows} height={360} />
            </div>
            <div className={styles.muted} style={{ marginTop: 8, fontSize: 12 }}>
              False trend rate càng thấp càng tốt (tỷ lệ báo xu hướng sai); Macro F1 càng cao càng
              tốt. Thanh lỗi = ±1 std qua các fold.
            </div>
          </>
        )}
      </Card>

      <Card title="Tất cả backtest đã hoàn tất">
        {doneBacktests.length === 0 && !backtests.isLoading && (
          <EmptyState hint="Chưa có backtest done" />
        )}
        {doneBacktests.length > 0 && (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Tên</th>
                  <th className="num">Folds</th>
                  <th>Chosen</th>
                  <th className="num">HMM-only F1</th>
                  <th className="num">RF-only F1</th>
                  <th className="num">Combined F1</th>
                  <th className="num">Combined FTR</th>
                  <th>Kết thúc (UTC)</th>
                </tr>
              </thead>
              <tbody>
                {doneBacktests.map((r) => {
                  const vc = r.metrics?.variant_comparison ?? {};
                  return (
                    <tr key={r.id}>
                      <td className="mono">{r.id}</td>
                      <td className="mono">{r.name}</td>
                      <td className="num">{r.metrics?.n_folds ?? '—'}</td>
                      <td>
                        {r.metrics?.chosen_variant ? (
                          <Badge tone="teal">{variantName(r.metrics.chosen_variant)}</Badge>
                        ) : (
                          '—'
                        )}
                      </td>
                      <td className="num">{f1Of(vc.hmm_only)}</td>
                      <td className="num">{f1Of(vc.rf_only)}</td>
                      <td className="num">{f1Of(vc.combined)}</td>
                      <td className="num">{ftrOf(vc.combined)}</td>
                      <td className="mono">{fmtUtcSec(r.finished_at)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card title="Variant results theo lượt huấn luyện">
        {training.isLoading && <Loading />}
        {training.error && <ErrorState error={training.error} />}
        {trainRows.length === 0 && !training.isLoading && (
          <EmptyState hint="Chưa có lượt huấn luyện có variant_results" />
        )}
        {trainRows.length > 0 && (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Run #</th>
                  <th>Trạng thái</th>
                  <th>Chosen</th>
                  {VARIANTS.map((v) => (
                    <th key={v} className="num">
                      F1 {variantName(v)}
                    </th>
                  ))}
                  <th className="num">Accuracy (chosen)</th>
                  <th className="num">FTR (chosen)</th>
                </tr>
              </thead>
              <tbody>
                {trainRows.map((r) => {
                  const vr = r.metrics?.variant_results ?? {};
                  const chosen = r.metrics?.chosen_variant;
                  return (
                    <tr key={r.id}>
                      <td className="mono">{r.id}</td>
                      <td>
                        <StatusPill status={r.status} />
                      </td>
                      <td>{chosen ? <Badge tone="teal">{variantName(chosen)}</Badge> : '—'}</td>
                      {VARIANTS.map((v) => (
                        <td key={v} className="num">
                          {vr[v]?.test_macro_f1 != null ? fmtNum(vr[v].test_macro_f1, 4) : '—'}
                        </td>
                      ))}
                      <td className="num">
                        {chosen && vr[chosen]?.test_accuracy != null
                          ? fmtNum(vr[chosen].test_accuracy, 4)
                          : '—'}
                      </td>
                      <td className="num">
                        {chosen && vr[chosen]?.false_trend_rate != null
                          ? fmtNum(vr[chosen].false_trend_rate, 4)
                          : '—'}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card title="F1 theo phiên bản mô hình (Model Registry)">
        {models.isLoading && <Loading />}
        {models.error && <ErrorState error={models.error} />}
        {modelRows.length === 0 && !models.isLoading && (
          <EmptyState hint="Chưa có phiên bản mô hình có chỉ số F1" />
        )}
        {modelRows.length > 0 && (
          <div>
            {modelRows.map(({ row, f1 }) => (
              <ProbRow
                key={row.version_id}
                label={`${row.model_type} v${row.version} (#${row.version_id})`}
                value={f1}
                color={row.model_type === 'hmm' ? '#14b8a6' : '#a855f7'}
                digits={2}
              />
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
