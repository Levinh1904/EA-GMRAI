'use client';

import Plot from 'react-plotly.js';
import type { Config, Data, Layout } from 'plotly.js';
import type { Candle, Regime } from '@/lib/types';
import { regimeColor } from '@/lib/regime';

const UP = '#22c55e';
const DOWN = '#ef4444';
const EMA_COLOR = '#f0b429';

interface Props {
  candles: Candle[];
  ema?: (number | null)[];
  regimes?: (Regime | null)[];
  height?: number;
  title?: string;
}

export default function CandlestickChart({ candles, ema, regimes, height = 470, title }: Props) {
  if (!candles.length) return null;

  const ts = candles.map((c) => c.ts);
  const dirColors = candles.map((c) => (c.close >= c.open ? UP : DOWN));

  const traces: Data[] = [
    {
      type: 'candlestick',
      name: 'XAUUSD',
      x: ts,
      open: candles.map((c) => c.open),
      high: candles.map((c) => c.high),
      low: candles.map((c) => c.low),
      close: candles.map((c) => c.close),
      increasing: { line: { color: UP, width: 1 }, fillcolor: UP },
      decreasing: { line: { color: DOWN, width: 1 }, fillcolor: DOWN },
      yaxis: 'y',
      xaxis: 'x',
    },
    {
      type: 'bar',
      name: 'Tick volume',
      x: ts,
      y: candles.map((c) => c.tick_volume),
      marker: { color: dirColors, opacity: 0.5 },
      yaxis: 'y2',
      xaxis: 'x',
      hoverinfo: 'x+y',
    },
  ];

  if (ema && ema.length === candles.length) {
    traces.push({
      type: 'scatter',
      name: 'EMA20',
      x: ts,
      y: ema,
      mode: 'lines',
      line: { color: EMA_COLOR, width: 1.4 },
      yaxis: 'y',
      xaxis: 'x',
    });
  }

  const shapes: Layout['shapes'] = [];
  if (regimes && regimes.length === candles.length) {
    let start = 0;
    for (let i = 1; i <= regimes.length; i++) {
      const changed = i === regimes.length || regimes[i] !== regimes[start];
      if (changed) {
        const r = regimes[start];
        if (r) {
          shapes.push({
            type: 'rect',
            x0: candles[start].ts,
            x1: i < candles.length ? candles[i].ts : candles[candles.length - 1].ts,
            yref: 'paper',
            y0: 0,
            y1: 1,
            fillcolor: regimeColor(r),
            opacity: 0.055,
            line: { width: 0 },
            layer: 'below',
          });
        }
        start = i;
      }
    }
  }

  const layout: Layout = {
    title: title ? { text: title, font: { color: '#93a0b3', size: 13 } } : undefined,
    paper_bgcolor: 'rgba(0,0,0,0)',
    plot_bgcolor: '#0d1117',
    font: { color: '#93a0b3', size: 11 },
    margin: { l: 8, r: 66, t: title ? 38 : 10, b: 34 },
    hovermode: 'x unified',
    showlegend: true,
    legend: { orientation: 'h', y: title ? 1.16 : 1.08, x: 0, font: { size: 11 } },
    xaxis: {
      type: 'date',
      gridcolor: '#1a212c',
      rangeslider: { visible: false },
      tickformat: '%H:%M\n%d/%m',
      showgrid: true,
    },
    yaxis: {
      gridcolor: '#1a212c',
      side: 'right',
      domain: [0.32, 1],
      tickformat: ',.1f',
    },
    yaxis2: {
      gridcolor: '#131a24',
      side: 'right',
      domain: [0, 0.22],
      showticklabels: false,
      fixedrange: true,
    },
    shapes,
    bargap: 0.25,
  };

  const config: Config = {
    responsive: true,
    displaylogo: false,
    scrollZoom: false,
    modeBarButtonsToRemove: ['lasso2d', 'select2d', 'autoScale2d'],
  };

  return (
    <Plot data={traces} layout={layout} config={config} style={{ width: '100%', height }} useResizeHandler />
  );
}
