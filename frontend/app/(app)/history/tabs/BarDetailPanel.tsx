'use client';

import { Badge, Card, EmptyState, KV, ProbRow, RegimeBadge } from '@/components/ui/ui';
import { fmtNum, fmtPrice, fmtUtcSec } from '@/lib/format';
import { permissionLabel, reasonCodeLabel, regimeColor } from '@/lib/regime';
import type { HistoryBar, HistoryRun } from '@/lib/types';
import { HMM_STATE_COLORS, type HmmStateLabel } from '../shared';

function pct(v: number | null | undefined, digits = 1): string {
  return v == null || Number.isNaN(v) ? '—' : `${(v * 100).toFixed(digits)}%`;
}

export function BarDetailPanel({
  bar,
  hmmStateMap,
  run,
  referenceVersion,
  onClose,
}: {
  bar: HistoryBar | null;
  hmmStateMap: Record<string, HmmStateLabel>;
  run: HistoryRun;
  referenceVersion: string | null;
  onClose?: () => void;
}) {
  if (!bar) {
    return (
      <Card title="Chi tiết thanh nến" subtitle="Bấm vào một cây nến trên biểu đồ timeline để xem chi tiết thanh nến đó">
        <EmptyState
          title="Chưa chọn thanh nến"
          hint="Bấm trực tiếp vào cây nến (không phải dải regime) để xem OHLC, dự đoán AI (HMM + RF) và phân loại Reference cùng các chỉ báo quy tắc."
        />
      </Card>
    );
  }

  const refRange = bar.ref_channel_high != null && bar.ref_channel_low != null ? bar.ref_channel_high - bar.ref_channel_low : null;
  const rf = bar.rf_probs;
  const posterior = bar.hmm_posterior;

  return (
    <Card
      title={
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 10 }}>
          <RegimeBadge regime={bar.regime} />
          <span>
            Thanh nến{' '}
            <span style={{ color: 'var(--text-faint)', fontWeight: 400 }}>{fmtUtcSec(bar.ts)}</span>
          </span>
        </span>
      }
      subtitle={`M15 · Run #${run.id} · ${run.symbol}`}
      right={
        onClose ? (
          <button
            type="button"
            onClick={onClose}
            style={{
              padding: '4px 10px',
              fontSize: 12,
              background: 'var(--panel-2)',
              border: '1px solid var(--border)',
              borderRadius: 6,
              color: 'var(--text)',
              cursor: 'pointer',
            }}
          >
            Đóng
          </button>
        ) : undefined
      }
    >
      <h3 style={{ marginBottom: 8 }}>Giá (OHLC)</h3>
      <KV
        columns={2}
        items={[
          { label: 'Mở', value: fmtPrice(bar.open) },
          { label: 'Cao', value: fmtPrice(bar.high) },
          { label: 'Thấp', value: fmtPrice(bar.low) },
          {
            label: 'Đóng',
            value: (
              <span style={{ color: bar.close >= bar.open ? 'var(--green)' : 'var(--red)' }}>
                {fmtPrice(bar.close)}
              </span>
            ),
          },
          { label: 'Biên độ (cao − thấp)', value: fmtPrice(bar.high - bar.low) },
          {
            label: 'Thay đổi (đóng − mở)',
            value: (
              <span style={{ color: bar.close >= bar.open ? 'var(--green)' : 'var(--red)' }}>
                {bar.close - bar.open >= 0 ? '+' : ''}
                {fmtPrice(bar.close - bar.open)}
              </span>
            ),
          },
        ]}
      />

      <h3 style={{ marginTop: 14 }}>Dự đoán AI (HMM + RF)</h3>
      <KV
        columns={2}
        items={[
          { label: 'Regime AI', value: <RegimeBadge regime={bar.regime} /> },
          { label: 'Độ tin cậy', value: pct(bar.confidence) },
          { label: 'Quyền giao dịch', value: permissionLabel(bar.permission) },
          {
            label: 'HMM state',
            value: bar.hmm_state != null ? String(bar.hmm_state) : '—',
          },
        ]}
      />
      {bar.reason_codes && bar.reason_codes.length > 0 && (
        <div style={{ marginTop: 8, display: 'flex', flexWrap: 'wrap', gap: 6 }}>
          {bar.reason_codes.map((c) => (
            <Badge key={c} tone="neutral" title={c}>
              {reasonCodeLabel(c)}
            </Badge>
          ))}
        </div>
      )}

      {posterior && posterior.length > 0 && (
        <>
          <h4 style={{ marginTop: 12, fontSize: 12, color: 'var(--text-muted)' }}>
            Xác suất hậu nghiệm HMM (5 trạng thái)
          </h4>
          {posterior.map((p, i) => {
            const label = hmmStateMap[String(i)];
            return (
              <ProbRow
                key={i}
                label={
                  label
                    ? `State ${i} · ${label.regime}${label.reason ? ` (${label.reason})` : ''}`
                    : `State ${i}`
                }
                value={p}
                color={HMM_STATE_COLORS[i % HMM_STATE_COLORS.length]}
              />
            );
          })}
        </>
      )}

      {rf && (
        <>
          <h4 style={{ marginTop: 12, fontSize: 12, color: 'var(--text-muted)' }}>
            Xác suất Random Forest
          </h4>
          <ProbRow label="TREND_UP" value={rf.TREND_UP} color={regimeColor('TREND_UP')} />
          <ProbRow label="SIDEWAYS" value={rf.SIDEWAYS} color={regimeColor('SIDEWAYS')} />
          <ProbRow label="TREND_DOWN" value={rf.TREND_DOWN} color={regimeColor('TREND_DOWN')} />
        </>
      )}

      <h3 style={{ marginTop: 16 }}>Reference (bộ phân loại quy tắc độc lập)</h3>
      <KV
        columns={2}
        items={[
          { label: 'Regime Reference', value: <RegimeBadge regime={bar.reference_regime} /> },
          {
            label: 'Quy tắc kích hoạt',
            value: bar.reference_reason ? (
              <code className="mono" style={{ fontSize: 11 }}>
                {bar.reference_reason}
              </code>
            ) : (
              '—'
            ),
          },
          { label: 'DI gap (D+ − D−)', value: fmtNum(bar.di_gap, 3) },
          { label: 'Độ dốc EMA', value: fmtNum(bar.ema_slope, 3) },
          { label: 'Kênh cao (channel high)', value: fmtPrice(bar.ref_channel_high) },
          { label: 'Kênh thấp (channel low)', value: fmtPrice(bar.ref_channel_low) },
          { label: 'Độ rộng kênh', value: refRange != null ? fmtPrice(refRange) : '—' },
          { label: 'Displacement (ATR)', value: fmtNum(bar.ref_displacement, 3) },
          { label: 'ADX (chuẩn hóa)', value: fmtNum(bar.adx_norm, 3) },
          { label: 'ATR ratio', value: fmtNum(bar.atr_ratio, 3) },
          { label: 'Efficiency ratio', value: fmtNum(bar.efficiency_ratio, 3) },
          { label: 'Bối cảnh H1', value: fmtNum(bar.h1_trend_context, 3) },
          { label: 'Động lượng M5', value: fmtNum(bar.m5_momentum, 3) },
        ]}
      />
      {bar.reference_regime != null && bar.regime != null && bar.reference_regime !== bar.regime && (
        <div style={{ marginTop: 8 }}>
          <Badge tone="danger">Bất đồng: AI = {bar.regime} · Reference = {bar.reference_regime}</Badge>
        </div>
      )}
      {bar.reference_regime != null && bar.regime != null && bar.reference_regime === bar.regime && (
        <div style={{ marginTop: 8 }}>
          <Badge tone="success">Đồng thuận: AI = Reference = {bar.regime}</Badge>
        </div>
      )}

      <div style={{ marginTop: 14, fontSize: 12, color: 'var(--text-faint)' }}>
        Phiên bản mô hình: HMM v{run.hmm_model_version_id ?? '—'} · RF v{run.rf_model_version_id ?? '—'} ·
        Reference {referenceVersion ?? '—'}. Reference là bộ phân loại quy tắc độc lập (ngưỡng nghiên
        cứu, có version) — dùng để so sánh, không phải ground truth.
      </div>
    </Card>
  );
}
