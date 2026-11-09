// Minimal ambient typings for plotly.js (v2) — the package ships no bundled
// types, and @types/plotly.js is deprecated. Covers only the API surface used
// by this app. Strict: no `any` anywhere.

declare module 'plotly.js' {
  export type Datum = string | number | Date | null;
  export type Color = string;

  export interface TraceLine {
    color?: Color;
    width?: number;
    dash?: string;
    shape?: string;
  }

  export interface TraceMarker {
    color?: Color | Color[];
    size?: number | number[];
    line?: { color?: Color; width?: number };
    symbol?: string;
    opacity?: number;
  }

  export interface CandleAppearance {
    line?: { color?: Color; width?: number };
    fillcolor?: Color;
  }

  export interface ErrorBars {
    visible?: boolean;
    array?: number[];
    arrayminus?: number[];
    type?: string;
    thickness?: number;
    width?: number;
    color?: Color;
  }

  export interface Trace {
    type?: string;
    name?: string;
    x?: Datum[];
    y?: Datum[];
    open?: number[];
    high?: number[];
    low?: number[];
    close?: number[];
    mode?: string;
    line?: TraceLine;
    marker?: TraceMarker;
    increasing?: CandleAppearance;
    decreasing?: CandleAppearance;
    width?: number | number[];
    base?: number | number[];
    error_y?: ErrorBars;
    xaxis?: string;
    yaxis?: string;
    hoverinfo?: string;
    opacity?: number;
    text?: string[];
    textposition?: string;
    fill?: string;
    connectgaps?: boolean;
  }

  export type Data = Trace;

  export interface AxisRangeSlider {
    visible?: boolean;
    thickness?: number;
  }

  export interface Axis {
    type?: string;
    gridcolor?: Color;
    zerolinecolor?: Color;
    zeroline?: boolean;
    showgrid?: boolean;
    rangeslider?: AxisRangeSlider;
    tickformat?: string;
    nticks?: number;
    showticklabels?: boolean;
    side?: string;
    domain?: number[];
    range?: [Datum, Datum];
    title?: { text?: string; font?: { color?: Color; size?: number } };
    tickfont?: { size?: number; color?: Color };
    fixedrange?: boolean;
  }

  export interface Shape {
    type?: string;
    x0?: Datum;
    x1?: Datum;
    y0?: Datum;
    y1?: Datum;
    xref?: string;
    yref?: string;
    fillcolor?: Color;
    opacity?: number;
    line?: { color?: Color; width?: number };
    layer?: string;
  }

  export interface Layout {
    paper_bgcolor?: Color;
    plot_bgcolor?: Color;
    font?: { color?: Color; size?: number; family?: string };
    margin?: { l?: number; r?: number; t?: number; b?: number };
    xaxis?: Axis;
    yaxis?: Axis;
    yaxis2?: Axis;
    xaxis2?: Axis;
    height?: number;
    autosize?: boolean;
    showlegend?: boolean;
    legend?: { orientation?: string; x?: number; y?: number; bgcolor?: string; font?: { color?: Color; size?: number } };
    barmode?: string;
    bargap?: number;
    shapes?: Shape[];
    hovermode?: string;
    dragmode?: string;
    uirevision?: string;
    title?: { text?: string; font?: { color?: Color; size?: number } };
    [key: string]: unknown;
  }

  export interface Config {
    responsive?: boolean;
    displaylogo?: boolean;
    modeBarButtonsToRemove?: string[];
    scrollZoom?: boolean;
    displayModeBar?: boolean;
    [key: string]: unknown;
  }
}
