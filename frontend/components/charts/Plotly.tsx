'use client';

// Shared Plotly component using the FULL plotly.js build.
// react-plotly.js's default export uses plotly.js-basic-dist, which does NOT
// include candlestick/ohlc traces (finance traces) — candles rendered as
// empty charts. The factory + full dist fixes it for every chart in the app.
import createPlotlyComponent from 'react-plotly.js/factory';
import Plotly from 'plotly.js/dist/plotly.js';

const Plot = createPlotlyComponent(Plotly);

export default Plot;
