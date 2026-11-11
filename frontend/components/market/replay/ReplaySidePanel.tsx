'use client';

// Side panel for the Historical Market Replay: shows ONLY the cursor bar's data.
// For M15 the bar is per-candle; for M5/H1 the AI/reference values come from the
// most recent M15 bar at-or-before the cursor (as-of join, causal).

import { Badge, Card, EmptyState, ProbRow, RegimeBadge, Stat } from '@/components/ui/ui';
import { fmtNum, fmtPrice, fmtPct, fmtUtcSec } from '@/lib/format';
import { regimeColor, regimeLabel } from '@/lib/regime';
import type { Candle, HistoryBar, Timeframe } from '@/lib/types';
import { HMM_STATE_COLORS, type HmmStateLabel } from '@/app/(app)/history/shared';
import styles from './replay.module.css';

function directionalBias(bar: HistoryBar | null): { tone: 'up' | 'down' | 'neutral'; label: string } {
  if (!bar) return { tone: 'neutral', label: '—' };
  const rf = bar.rf_probs;
  const rfScore = rf ? rf.TREND_UP - rf.TREND_DOWN : 0;
  const h1 = bar.h1_trend_context;
  const h1Score = h1 == null ? 0 : Math.max(-1, Math.min(1, h1));
  const combined = 0.6 * rfScore + 0.4 * h1Score;
  if (combined > 0.15) return { tone: 'up', label: 'Thiên hướng tăng' };
  if (combined < -0.15) return { tone: 'down', label: 'Thiên hướng giảm' };
  return { tone: 'neutral', label: 'Trung lập' };
}

export function ReplaySidePanel({
  candle,
  bar,
  prevClose,
  tf,
  hmmStateMap,
  barsLoading,
  hasRun,
}: {
  candle: Candle | null;
  bar: HistoryBar | null;
  prevClose: number | null;
  tf: Timeframe;
  hmmStateMap: Record<string, HmmStateLabel>;
  barsLoading: boolean;
  hasRun: boolean;
}) {
  if (!candle) {
    return (
      <Card title="Nến tại con trỏ" subtitle="Chưa có dữ liệu nến tại thời điểm đã chọn">
        <EmptyState
          title="Chưa có dữ liệu"
          hint="Chọn một thời điểm trong khoảng dữ liệu 1 năm để bắt đầu phát lại."
        />
      </Card>
    );
  }

  const change = prevClose != null ? candle.close - prevClose : null;
  const changePct = change != null && prevClose ? (change / prevClose) * 100 : null;
  const up = candle.close >= candle.open;
  const contextLabel = tf === 'M15' ? null : 'M15 context tại thời điểm đó';
  const bias = directionalBias(bar);

  let agreement: { tone: 'success' | 'danger' | 'neutral'; label: string } = {
    tone: 'neutral',
    label: 'Không đủ dữ liệu',
  };
  if (bar?.regime != null && bar.reference_regime != null) {
    agreement =
      bar.regime === bar.reference_regime
        ? { tone: 'success', label: 'Đồng thuận' }
        : { tone: 'danger', label: 'Bất đồng' };
  }

  return (
    <div className={styles.sidePanel}>
      <Card title="Nến tại con trỏ" subtitle={`${fmtUtcSec(candle.ts)} · ${tf}`}>
        <div className={styles.ohlcRow}>
          <Stat
            label="Mở"
            value={fmtPrice(candle.open)}
            tone={candle.close >= candle.open ? 'up' : 'down'}
          />
          <Stat label="Cao" value={fmtPrice(candle.high)} tone="up" />
          <Stat label="Thấp" value={fmtPrice(candle.low)} tone="down" />
        </div>
        <div className={styles.ohlcRow}>
          <Stat
            label="Đóng"
            value={fmtPrice(candle.close)}
            tone={candle.close >= candle.open ? 'up' : 'down'}
          />
          <Stat
            label="Thay đổi"
            value={change == null ? '—' : `${change >= 0 ? '+' : ''}${fmtPrice(change)}`}
            sub={changePct == null ? undefined : `${fmtPct(changePct / 100, 2)}`}
            tone={up ? 'up' : 'down'}
          />
          <Stat label="Khối lượng" value={fmtNum(candle.tick_volume, 0)} />
        </div>
      </Card>

      {!hasRun && (
        <Card title="Chế độ AI / Reference">
          <EmptyState
            title="Chưa có run lịch sử hoàn tất"
            hint="Cần một history run (M15) hoàn tất để hiển thị chế độ AI theo từng nến."
          />
        </Card>
      )}

      {hasRun && barsLoading && !bar && (
        <Card title="Chế độ AI / Reference">
          <div className={styles.muted}>Đang tải dữ liệu run lịch sử…</div>
        </Card>
      )}

      {hasRun && !barsLoading && (
        <Card
          title="Chế độ AI"
          subtitle={contextLabel ? `${contextLabel} · M15` : 'M15 · theo từng nến'}
        >
          <div className={styles.regimeRow}>
            <RegimeBadge regime={bar?.regime ?? null} large />
            <Stat
              label="Độ tin cậy"
              value={bar?.confidence != null ? fmtPct(bar.confidence) : '—'}
            />
          </div>
          {bar?.reason_codes && bar.reason_codes.length > 0 && (
            <div className={styles.chips}>
              {bar.reason_codes.map((c) => (
                <Badge key={c} tone="neutral" title={c}>
                  {c}
                </Badge>
              ))}
            </div>
          )}
        </Card>
      )}

      {hasRun && !barsLoading && bar?.hmm_posterior && bar.hmm_posterior.length > 0 && (
        <Card title="Hậu nghiệm HMM (5 trạng thái)" subtitle="Xác suất trạng thái ẩn">
          {bar.hmm_posterior.map((p, i) => {
            const label = hmmStateMap[String(i)];
            return (
              <ProbRow
                key={i}
                label={
                  label ? `State ${i} · ${label.regime}` : `State ${i}`
                }
                value={p}
                color={HMM_STATE_COLORS[i % HMM_STATE_COLORS.length]}
              />
            );
          })}
        </Card>
      )}

      {hasRun && !barsLoading && bar?.rf_probs && (
        <Card title="Xác suất Random Forest" subtitle="Thiên hướng từ các lớp">
          <ProbRow label="TREND_UP" value={bar.rf_probs.TREND_UP} color={regimeColor('TREND_UP')} />
          <ProbRow label="SIDEWAYS" value={bar.rf_probs.SIDEWAYS} color={regimeColor('SIDEWAYS')} />
          <ProbRow label="TREND_DOWN" value={bar.rf_probs.TREND_DOWN} color={regimeColor('TREND_DOWN')} />
          <div className={styles.biasRow}>
            <span className={styles.ctxLabel}>Thiên hướng</span>
            <span
              className={styles.biasValue}
              data-tone={bias.tone}
              title="Kết hợp RF (TREND_UP − TREND_DOWN) và dấu của h1_trend_context"
            >
              {bias.label}
            </span>
          </div>
        </Card>
      )}

      {hasRun && !barsLoading && (
        <Card
          title="Reference (bộ phân loại quy tắc)"
          subtitle={contextLabel ? `${contextLabel} · M15` : 'M15 · theo từng nến'}
        >
          <div className={styles.regimeRow}>
            <RegimeBadge regime={bar?.reference_regime ?? null} large />
            <Badge tone={agreement.tone} title="AI so với Reference">
              {agreement.label}
            </Badge>
          </div>
          <div className={styles.kv}>
            <div className={styles.kvItem}>
              <span className={styles.kvLabel}>Quy tắc kích hoạt</span>
              <span className={styles.kvValue}>
                {bar?.reference_reason ? (
                  <code className={styles.code}>{bar.reference_reason}</code>
                ) : (
                  '—'
                )}
              </span>
            </div>
            {bar && (
              <>
                <div className={styles.kvItem}>
                  <span className={styles.kvLabel}>ADX (chuẩn hóa)</span>
                  <span className={styles.kvValue}>{fmtNum(bar.adx_norm, 3)}</span>
                </div>
                <div className={styles.kvItem}>
                  <span className={styles.kvLabel}>ATR ratio</span>
                  <span className={styles.kvValue}>{fmtNum(bar.atr_ratio, 3)}</span>
                </div>
                <div className={styles.kvItem}>
                  <span className={styles.kvLabel}>Efficiency</span>
                  <span className={styles.kvValue}>{fmtNum(bar.efficiency_ratio, 3)}</span>
                </div>
                <div className={styles.kvItem}>
                  <span className={styles.kvLabel}>Bối cảnh H1</span>
                  <span className={styles.kvValue}>{fmtNum(bar.h1_trend_context, 3)}</span>
                </div>
              </>
            )}
          </div>
        </Card>
      )}

      {hasRun && !barsLoading && (
        <div className={styles.disclaimer}>
          Chế độ AI/Reference là đầu ra của mô hình tại thời điểm con trỏ — không phải lệnh giao
          dịch. Múi giờ hiển thị: UTC.
        </div>
      )}
    </div>
  );
}
