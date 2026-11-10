// Ambient typings for react-plotly.js (default export). Strict: no `any`.

declare module 'react-plotly.js' {
  import * as React from 'react';
  import type { Config, Data, Datum, Layout } from 'plotly.js';

  export interface PlotPoint {
    curveNumber?: number;
    pointNumber?: number;
    pointIndex?: number;
    x?: Datum;
    y?: Datum;
    customdata?: unknown;
    [key: string]: unknown;
  }

  export interface PlotMouseEvent {
    points?: PlotPoint[];
    event?: unknown;
  }

  export interface PlotParams {
    data: Data[];
    layout?: Layout;
    config?: Config;
    style?: React.CSSProperties;
    className?: string;
    divId?: string;
    useResizeHandler?: boolean;
    revision?: number;
    onInitialized?: (figure: unknown, graphDiv: HTMLElement) => void;
    onUpdate?: (figure: unknown, graphDiv: HTMLElement) => void;
    onError?: (err: Error) => void;
    onPurge?: (graphDiv: HTMLElement) => void;
    onClick?: (event: PlotMouseEvent) => void;
    onDoubleClick?: (event: PlotMouseEvent) => void;
  }

  export default class Plot extends React.Component<PlotParams> {}
}
