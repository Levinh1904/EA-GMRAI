'use client';

// Chart overlays for the TradingChart:
//  - RegimeBandPrimitive: canvas primitive drawing regime bands as pane background
//  - ChartOHLCLegend: OHLC readout driven by crosshair moves
//  - RegimePopover: detail popover when clicking a regime band area

import type {
  ISeriesPrimitive,
  IPrimitivePaneRenderer,
  IPrimitivePaneView,
  SeriesAttachedParameter,
  Time,
} from 'lightweight-charts';
import type { HistoryBar, HistorySegment } from '@/lib/types';
import { regimeColor, regimeLabel } from '@/lib/regime';
import { fmtNum, fmtPct, fmtPrice, fmtUtc } from '@/lib/format';
import { fmtMinHours } from '@/app/(app)/history/shared';
import styles from './tradingchart.module.css';

// ---------- Band fill palette (low-alpha backgrounds) ----------

export const REGIME_BAND_FILL: Record<string, string> = {
  TREND_UP: 'rgba(34, 197, 94, 0.13)',
  TREND_DOWN: 'rgba(239, 68, 68, 0.13)',
  SIDEWAYS: 'rgba(139, 152, 169, 0.11)',
  EARLY_TREND_UP: 'rgba(20, 184, 166, 0.13)',
  EARLY_TREND_DOWN: 'rgba(20, 184, 166, 0.13)',
  EARLY_TREND: 'rgba(20, 184, 166, 0.13)',
  TRANSITION: 'rgba(168, 85, 247, 0.12)',
  HIGH_VOLATILITY: 'rgba(245, 158, 11, 0.16)',
  UNKNOWN: 'rgba(75, 85, 99, 0)',
  // Live tail: candles newer than the analysed run — shown but not yet
  // classified by the model (honest "not analysed" marker).
  LIVE: 'rgba(76, 141, 255, 0.10)',
  // Disagreement strip (History "Bất đồng" mode) — higher-alpha by design so
  // the agree/disagree band is clearly readable as a single strip.
  AGREE: 'rgba(100, 116, 139, 0.55)',
  DISAGREE: 'rgba(244, 63, 94, 0.9)',
};

/** Opaque strip colours — used when the band is drawn as its own pane. */
export const REGIME_STRIP_FILL: Record<string, string> = {
  TREND_UP: '#22c55e',
  TREND_DOWN: '#ef4444',
  SIDEWAYS: '#8b98a9',
  EARLY_TREND_UP: '#14b8a6',
  EARLY_TREND_DOWN: '#0d9488',
  EARLY_TREND: '#14b8a6',
  TRANSITION: '#a855f7',
  HIGH_VOLATILITY: '#f59e0b',
  UNKNOWN: '#3f4756',
  LIVE: '#4c8dff',
  AGREE: '#64748b',
  DISAGREE: '#f43f5e',
};

export function bandFill(regime: string): string {
  return REGIME_BAND_FILL[regime] ?? REGIME_BAND_FILL.UNKNOWN;
}

export function stripFill(regime: string): string {
  return REGIME_STRIP_FILL[regime] ?? REGIME_STRIP_FILL.UNKNOWN;
}

export interface Band {
  start: number; // unix seconds
  end: number; // unix seconds
  regime: string;
}

// ---------------------------------------------------------------------------
// Canvas primitive: regime bands as chart background
// ---------------------------------------------------------------------------

class RegimeBandRenderer implements IPrimitivePaneRenderer {
  constructor(
    private readonly prim: RegimeBandPrimitive
  ) {}

  draw(target: Parameters<IPrimitivePaneRenderer['draw']>[0]): void {
    const prim = this.prim;
    if (!prim.visible) return;
    const timeScale = prim.timeScale;
    const bands = prim.bands;
    if (!timeScale || bands.length === 0) return;

    const range = timeScale.getVisibleRange();
    if (!range) return;
    const barPx = Math.max(1, Math.ceil((timeScale.options()?.barSpacing ?? 1) * 1));

    target.useBitmapCoordinateSpace((scope) => {
      const ctx = scope.context;
      const height = scope.mediaSize.height * scope.verticalPixelRatio;
      const hpx = scope.horizontalPixelRatio;
      const vpx = scope.verticalPixelRatio;
      let top = 0;
      let bottom = height;
      // `bottom*` areas reserve the lower band of the pane for the regime
      // strip; the candle series shrinks itself via scaleMargins. The upper /
      // lower halves let Overlay mode stack AI and Reference strips.
      if (prim.area === 'top') bottom = height * 0.55;
      else if (prim.area === 'bottom') top = height * 0.76;
      else if (prim.area === 'bottomUpper') {
        top = height * 0.76;
        bottom = height * 0.88;
      } else if (prim.area === 'bottomLower') {
        top = height * 0.88;
        bottom = height;
      }
      const bandH = bottom - top;

      for (let i = 0; i < bands.length; i++) {
        const b = bands[i];
        if (b.start > (range.to as number)) break;
        if (b.end < (range.from as number)) continue;
        // NOTE: timeToCoordinate() returns null for timestamps that are not
        // present in the series data, so never probe `end + 1` — resolve the
        // band's own end and extend it by one bar's pixel width instead.
        const x1 = timeScale.timeToCoordinate(b.start as Time);
        if (x1 == null) continue;
        const x2 = timeScale.timeToCoordinate(b.end as Time);
        const right = (x2 == null ? x1 : x2) + barPx;
        const bx1 = Math.floor(x1 * hpx);
        let bw = Math.max(1, Math.ceil((right - x1) * hpx));
        // Clip to the plot area (mediaSize excludes the price scale), so the
        // strip never paints over the price axis.
        const plotRight = Math.floor(scope.mediaSize.width * hpx);
        if (bx1 + bw > plotRight) bw = Math.max(0, plotRight - bx1);
        if (bw <= 0) continue;
        ctx.globalAlpha = prim.strip ? 0.9 : 1;
        ctx.fillStyle = prim.strip ? stripFill(b.regime) : bandFill(b.regime);
        ctx.fillRect(bx1, top, bw, bandH);
        ctx.globalAlpha = 1;

        // Label inside wide-enough bands so the strip is readable on its own.
        if (prim.showLabels && bw > 54 * hpx) {
          const label = regimeLabel(b.regime);
          const fontSize = Math.round(10 * vpx);
          ctx.font = `${fontSize}px -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif`;
          const textWidth = ctx.measureText(label).width;
          if (textWidth + 8 * hpx < bw) {
            ctx.fillStyle = 'rgba(240, 245, 255, 0.92)';
            ctx.textBaseline = 'middle';
            ctx.fillText(label, bx1 + 4 * hpx, (top + bottom) / 2);
          }
        }
      }
    });
  }
}

export class RegimeBandPrimitive implements ISeriesPrimitive<Time> {
  bands: Band[] = [];
  visible = true;
  area: 'full' | 'top' | 'bottom' | 'bottomUpper' | 'bottomLower' = 'full';
  /** Draw opaque strip colours (used when the primitive owns a whole pane). */
  strip = false;
  /** Draw the regime name inside wide bands. */
  showLabels = false;
  timeScale: ReturnType<SeriesAttachedParameter<Time>['chart']['timeScale']> | null = null;
  private requestUpdate: (() => void) | null = null;
  private view: IPrimitivePaneView;

  constructor() {
    this.view = {
      // 'bottom' paints under the grid/background fills; the strip must sit
      // above the pane background to be visible at all.
      zOrder: () => 'normal',
      renderer: () => new RegimeBandRenderer(this),
    };
  }

  attached(param: SeriesAttachedParameter<Time>): void {
    this.timeScale = param.chart.timeScale();
    this.requestUpdate = param.requestUpdate;
  }

  detached(): void {
    this.timeScale = null;
    this.requestUpdate = null;
  }

  setBands(bands: Band[]): void {
    this.bands = bands;
    this.requestUpdate?.();
  }

  setVisible(visible: boolean): void {
    this.visible = visible;
    this.requestUpdate?.();
  }

  setArea(area: 'full' | 'top' | 'bottom' | 'bottomUpper' | 'bottomLower'): void {
    this.area = area;
    this.requestUpdate?.();
  }

  setStrip(strip: boolean): void {
    this.strip = strip;
    this.requestUpdate?.();
  }

  setShowLabels(show: boolean): void {
    this.showLabels = show;
    this.requestUpdate?.();
  }

  paneViews(): readonly IPrimitivePaneView[] {
    return [this.view];
  }
}

// ---------------------------------------------------------------------------
// Replay cursor primitive: a dashed vertical "now" line drawn across the pane.
// ---------------------------------------------------------------------------

class ReplayCursorRenderer implements IPrimitivePaneRenderer {
  constructor(private readonly prim: ReplayCursorPrimitive) {}

  draw(target: Parameters<IPrimitivePaneRenderer['draw']>[0]): void {
    const prim = this.prim;
    if (prim.cursorTime == null) return;
    const timeScale = prim.timeScale;
    if (!timeScale) return;

    const range = timeScale.getVisibleRange();
    if (!range) return;
    const t = prim.cursorTime;
    if (t < (range.from as number) || t > (range.to as number)) return;

    target.useBitmapCoordinateSpace((scope) => {
      const ctx = scope.context;
      const x = timeScale.timeToCoordinate(t as Time);
      if (x == null) return;
      const hpx = scope.horizontalPixelRatio;
      const vpx = scope.verticalPixelRatio;
      const bx = Math.round(x * hpx);
      const height = scope.mediaSize.height * vpx;

      ctx.save();
      ctx.strokeStyle = prim.color;
      ctx.lineWidth = 1.5 * hpx;
      ctx.setLineDash([5 * hpx, 4 * hpx]);
      ctx.beginPath();
      ctx.moveTo(bx, 0);
      ctx.lineTo(bx, height);
      ctx.stroke();
      ctx.setLineDash([]);

      // Small filled triangle at the top of the line.
      const triH = 7 * vpx;
      ctx.fillStyle = prim.color;
      ctx.beginPath();
      ctx.moveTo(bx - triH, 0);
      ctx.lineTo(bx + triH, 0);
      ctx.lineTo(bx, triH);
      ctx.closePath();
      ctx.fill();
      ctx.restore();
    });
  }
}

export class ReplayCursorPrimitive implements ISeriesPrimitive<Time> {
  cursorTime: number | null = null;
  color = '#f0b429';
  timeScale: ReturnType<SeriesAttachedParameter<Time>['chart']['timeScale']> | null = null;
  private requestUpdate: (() => void) | null = null;
  private view: IPrimitivePaneView;

  constructor() {
    this.view = {
      zOrder: () => 'top',
      renderer: () => new ReplayCursorRenderer(this),
    };
  }

  attached(param: SeriesAttachedParameter<Time>): void {
    this.timeScale = param.chart.timeScale();
    this.requestUpdate = param.requestUpdate;
  }

  detached(): void {
    this.timeScale = null;
    this.requestUpdate = null;
  }

  setCursor(cursorTime: number | null): void {
    this.cursorTime = cursorTime;
    this.requestUpdate?.();
  }

  setColor(color: string): void {
    this.color = color;
    this.requestUpdate?.();
  }

  paneViews(): readonly IPrimitivePaneView[] {
    return [this.view];
  }
}

export interface LegendBar {
  time: string; // ISO
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  prevClose: number | null;
  ema: number | null;
  regime: string | null;
  refRegime: string | null;
}

export function ChartOHLCLegend({ bar, label }: { bar: LegendBar | null; label: string }) {
  if (!bar) {
    return (
      <div className={styles.ohlcLegend}>
        <span className={styles.ohlcSymbol}>{label}</span>
        <span className={styles.ohlcHint}>Di chuột vào biểu đồ để xem OHLC</span>
      </div>
    );
  }
  const change = bar.prevClose != null ? bar.close - bar.prevClose : null;
  const changePct =
    change != null && bar.prevClose ? (change / bar.prevClose) * 100 : null;
  const up = change == null ? undefined : change >= 0;
  const cls = up == null ? '' : up ? styles.ohlcUp : styles.ohlcDown;

  return (
    <div className={styles.ohlcLegend}>
      <span className={styles.ohlcSymbol}>{label}</span>
      <span className={styles.ohlcCell}>
        <span className={styles.ohlcKey}>O</span>
        <span className="num">{fmtPrice(bar.open)}</span>
      </span>
      <span className={styles.ohlcCell}>
        <span className={styles.ohlcKey}>H</span>
        <span className="num">{fmtPrice(bar.high)}</span>
      </span>
      <span className={styles.ohlcCell}>
        <span className={styles.ohlcKey}>L</span>
        <span className="num">{fmtPrice(bar.low)}</span>
      </span>
      <span className={styles.ohlcCell}>
        <span className={styles.ohlcKey}>C</span>
        <span className="num">{fmtPrice(bar.close)}</span>
      </span>
      <span className={`${styles.ohlcCell} ${cls}`}>
        <span className="num">
          {change == null ? '—' : `${change >= 0 ? '+' : ''}${fmtPrice(change)}`}
        </span>
        <span className="num">({changePct == null ? '—' : `${fmtPct(changePct / 100, 2)}`})</span>
      </span>
      <span className={styles.ohlcCell}>
        <span className={styles.ohlcKey}>Vol</span>
        <span className="num">{fmtNum(bar.volume, 0)}</span>
      </span>
      {bar.ema != null && (
        <span className={styles.ohlcCell}>
          <span className={styles.ohlcKey} style={{ color: 'var(--accent)' }}>
            EMA20
          </span>
          <span className="num">{fmtPrice(bar.ema)}</span>
        </span>
      )}
      {bar.regime && (
        <span className={styles.ohlcCell}>
          <span className={styles.ohlcRegimeDot} style={{ background: regimeColor(bar.regime) }} />
          <span style={{ color: regimeColor(bar.regime) }}>{regimeLabel(bar.regime)}</span>
        </span>
      )}
      {bar.refRegime && (
        <span className={styles.ohlcCell}>
          <span
            className={styles.ohlcRegimeDot}
            style={{ background: regimeColor(bar.refRegime), borderRadius: 3 }}
          />
          <span className={styles.ohlcKey} style={{ color: '#c084fc' }}>
            Ref
          </span>
          <span style={{ color: regimeColor(bar.refRegime) }}>{regimeLabel(bar.refRegime)}</span>
        </span>
      )}
      <span className={styles.ohlcTime}>{fmtUtc(bar.time)}</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Regime band click popover
// ---------------------------------------------------------------------------

export interface BandDetail {
  ts: string;
  band: Band | null;
  refBand: Band | null;
  bar: HistoryBar | null;
  segment: HistorySegment | null;
}

export function RegimePopover({
  detail,
  x,
  y,
  onClose,
  containerWidth,
}: {
  detail: BandDetail;
  x: number;
  y: number;
  onClose: () => void;
  containerWidth: number;
}) {
  const { band, refBand, bar, segment } = detail;
  const regime = band?.regime ?? bar?.regime ?? null;
  const flip = x > containerWidth * 0.55;

  return (
    <div
      className={`${styles.popover} ${flip ? styles.popoverLeft : styles.popoverRight}`}
      style={{ top: Math.max(4, y - 8), left: x }}
      role="dialog"
      aria-label="Chi tiết vùng regime"
    >
      <div className={styles.popoverHead}>
        <span className={styles.popoverRegime} style={{ color: regimeColor(regime) }}>
          {regimeLabel(regime)}
        </span>
        <button type="button" className={styles.popoverClose} onClick={onClose} aria-label="Đóng">
          ✕
        </button>
      </div>
      <div className={styles.popoverBody}>
        {band && (
          <>
            <div className={styles.popoverRow}>
              <span>Từ</span>
              <span className="num">{fmtUtc(new Date(band.start * 1000).toISOString())}</span>
            </div>
            <div className={styles.popoverRow}>
              <span>Đến</span>
              <span className="num">{fmtUtc(new Date(band.end * 1000).toISOString())}</span>
            </div>
            <div className={styles.popoverRow}>
              <span>Thời lượng</span>
              <span className="num">
                {band.end > band.start ? fmtMinHours(Math.round((band.end - band.start) / 60)) : '—'}
              </span>
            </div>
          </>
        )}
        {refBand && (
          <div className={styles.popoverRow}>
            <span>Reference</span>
            <span style={{ color: regimeColor(refBand.regime) }}>
              {regimeLabel(refBand.regime)}
            </span>
          </div>
        )}
        {segment && (
          <>
            <div className={styles.popoverRow}>
              <span>Số nến</span>
              <span className="num">{segment.bar_count}</span>
            </div>
            <div className={styles.popoverRow}>
              <span>Độ tin cậy TB</span>
              <span className="num">{fmtPct(segment.confidence_mean)}</span>
            </div>
            {segment.model_version_id != null && (
              <div className={styles.popoverRow}>
                <span>Model version</span>
                <span className="num">v{segment.model_version_id}</span>
              </div>
            )}
          </>
        )}
        {bar && (
          <>
            {bar.rf_probs && (
              <div className={styles.popoverProbs}>
                {Object.entries(bar.rf_probs)
                  .sort((a, b) => b[1] - a[1])
                  .map(([k, v]) => (
                    <div className={styles.popoverProbRow} key={k}>
                      <span style={{ color: regimeColor(k) }}>{regimeLabel(k)}</span>
                      <span className="num">{fmtPct(v)}</span>
                    </div>
                  ))}
              </div>
            )}
            {bar.reference_reason && (
              <div className={styles.popoverRow}>
                <span>Lý do Reference</span>
                <span>{bar.reference_reason}</span>
              </div>
            )}
            <div className={styles.popoverRow}>
              <span>ATR ratio</span>
              <span className="num">{fmtNum(bar.atr_ratio)}</span>
            </div>
            <div className={styles.popoverRow}>
              <span>ADX norm</span>
              <span className="num">{fmtNum(bar.adx_norm)}</span>
            </div>
            <div className={styles.popoverRow}>
              <span>Efficiency</span>
              <span className="num">{fmtNum(bar.efficiency_ratio)}</span>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
