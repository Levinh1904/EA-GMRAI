'use client';

// Shared Plotly chart components for the History module (dark quant theme).
// All are rendered client-side only (imported via next/dynamic with ssr:false).

import { useMemo } from 'react';
import Plot from '@/components/charts/Plotly';
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

// Timeline gets full zoom/pan controls: wheel zoom + drag zoom + modebar buttons.
const TIMELINE_CONFIG: Config = {
  responsive: true,
  displaylogo: false,
  scrollZoom: true,
  doubleClick: 'reset+autosize',
  modeBarButtons: [['zoom2d', 'pan2d', 'zoomIn2d', 'zoomOut2d', 'resetScale2d']],
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

export type TimelineStripMode = 'ai' | 'reference' | 'overlay' | 'disagreement';

/** Client-built segment of the reference strip (grouped consecutive reference_regime). */
export interface RefStripSegment {
  start_ts: string;
  end_ts: string;
  regime: string;
}

/** Client-built segment of the disagreement strip (AI vs reference). */
export interface DiffStripSegment {
  start_ts: string;
  end_ts: string;
  agree: boolean;
}

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
  /** Which regime strip(s) to render below the candles. */
  stripMode?: TimelineStripMode;
  /** Reference segments (built client-side from per-bar reference_regime). */
  refSegments?: RefStripSegment[];
  /** Disagreement segments (built client-side from regime vs reference_regime). */
  diffSegments?: DiffStripSegment[];
  /** Called with the bar's ISO timestamp when a candle is clicked (curveNumber 0/1). */
  onSelectBar?: (barTs: string) => void;
}

function segEndTs(s: HistorySegment): string {
  const endMs = new Date(s.end_ts).getTime();
  if (Number.isNaN(endMs)) return s.end_ts;
  return new Date(endMs + BAR_MS).toISOString();
}

/** Normalize a Plotly click x value ("2025-11-11 15:00", Date, ISO…) to an ISO timestamp. */
function normalizeTs(raw: unknown): string | null {
  if (raw instanceof Date) {
    return Number.isNaN(raw.getTime()) ? null : raw.toISOString();
  }
  if (typeof raw === 'number') {
    const d = new Date(raw);
    return Number.isNaN(d.getTime()) ? null : d.toISOString();
  }
  if (typeof raw === 'string') {
    const s = raw.trim();
    if (!s) return null;
    // Already timezone-aware ISO — keep as-is.
    if (/Z$|[+-]\d{2}:?\d{2}$/.test(s)) return s;
    // "2025-11-11 15:00" / "2025-11-11 15:00:00[.xxx]" → UTC ISO.
    const m = s.match(/^(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?)$/);
    if (m) return `${m[1]}T${m[2]}Z`;
    return s;
  }
  return null;
}

function makeStripTrace(
  rows: Array<{ start_ts: string; end_ts: string; regime: string; label?: string }>,
  yaxis: string,
  name: string,
  showLegend: boolean
): Data {
  return {
    type: 'bar',
    name,
    x: rows.map((r) => r.start_ts),
    y: rows.map(() => 1),
    width: rows.map((r) => {
      const startMs = new Date(r.start_ts).getTime();
      const endMs = new Date(r.end_ts).getTime();
      if (Number.isNaN(startMs) || Number.isNaN(endMs)) return BAR_MS;
      return Math.max(endMs - startMs, 0) + BAR_MS;
    }),
    base: 0,
    marker: { color: rows.map((r) => regimeColor(r.regime)), line: { width: 0 } },
    hovertext: rows.map(
      (r) => `${name} · ${regimeLabel(r.regime)} · ${r.start_ts} → ${r.end_ts}${r.label ? ` · ${r.label}` : ''}`
    ),
    hoverinfo: 'text',
    showlegend: showLegend,
    legendgroup: yaxis,
    xaxis: 'x',
    yaxis,
  };
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
  stripMode = 'ai',
  refSegments = [],
  diffSegments = [],
  onSelectBar,
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

  const overlay = stripMode === 'overlay';

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
        regimeLabel(b.reference_regime),
        b.reference_reason ?? '—',
      ]),
      hovertemplate:
        '<b>%{x|%d/%m/%Y %H:%M} UTC</b><br>Mở %{open:,.2f} · Cao %{high:,.2f}<br>Thấp %{low:,.2f} · Đóng %{close:,.2f}<br>AI: %{customdata[0]} · Conf %{customdata[1]}%<br>HMM state %{customdata[2]} · %{customdata[3]}<br>Reference: %{customdata[4]}<br><i>%{customdata[5]}</i><extra></extra>',
      xaxis: 'x',
      yaxis: 'y',
    };
    const out: Data[] = [closeLine, candles];

    if (stripMode === 'ai' || stripMode === 'overlay') {
      const aiStrip = makeStripTrace(
        segments.map((s) => ({
          start_ts: s.start_ts,
          end_ts: s.end_ts,
          regime: s.regime,
          label: `Seg #${s.segment_index} · ${s.bar_count} nến`,
        })),
        'y2',
        'AI',
        overlay
      );
      aiStrip.customdata = segments.map((s) => s.id);
      out.push(aiStrip);
    }
    if (stripMode === 'reference' || stripMode === 'overlay') {
      out.push(makeStripTrace(refSegments, overlay ? 'y3' : 'y2', 'Reference', overlay));
    }
    if (stripMode === 'disagreement') {
      out.push({
        type: 'bar',
        name: 'Bất đồng',
        x: diffSegments.map((d) => d.start_ts),
        y: diffSegments.map(() => 1),
        width: diffSegments.map((d) => {
          const startMs = new Date(d.start_ts).getTime();
          const endMs = new Date(d.end_ts).getTime();
          if (Number.isNaN(startMs) || Number.isNaN(endMs)) return BAR_MS;
          return Math.max(endMs - startMs, 0) + BAR_MS;
        }),
        base: 0,
        marker: {
          color: diffSegments.map((d) =>
            d.agree ? 'rgba(100,116,139,0.55)' : 'rgba(244,63,94,0.9)'
          ),
          line: { width: 0 },
        },
        hovertext: diffSegments.map((d) =>
          d.agree ? 'Đồng thuận AI = Reference' : 'Bất đồng AI ≠ Reference'
        ),
        hoverinfo: 'text',
        showlegend: false,
        xaxis: 'x',
        yaxis: 'y2',
      });
    }
    return out;
  }, [sampled, segments, refSegments, diffSegments, stripMode, overlay]);

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
    const yaxis: Layout['yaxis'] = overlay
      ? { domain: [0.42, 1], side: 'right', gridcolor: GRID, tickformat: ',.1f', fixedrange: true }
      : { domain: [0.3, 1], side: 'right', gridcolor: GRID, tickformat: ',.1f', fixedrange: true };
    const yaxis2: Layout['yaxis'] = overlay
      ? { domain: [0.2, 0.3], range: [0, 1], showticklabels: false, fixedrange: true, zeroline: false, showgrid: false }
      : { domain: [0.03, 0.2], range: [0, 1], showticklabels: false, fixedrange: true, zeroline: false, showgrid: false };
    const yaxis3: Layout['yaxis'] | undefined = overlay
      ? { domain: [0.03, 0.13], range: [0, 1], showticklabels: false, fixedrange: true, zeroline: false, showgrid: false }
      : undefined;

    return {
      paper_bgcolor: 'rgba(0,0,0,0)',
      plot_bgcolor: BG,
      font: { color: FONT, size: 11 },
      margin: { l: 8, r: 62, t: 8, b: 46 },
      // NOTE: hovermode 'x' breaks candlestick rendering (plotly.js bug) — keep default.
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
      yaxis,
      yaxis2,
      ...(yaxis3 ? { yaxis3 } : {}),
      bargap: 0,
      barmode: 'overlay',
    };
  }, [selected, focusRange, overlay]);

  const handleClick = (ev: PlotMouseEvent) => {
    const pt = ev.points?.[0];
    if (!pt) return;
    const cn = pt.curveNumber;
    if (cn === 0 || cn === 1) {
      // Candle (or close line) click → bar detail.
      const x = normalizeTs(pt.x);
      if (!x) return;
      if (onSelectBar) {
        onSelectBar(x);
        return;
      }
      // Legacy fallback: select the segment containing the clicked bar.
      const seg = segments.find((s) => x >= s.start_ts && x <= s.end_ts);
      onSelectSegment(seg ? seg.id : null);
      return;
    }
    // Strip clicks: only the AI strip (curve 2 in ai/overlay mode) selects a segment.
    const aiStripCurve = stripMode === 'ai' || stripMode === 'overlay' ? 2 : -1;
    if (cn === aiStripCurve) {
      const id = typeof pt.customdata === 'number' ? pt.customdata : null;
      onSelectSegment(id);
    }
  };

  return (
    <Plot
      data={traces}
      layout={layout}
      config={TIMELINE_CONFIG}
      revision={sampled.length + (segments.length << 20) + refSegments.length + diffSegments.length}
      style={{ width: '100%', height }}
      useResizeHandler
      onClick={handleClick}
      onDoubleClick={() => onClearFocus()}
    />
  );
}
