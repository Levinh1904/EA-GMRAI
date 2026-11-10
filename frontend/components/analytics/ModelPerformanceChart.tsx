'use client';

// Model performance over time: per-run macro F1 / false trend rate across
// history runs (vs reference labels), training runs (chosen variant) and
// walk-forward backtests (variant comparison). Every point comes from a real
// API response — nothing is invented.

import { useCallback, useEffect, useMemo, useState } from 'react';
import { Card, EmptyState, Loading, Segmented } from '@/components/ui/ui';
import { useApi } from '@/lib/swr';
import Plot from '@/components/charts/Plotly';
import type {
  BacktestRun,
  CompareVsReferenceResponse,
  HistoryRun,
  TrainingRun,
} from '@/lib/types';
import { variantName } from '@/lib/format';
import styles from './analytics.module.css';

export interface PerfPoint {
  x: number; // ms
  f1: number | null;
  ftr: number | null;
  label: string;
  kind: 'history' | 'training' | 'backtest';
}

const KIND_COLORS: Record<PerfPoint['kind'], string> = {
  history: '#4c8dff',
  training: '#14b8a6',
  backtest: '#a855f7',
};

const KIND_LABELS: Record<PerfPoint['kind'], string> = {
  history: 'History run (vs Reference)',
  training: 'Training run (chosen variant)',
  backtest: 'Backtest walk-forward',
};

type Metric = 'f1' | 'ftr';
type TypeFilter = 'all' | PerfPoint['kind'];

/** Fetches one history run's vs-reference metrics and reports the point. */
function HistoryRunPoint({
  run,
  onPoint,
}: {
  run: HistoryRun;
  onPoint: (p: PerfPoint | null) => void;
}) {
  const { data } = useApi<CompareVsReferenceResponse>(
    run.status === 'done' ? `/history/runs/${run.id}/compare?vs_reference=true` : null,
    { revalidateOnFocus: false, refreshInterval: 0 }
  );
  useEffect(() => {
    if (!data) return;
    const x = new Date(run.data_end ?? run.finished_at ?? run.created_at).getTime();
    if (Number.isNaN(x)) return;
    onPoint({
      x,
      f1: data.classification?.macro_f1 ?? null,
      ftr: data.false_trend_rate ?? null,
      label: `History run #${run.id} (${run.bar_count ?? '—'} bars)`,
      kind: 'history',
    });
  }, [data, run, onPoint]);
  return null;
}

export function ModelPerformanceChart({
  historyRuns,
  trainingRuns,
  backtests,
}: {
  historyRuns: HistoryRun[];
  trainingRuns: TrainingRun[];
  backtests: BacktestRun[];
}) {
  const [metric, setMetric] = useState<Metric>('f1');
  const [typeFilter, setTypeFilter] = useState<TypeFilter>('all');
  const [points, setPoints] = useState<Record<string, PerfPoint>>({});

  const upsertPoint = useCallback((key: string, p: PerfPoint | null) => {
    setPoints((prev) => {
      const existing = prev[key];
      if (!existing && !p) return prev;
      if (
        existing &&
        p &&
        existing.x === p.x &&
        existing.f1 === p.f1 &&
        existing.ftr === p.ftr &&
        existing.label === p.label
      ) {
        return prev;
      }
      const next = { ...prev };
      if (p) next[key] = p;
      else delete next[key];
      return next;
    });
  }, []);

  // Backtest points (from variant_comparison — one point per variant).
  const backtestPoints = useMemo<Array<{ key: string; p: PerfPoint }>>(() => {
    const out: Array<{ key: string; p: PerfPoint }> = [];
    for (const bt of backtests) {
      if (bt.status !== 'done') continue;
      const vc = bt.metrics?.variant_comparison;
      const x = new Date(bt.finished_at ?? bt.started_at ?? '').getTime();
      if (!vc || Number.isNaN(x)) continue;
      for (const [variant, v] of Object.entries(vc)) {
        const mf1 = v.macro_f1?.mean ?? null;
        const ftr = v.false_trend_rate?.mean ?? null;
        if (mf1 == null && ftr == null) continue;
        out.push({
          key: `bt-${bt.id}-${variant}`,
          p: {
            x,
            f1: mf1,
            ftr,
            label: `Backtest #${bt.id} «${bt.name}» · ${variantName(variant)}`,
            kind: 'backtest',
          },
        });
      }
    }
    return out;
  }, [backtests]);

  // Training points (chosen variant test metrics).
  const trainingPoints = useMemo<Array<{ key: string; p: PerfPoint }>>(() => {
    const out: Array<{ key: string; p: PerfPoint }> = [];
    for (const tr of trainingRuns) {
      if (tr.status !== 'done') continue;
      const x = new Date(tr.finished_at ?? tr.started_at ?? '').getTime();
      if (Number.isNaN(x)) continue;
      const chosen = tr.metrics?.chosen_variant;
      const vr = chosen ? tr.metrics?.variant_results?.[chosen] : undefined;
      const mf1 = typeof vr?.test_macro_f1 === 'number' ? vr.test_macro_f1 : null;
      const ftr = typeof vr?.false_trend_rate === 'number' ? vr.false_trend_rate : null;
      if (mf1 == null && ftr == null) continue;
      out.push({
        key: `tr-${tr.id}`,
        p: {
          x,
          f1: mf1,
          ftr,
          label: `Training run #${tr.id} · ${chosen ? variantName(chosen) : tr.model_type}`,
          kind: 'training',
        },
      });
    }
    return out;
  }, [trainingRuns]);

  const allPoints = useMemo(() => {
    const map = new Map<string, PerfPoint>();
    for (const [k, v] of Object.entries(points)) map.set(k, v);
    for (const { key, p } of backtestPoints) map.set(key, p);
    for (const { key, p } of trainingPoints) map.set(key, p);
    return [...map.values()].sort((a, b) => a.x - b.x);
  }, [points, backtestPoints, trainingPoints]);

  const visible = useMemo(
    () => (typeFilter === 'all' ? allPoints : allPoints.filter((p) => p.kind === typeFilter)),
    [allPoints, typeFilter]
  );

  const kindsPresent = useMemo(() => {
    const set = new Set<PerfPoint['kind']>();
    for (const p of allPoints) set.add(p.kind);
    return set;
  }, [allPoints]);

  const traces = useMemo(() => {
    const out: Array<Record<string, unknown>> = [];
    for (const kind of ['history', 'training', 'backtest'] as const) {
      const pts = visible.filter((p) => p.kind === kind);
      if (pts.length === 0) continue;
      const y = pts.map((p) => (metric === 'f1' ? p.f1 : p.ftr));
      out.push({
        type: 'scatter',
        mode: 'lines+markers',
        name: KIND_LABELS[kind],
        x: pts.map((p) => new Date(p.x)),
        y,
        text: pts.map(
          (p) =>
            `${p.label}<br>${metric === 'f1' ? 'Macro F1' : 'False trend rate'}: ${
              (metric === 'f1' ? p.f1 : p.ftr) != null
                ? ((metric === 'f1' ? p.f1 : p.ftr) as number).toFixed(4)
                : '—'
            }`
        ),
        hoverinfo: 'text',
        marker: { color: KIND_COLORS[kind], size: 9 },
        line: { width: 1.6, shape: 'hv' },
      });
    }
    return out;
  }, [visible, metric]);

  const layout = useMemo<Record<string, unknown>>(
    () => ({
      paper_bgcolor: 'rgba(0,0,0,0)',
      plot_bgcolor: '#0d1117',
      font: { color: '#93a0b3', size: 11.5 },
      margin: { l: 8, r: 8, t: 8, b: 8 },
      showlegend: true,
      legend: { orientation: 'h', y: 1.12, x: 0, font: { size: 11 } },
      hovermode: 'closest',
      xaxis: {
        gridcolor: '#1a212c',
        title: { text: 'Thời điểm (UTC)', font: { size: 11 } },
      },
      yaxis: {
        gridcolor: '#1a212c',
        range: metric === 'ftr' ? [0, 1] : [0, 1],
        tickformat: '.0%',
      },
    }),
    [metric]
  );

  const config = useMemo(() => ({ responsive: true, displaylogo: false }), []);

  return (
    <Card
      title="Hiệu suất mô hình theo thời gian"
      subtitle="Macro F1 / False trend rate của từng run — History (vs Reference), Training (chosen variant), Backtest (walk-forward)"
      right={
        <div className={styles.perfControls}>
          <Segmented
            options={[
              { value: 'f1', label: 'Macro F1' },
              { value: 'ftr', label: 'False trend rate' },
            ]}
            value={metric}
            onChange={setMetric}
          />
          <Segmented
            options={[
              { value: 'all', label: 'Tất cả' },
              { value: 'history', label: 'History' },
              { value: 'training', label: 'Training' },
              { value: 'backtest', label: 'Backtest' },
            ]}
            value={typeFilter}
            onChange={setTypeFilter}
          />
        </div>
      }
    >
      {kindsPresent.size === 0 && allPoints.length === 0 && historyRuns.length === 0 && (
        <EmptyState
          title="Chưa có dữ liệu hiệu suất"
          hint="Cần có run lịch sử / huấn luyện / backtest hoàn tất."
        />
      )}
      {allPoints.length === 0 && historyRuns.length > 0 && <Loading label="Đang tải chỉ số các run…" />}
      {allPoints.length > 0 && visible.length === 0 && (
        <EmptyState title="Không có điểm nào thuộc bộ lọc đã chọn" />
      )}
      {visible.length > 0 && (
        <>
          <div className={styles.chartBox}>
            <Plot
              data={traces as never[]}
              layout={layout as never}
              config={config as never}
              style={{ width: '100%', height: 360 }}
              useResizeHandler
            />
          </div>
          <div className={styles.chartNote}>
            False trend rate càng thấp càng tốt (báo xu hướng sai); Macro F1 càng cao càng tốt.
            History runs so với reference labels (forward returns 12 nến vs 0.75 ATR — chỉ để đánh
            giá, không phải ground truth).
          </div>
        </>
      )}
      {historyRuns
        .filter((r) => r.status === 'done')
        .map((r) => (
          <HistoryRunPoint
            key={`hr-${r.id}`}
            run={r}
            onPoint={(p) => upsertPoint(`hr-${r.id}`, p)}
          />
        ))}
    </Card>
  );
}
