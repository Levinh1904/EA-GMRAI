'use client';

import Plot from '@/components/charts/Plotly';
import type { Config, Data, Layout } from 'plotly.js';
import { variantName } from '@/lib/format';

export interface VariantMetricRow {
  variant: string;
  f1Mean: number;
  f1Std: number;
  ftrMean: number;
  ftrStd: number;
}

interface Props {
  rows: VariantMetricRow[];
  height?: number;
}

export default function VariantCompareChart({ rows, height = 340 }: Props) {
  if (!rows.length) return null;

  const labels = rows.map((r) => variantName(r.variant));

  const f1: Data = {
    type: 'bar',
    name: 'Macro F1 (trung bình)',
    x: labels,
    y: rows.map((r) => r.f1Mean),
    error_y: { visible: true, type: 'data', array: rows.map((r) => r.f1Std) },
    marker: { color: '#4c8dff', opacity: 0.92 },
  };

  const ftr: Data = {
    type: 'bar',
    name: 'False trend rate (trung bình)',
    x: labels,
    y: rows.map((r) => r.ftrMean),
    error_y: { visible: true, type: 'data', array: rows.map((r) => r.ftrStd) },
    marker: { color: '#a855f7', opacity: 0.82 },
  };

  const layout: Layout = {
    paper_bgcolor: 'rgba(0,0,0,0)',
    plot_bgcolor: '#0d1117',
    font: { color: '#93a0b3', size: 12 },
    margin: { l: 8, r: 8, t: 10, b: 40 },
    barmode: 'group',
    bargap: 0.22,
    legend: { orientation: 'h', y: 1.14, x: 0, font: { size: 11 } },
    yaxis: { gridcolor: '#1a212c', range: [0, 1], tickformat: '.0%' },
    xaxis: { gridcolor: 'transparent' },
  };

  const config: Config = { responsive: true, displaylogo: false };

  return (
    <Plot data={[f1, ftr]} layout={layout} config={config} style={{ width: '100%', height }} useResizeHandler />
  );
}
