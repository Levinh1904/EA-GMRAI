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
};

export function bandFill(regime: string): string {
  return REGIME_BAND_FILL[regime] ?? REGIME_BAND_FILL.UNKNOWN;
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
    // Cull: only draw bands intersecting the visible time range.
    let lo = 0;
    let hi = bands.length - 1;
    let first = bands.length;
    while (lo <= hi) {
      const mid = (lo + hi) >> 1;
      if (bands[mid].end >= (range.from as number)) {
        first = mid;
        hi = mid - 1;
      } else {
        lo = mid + 1;
      }
    }
    if (first >= bands.length) return;

    target.useBitmapCoordinateSpace((scope) => {
      const ctx = scope.context;
      const height = scope.mediaSize.height * scope.verticalPixelRatio;
      const hpx = scope.horizontalPixelRatio;
      let top = 0;
      let bottom = height;
      if (prim.area === 'top') bottom = height * 0.55;
      else if (prim.area === 'bottom') top = height * 0.45;

      for (let i = first; i < bands.length; i++) {
        const b = bands[i];
        if (b.start > (range.to as number)) break;
        const x1 = timeScale.timeToCoordinate(b.start as Time);
        const x2 = timeScale.timeToCoordinate(Math.min(b.end + 1, Number(range.to)) as Time);
        if (x1 == null || x2 == null) continue;
        const bx1 = Math.floor(x1 * hpx);
        const bw = Math.max(1, Math.ceil((x2 - x1) * hpx));
        ctx.fillStyle = bandFill(b.regime);
        ctx.fillRect(bx1, top, bw, bottom - top);
      }
    });
  }
}

export class RegimeBandPrimitive implements ISeriesPrimitive<Time> {
  bands: Band[] = [];
  visible = true;
  area: 'full' | 'top' | 'bottom' = 'full';
  timeScale: ReturnType<SeriesAttachedParameter<Time>['chart']['timeScale']> | null = null;
  private requestUpdate: (() => void) | null = null;
  private view: IPrimitivePaneView;

  constructor() {
    this.view = {
      zOrder: () => 'bottom',
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

  setArea(area: 'full' | 'top' | 'bottom'): void {
    this.area = area;
    this.requestUpdate?.();
  }

  paneViews(): readonly IPrimitivePaneView[] {
    return [this.view];
  }
}

// ---------------------------------------------------------------------------
// Crosshair legend (OHLC readout)
// ---------------------------------------------------------------------------

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
