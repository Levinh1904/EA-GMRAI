// Ambient typings for react-plotly.js (default export). Strict: no `any`.

declare module 'react-plotly.js' {
  import * as React from 'react';
  import type { Config, Data, Layout } from 'plotly.js';

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
  }

  export default class Plot extends React.Component<PlotParams> {}
}
