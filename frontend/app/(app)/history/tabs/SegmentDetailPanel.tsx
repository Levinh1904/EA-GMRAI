'use client';

import { Badge, Card, EmptyState, KV, Notice, ProbRow, RegimeBadge } from '@/components/ui/ui';
import { fmtNum, fmtPrice } from '@/lib/format';
import type { HistorySegment } from '@/lib/types';
import { HMM_STATE_COLORS, fmtMinHours, fmtTs, signedUsd, type HmmStateLabel } from '../shared';

export function SegmentDetailPanel({
  segment,
  hmmStateMap,
  onClose,
}: {
  segment: HistorySegment | null;
  hmmStateMap: Record<string, HmmStateLabel>;
  onClose?: () => void;
}) {
  if (!segment) {
    return (
      <Card title="Chi tiết segment">
        <EmptyState title="Chưa chọn segment" hint="Bấm vào dải regime trên biểu đồ hoặc một dòng trong bảng để xem chi tiết." />
      </Card>
    );
  }

  const rangeUsd = segment.high_price - segment.low_price;
  const rangePct = segment.start_price ? (rangeUsd / segment.start_price) * 100 : null;
  const hmmProbs = segment.hmm_probs ?? {};

  return (
    <Card
      title={
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 10 }}>
          <RegimeBadge regime={segment.regime} />
          <span>
            Segment #{segment.segment_index}{' '}
            <span style={{ color: 'var(--text-faint)', fontWeight: 400 }}>(id {segment.id})</span>
          </span>
        </span>
      }
      subtitle={segment.model_version_id != null ? `Phiên bản mô hình: ${segment.model_version_id}` : undefined}
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
      tone={segment.split_reason ? 'warn' : 'default'}
    >
      {segment.split_reason && (
        <Notice tone="warn">
          Lý do tách segment: <code>{segment.split_reason}</code> — có khoảng trống dữ liệu giữa các
          cây nến (data gap). Khoảng trống này có thể làm sai lệch thống kê giá của segment.
        </Notice>
      )}
      <KV
        items={[
          { label: 'Bắt đầu (UTC)', value: fmtTs(segment.start_ts) },
          { label: 'Kết thúc (UTC)', value: fmtTs(segment.end_ts) },
          { label: 'Thời lượng', value: fmtMinHours(segment.duration_minutes) },
          { label: 'Số nến', value: `${fmtNum(segment.bar_count, 0)} nến M15` },
          { label: 'Giá mở cửa', value: fmtPrice(segment.start_price) },
          { label: 'Giá đóng cửa', value: fmtPrice(segment.end_price) },
          { label: 'Giá cao nhất', value: fmtPrice(segment.high_price) },
          { label: 'Giá thấp nhất', value: fmtPrice(segment.low_price) },
          {
            label: 'Thay đổi ròng',
            value: (
              <span style={{ color: segment.net_change >= 0 ? 'var(--green)' : 'var(--red)' }}>
                {signedUsd(segment.net_change)}
              </span>
            ),
          },
          { label: 'MFE (lợi nhuận tối đa)', value: signedUsd(segment.mfe) },
          { label: 'MAE (bất lợi tối đa)', value: signedUsd(segment.mae) },
          { label: 'Biến động USD (cao − thấp)', value: fmtPrice(rangeUsd) },
          {
            label: 'Biến động % (so với giá mở)',
            value: rangePct != null ? `${rangePct.toFixed(2)}%` : '—',
          },
          { label: 'ATR trung bình', value: fmtNum(segment.atr_mean, 3) },
          { label: 'ADX trung bình (chuẩn hóa)', value: fmtNum(segment.adx_mean, 3) },
          { label: 'Efficiency trung bình', value: fmtNum(segment.efficiency_mean, 3) },
          { label: 'Độ tin cậy trung bình', value: `${fmtNum(segment.confidence_mean * 100, 1)}%` },
          { label: 'Chạm cận trên (high)', value: `${segment.range_touches_high} lần` },
          { label: 'Chạm cận dưới (low)', value: `${segment.range_touches_low} lần` },
        ]}
      />

      <h3 style={{ marginTop: 14 }}>Xác suất hậu nghiệm HMM (5 trạng thái)</h3>
      {Object.keys(hmmProbs).length === 0 ? (
        <div className="mono" style={{ color: 'var(--text-faint)', fontSize: 12 }}>
          Không có dữ liệu posterior
        </div>
      ) : (
        Object.keys(hmmProbs)
          .sort((a, b) => Number(a) - Number(b))
          .map((stateKey) => {
            const label = hmmStateMap[stateKey];
            return (
              <ProbRow
                key={stateKey}
                label={
                  label
                    ? `State ${stateKey} · ${label.regime}${label.reason ? ` (${label.reason})` : ''}`
                    : `State ${stateKey}`
                }
                value={hmmProbs[stateKey]}
                color={HMM_STATE_COLORS[Number(stateKey) % HMM_STATE_COLORS.length]}
              />
            );
          })
      )}
      <div style={{ marginTop: 10, fontSize: 12, color: 'var(--text-faint)' }}>
        Nhãn trạng thái HMM lấy từ state_mapping của mô hình v{segment.model_version_id ?? '—'}.
        Regime vận hành của segment được quyết định bởi tổ hợp HMM + RF.
      </div>
      {segment.model_version_id == null && (
        <div style={{ marginTop: 6 }}>
          <Badge tone="warning">Chưa ghi nhận phiên bản mô hình</Badge>
        </div>
      )}
    </Card>
  );
}
