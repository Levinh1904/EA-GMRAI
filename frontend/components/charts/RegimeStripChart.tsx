'use client';

import Plot from '@/components/charts/Plotly';
import type { Config, Data, Layout } from 'plotly.js';
import type { Regime } from '@/lib/types';
import { regimeColor } from '@/lib/regime';

export interface RegimePoint {
  ts: string;
  regime: Regime | null;
}

interface Props {
  points: RegimePoint[];
  height?: number;
  barWidthMs?: number;
  title?: string;
}

export default function RegimeStripChart({
  points,
  height = 104,
  barWidthMs = 15 * 60 * 1000,
  title,
}: Props) {
  if (!points.length) return null;

  const trace: Data = {
    type: 'bar',
    x: points.map((p) => p.ts),
    y: points.map(() => 1),
    width: barWidthMs,
    base: 0,
    marker: { color: points.map((p) => regimeColor(p.regime)) },
    hoverinfo: 'x',
  };

  const layout: Layout = {
    title: title ? { text: title, font: { color: '#93a0b3', size: 12 } } : undefined,
    paper_bgcolor: 'rgba(0,0,0,0)',
    plot_bgcolor: '#0d1117',
    font: { color: '#93a0b3', size: 11 },
    margin: { l: 8, r: 8, t: title ? 30 : 8, b: 30 },
    showlegend: false,
    bargap: 0,
    xaxis: {
      type: 'date',
      rangeslider: { visible: false },
      tickformat: '%H:%M\n%d/%m',
      showgrid: false,
      fixedrange: true,
    },
    yaxis: {
      range: [0, 1],
      showticklabels: false,
      showgrid: false,
      zeroline: false,
      fixedrange: true,
    },
  };

  const config: Config = { responsive: true, displaylogo: false, displayModeBar: false };

  return (
    <Plot data={[trace]} layout={layout} config={config} style={{ width: '100%', height }} useResizeHandler />
  );
}
