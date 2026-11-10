'use client';

// Shared Plotly chart components for the History module (dark quant theme).
// All are rendered client-side only (imported via next/dynamic with ssr:false).

import { useMemo } from 'react';
import Plot from 'react-plotly.js';
import type { Config, Data, Layout, Shape } from 'plotly.js';
import type { HistoryBar, HistorySegment, PeriodRow } from '@/lib/types';
import { regimeColor, regimeLabel } from '@/lib/regime';
import { PERIOD_REGIME_FIELDS } from '@/app/(app)/history/shared';
import type { PlotMouseEvent } from 'react-plotly.js';

const FONT = '#93a0b3';
const GRID = '#1a212c';
const BG = '#0d1117';
const FALLBACK_PALETTE = [
  '#4c8dff',
  '#14b8a6',
  '#f59e0b',
  '#a855f7',
  '#22c55e',
  '#ef4444',
  '#8b98a9',
  '#facc15',
];

const BASE_CONFIG: Config = {
  responsive: true,
  displaylogo: false,
  scrollZoom: false,
  modeBarButtonsToRemove: ['lasso2d', 'select2d', 'autoScale2d'],
};

// ---------- Bar chart ----------

export interface HBarDatum {
  label: string;
  value: number;
  color?: string;
}

export function HBars({
  data,
  title,
  height = 300,
  horizontal = false,
  fmt = (v: number) => String(v),
}: {
  data: HBarDatum[];
  title?: string;
  height?: number;
  horizontal?: boolean;
  fmt?: (v: number) => string;
}) {
  if (!data.length) return null;

  const colors = data.map((d, i) => d.color ?? FALLBACK_PALETTE[i % FALLBACK_PALETTE.length]);
  const text = data.map((d) => fmt(d.value));

  const trace: Data = {
    type: 'bar',
    orientation: horizontal ? 'h' : 'v',
    x: horizontal ? data.map((d) => d.value) : data.map((d) => d.label),
    y: horizontal ? data.map((d) => d.label) : data.map((d) => d.value),
    marker: { color: colors },
    text,
    textposition: 'auto',
    hoverinfo: 'x+y+text',
    hovertext: text,
  };

  const layout: Layout = {
    title: title ? { text: title, font: { color: FONT, size: 12 } } : undefined,
    paper_bgcolor: 'rgba(0,0,0,0)',
    plot_bgcolor: BG,
    font: { color: FONT, size: 11 },
    margin: { l: 8, r: 8, t: title ? 34 : 12, b: 40 },
    showlegend: false,
    bargap: 0.3,
    xaxis: {
      gridcolor: GRID,
      tickfont: { size: 10 },
      automargin: true,
    },
    yaxis: {
      gridcolor: GRID,
      automargin: true,
    },
  };

  return (
    <Plot data={[trace]} layout={layout} config={BASE_CONFIG} style={{ width: '100%', height }} useResizeHandler />
  );
}

// ---------- Pie chart ----------

export interface HPieDatum {
  label: string;
  value: number;
  color?: string;
}

export function HPie({
  data,
  title,
  height = 300,
  hole = 0,
  fmt = (v: number) => String(v),
}: {
  data: HPieDatum[];
  title?: string;
  height?: number;
  hole?: number;
  fmt?: (v: number) => string;
}) {
  const filtered = data.filter((d) => d.value > 0);
  if (!filtered.length) return null;

  const trace: Data = {
    type: 'pie',
    labels: filtered.map((d) => d.label),
    values: filtered.map((d) => d.value),
    hole,
    marker: { colors: filtered.map((d, i) => d.color ?? FALLBACK_PALETTE[i % FALLBACK_PALETTE.length]) },
    textinfo: 'label+percent',
    textposition: 'auto',
    hovertemplate: '%{label}: %{value} (%{percent})<extra></extra>',
    hovertext: filtered.map((d) => fmt(d.value)),
  };

  const layout: Layout = {
    title: title ? { text: title, font: { color: FONT, size: 12 } } : undefined,
    paper_bgcolor: 'rgba(0,0,0,0)',
    font: { color: FONT, size: 11 },
    margin: { l: 8, r: 8, t: title ? 34 : 12, b: 12 },
    showlegend: true,
    legend: { font: { size: 11 } },
  };

  return (
    <Plot data={[trace]} layout={layout} config={BASE_CONFIG} style={{ width: '100%', height }} useResizeHandler />
  );
}

// ---------- Heatmap ----------

export function HHeatmap({
  xLabels,
  yLabels,
  z,
  title,
  height = 340,
  colorscale = 'Viridis',
  zfmt,
}: {
  xLabels: string[];
  yLabels: string[];
  z: number[][];
  title?: string;
  height?: number;
  colorscale?: string;
  zfmt?: (v: number) => string;
}) {
  const text = useMemo(
    () => z.map((row) => row.map((v) => (zfmt ? zfmt(v) : String(v)))),
    [z, zfmt]
  );

  const trace: Data = {
    type: 'heatmap',
    x: xLabels,
    y: yLabels,
    z,
    colorscale,
    text,
    texttemplate: '%{text}',
    hovertemplate: '%{y} → %{x}: %{z}<extra></extra>',
    showscale: true,
    colorbar: {
      thickness: 12,
      tickfont: { size: 10, color: FONT },
      outlinewidth: 0,
    },
    xgap: 1,
    ygap: 1,
  };

  const layout: Layout = {
    title: title ? { text: title, font: { color: FONT, size: 12 } } : undefined,
    paper_bgcolor: 'rgba(0,0,0,0)',
    plot_bgcolor: BG,
    font: { color: FONT, size: 11 },
    margin: { l: 90, r: 8, t: title ? 34 : 12, b: 70 },
    xaxis: { side: 'top', tickfont: { size: 10 }, automargin: true },
    yaxis: { autorange: 'reversed', tickfont: { size: 10 }, automargin: true },
  };

  return (
    <Plot data={[trace]} layout={layout} config={BASE_CONFIG} style={{ width: '100%', height }} useResizeHandler />
  );
}

// ---------- Periods stacked chart ----------

export function PeriodsChart({ rows, height = 360 }: { rows: PeriodRow[]; height?: number }) {
  const traces = useMemo<Data[]>(() => {
    const out: Data[] = PERIOD_REGIME_FIELDS.map((f) => ({
      type: 'bar',
      name: f.label,
      x: rows.map((r) => r.period_start),
      y: rows.map((r) => (r as unknown as Record<string, number>)[f.key] ?? 0),
      marker: { color: f.color },
      hovertemplate: `${f.label}: %{y} phút<extra></extra>`,
    }));
    out.push({
      type: 'scatter',
      name: 'Biên độ USD',
      mode: 'lines+markers',
      x: rows.map((r) => r.period_start),
      y: rows.map((r) => r.range_usd),
      yaxis: 'y2',
      marker: { size: 3, color: '#f0b429' },
      line: { color: '#f0b429', width: 1.4 },
      hovertemplate: 'Biên độ: %{y:.2f} USD<extra></extra>',
    });
    return out;
  }, [rows]);

  const layout: Layout = {
    paper_bgcolor: 'rgba(0,0,0,0)',
    plot_bgcolor: BG,
    font: { color: FONT, size: 11 },
    margin: { l: 8, r: 62, t: 12, b: 40 },
    barmode: 'stack',
    bargap: 0.15,
    showlegend: true,
    legend: { orientation: 'h', y: 1.06, x: 0, font: { size: 10 } },
    hovermode: 'x unified',
    xaxis: {
      type: 'date',
      gridcolor: GRID,
      tickformat: '%d/%m/%y',
      tickfont: { size: 10 },
    },
    yaxis: {
      gridcolor: GRID,
      side: 'left',
      title: { text: 'Phút', font: { color: FONT, size: 10 } },
    },
    yaxis2: {
      overlaying: 'y',
      side: 'right',
      title: { text: 'USD', font: { color: FONT, size: 10 } },
      showgrid: false,
    },
  };

  return (
    <Plot data={traces} layout={layout} config={BASE_CONFIG} style={{ width: '100%', height }} useResizeHandler />
  );
}

// ---------- Timeline (candles + regime strip + rangeslider) ----------

const UP = '#22c55e';
const DOWN = '#ef4444';
const BAR_MS = 15 * 60 * 1000;

export interface TimelineChartProps {
  bars: HistoryBar[];
  segments: HistorySegment[];
  selectedSegmentId: number | null;
  focusRange: [string, string] | null;
  onSelectSegment: (id: number | null) => void;
  onClearFocus: () => void;
  /** 1 = full resolution; >1 = render every n-th bar (visual only, segment strip stays exact). */
  density?: number;
  height?: number;
}

function segEndTs(s: HistorySegment): string {
  const endMs = new Date(s.end_ts).getTime();
  if (Number.isNaN(endMs)) return s.end_ts;
  return new Date(endMs + BAR_MS).toISOString();
}

export function TimelineChart({
  bars,
  segments,
  selectedSegmentId,
  focusRange,
  onSelectSegment,
  onClearFocus,
  density = 1,
  height = 520,
}: TimelineChartProps) {
  const sampled = useMemo<HistoryBar[]>(() => {
    if (!density || density <= 1) return bars;
    const out: HistoryBar[] = [];
    for (let i = 0; i < bars.length; i += density) out.push(bars[i]);
    return out;
  }, [bars, density]);

  const segById = useMemo(() => {
    const m = new Map<number, HistorySegment>();
    for (const s of segments) m.set(s.id, s);
    return m;
  }, [segments]);

  const selected = selectedSegmentId != null ? (segById.get(selectedSegmentId) ?? null) : null;

  const traces = useMemo<Data[]>(() => {
    const ts = sampled.map((b) => b.ts);
    const closeLine: Data = {
      type: 'scatter',
      x: ts,
      y: sampled.map((b) => b.close),
      mode: 'lines',
      line: { color: 'rgba(76,141,255,0.4)', width: 1 },
      hoverinfo: 'skip',
      showlegend: false,
      xaxis: 'x',
      yaxis: 'y',
    };
    const candles: Data = {
      type: 'candlestick',
      name: 'XAUUSD M15',
      x: ts,
      open: sampled.map((b) => b.open),
      high: sampled.map((b) => b.high),
      low: sampled.map((b) => b.low),
      close: sampled.map((b) => b.close),
      increasing: { line: { color: UP, width: 1 }, fillcolor: UP },
      decreasing: { line: { color: DOWN, width: 1 }, fillcolor: DOWN },
      customdata: sampled.map((b) => [
        regimeLabel(b.regime),
        b.confidence != null ? (b.confidence * 100).toFixed(1) : '—',
        b.hmm_state ?? '—',
        b.permission ?? '—',
      ]),
      hovertemplate:
        '<b>%{x|%d/%m/%Y %H:%M} UTC</b><br>Mở %{open:,.2f} · Cao %{high:,.2f}<br>Thấp %{low:,.2f} · Đóng %{close:,.2f}<br>Regime: %{customdata[0]} · Conf %{customdata[1]}%<br>HMM state %{customdata[2]} · %{customdata[3]}<extra></extra>',
      xaxis: 'x',
      yaxis: 'y',
    };
    const strip: Data = {
      type: 'bar',
      name: 'Regime',
      x: segments.map((s) => s.start_ts),
      y: segments.map(() => 1),
      width: segments.map((s) => {
        const startMs = new Date(s.start_ts).getTime();
        const endMs = new Date(s.end_ts).getTime();
        if (Number.isNaN(startMs) || Number.isNaN(endMs)) return BAR_MS;
        return Math.max(endMs - startMs, 0) + BAR_MS;
      }),
      base: 0,
      marker: { color: segments.map((s) => regimeColor(s.regime)), line: { width: 0 } },
      customdata: segments.map((s) => s.id),
      hovertext: segments.map(
        (s) =>
          `Seg #${s.segment_index} · ${regimeLabel(s.regime)} · ${s.duration_minutes} phút · ${s.bar_count} nến`
      ),
      hoverinfo: 'text',
      showlegend: false,
      xaxis: 'x',
      yaxis: 'y2',
    };
    return [closeLine, candles, strip];
  }, [sampled, segments]);

  const layout = useMemo<Layout>(() => {
    const shapes: Shape[] = [];
    if (selected) {
      shapes.push({
        type: 'rect',
        xref: 'x',
        x0: selected.start_ts,
        x1: segEndTs(selected),
        yref: 'paper',
        y0: 0,
        y1: 1,
        fillcolor: regimeColor(selected.regime),
        opacity: 0.25,
        line: { color: 'rgba(255,255,255,0.65)', width: 1 },
        layer: 'below',
      });
    }
    return {
      paper_bgcolor: 'rgba(0,0,0,0)',
      plot_bgcolor: BG,
      font: { color: FONT, size: 11 },
      margin: { l: 8, r: 62, t: 8, b: 46 },
      hovermode: 'x',
      showlegend: true,
      legend: { orientation: 'h', y: 1.02, x: 0, font: { size: 11 } },
      uirevision: 'history-timeline',
      shapes,
      xaxis: {
        type: 'date',
        gridcolor: GRID,
        tickformat: '%H:%M\n%d/%m',
        rangeslider: { visible: true, thickness: 0.08, bgcolor: '#10141b', bordercolor: '#222a38' },
        ...(focusRange ? { range: focusRange } : {}),
      },
      yaxis: {
        domain: [0.3, 1],
        side: 'right',
        gridcolor: GRID,
        tickformat: ',.1f',
      },
      yaxis2: {
        domain: [0.03, 0.2],
        range: [0, 1],
        showticklabels: false,
        fixedrange: true,
        zeroline: false,
        showgrid: false,
      },
      bargap: 0,
      barmode: 'overlay',
    };
  }, [selected, focusRange]);

  const handleClick = (ev: PlotMouseEvent) => {
    const pt = ev.points?.[0];
    if (!pt) return;
    if (pt.curveNumber === 2) {
      const id = typeof pt.customdata === 'number' ? pt.customdata : null;
      onSelectSegment(id);
      return;
    }
    const raw = pt.x;
    const x = typeof raw === 'string' ? raw : raw instanceof Date ? raw.toISOString() : null;
    if (!x) return;
    const seg = segments.find((s) => x >= s.start_ts && x <= s.end_ts);
    onSelectSegment(seg ? seg.id : null);
  };

  return (
    <Plot
      data={traces}
      layout={layout}
      config={BASE_CONFIG}
      style={{ width: '100%', height }}
      useResizeHandler
      onClick={handleClick}
      onDoubleClick={() => onClearFocus()}
    />
  );
}
