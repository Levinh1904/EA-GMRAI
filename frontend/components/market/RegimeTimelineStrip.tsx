'use client';

// Bottom regime timeline strip: the most recent bars of the latest done
// history run, colored by AI regime (or reference). Clicking a cell focuses
// the main chart on that point in time.

import { Card, EmptyState, ErrorState, Loading } from '@/components/ui/ui';
import { fmtUtc } from '@/lib/format';
import { regimeColor, regimeLabel } from '@/lib/regime';
import type { HistoryRegimeBandBar } from '@/lib/types';
import styles from './market.module.css';

export function RegimeTimelineStrip({
  bars,
  loading,
  error,
  mode,
  onFocus,
  count = 240,
}: {
  bars: HistoryRegimeBandBar[];
  loading: boolean;
  error: unknown;
  mode: 'ai' | 'reference';
  onFocus: (ts: string) => void;
  count?: number;
}) {
  const window = bars.slice(-count);
  const label = mode === 'ai' ? 'AI' : 'Reference';

  return (
    <Card
      title={`Timeline regime gần đây — ${label}`}
      subtitle={`${window.length} nến cuối của run lịch sử mới nhất · bấm để xem vị trí trên biểu đồ`}
    >
      {loading && !bars.length && <Loading label="Đang tải timeline regime…" />}
      {error != null && !bars.length && <ErrorState error={error} />}
      {!loading && !error && bars.length === 0 && (
        <EmptyState title="Chưa có dữ liệu run lịch sử" />
      )}
      {window.length > 0 && (
        <>
          <div className={styles.strip}>
            {window.map((b) => {
              const regime = mode === 'ai' ? (b.regime ?? 'UNKNOWN') : (b.reference_regime ?? 'UNKNOWN');
              return (
                <button
                  key={b.ts}
                  type="button"
                  className={styles.stripCell}
                  style={{ background: regimeColor(regime) }}
                  title={`${fmtUtc(b.ts)} · ${regimeLabel(regime)}${b.confidence != null ? ` · conf ${(b.confidence * 100).toFixed(0)}%` : ''}`}
                  onClick={() => onFocus(b.ts)}
                  aria-label={`${fmtUtc(b.ts)} · ${regimeLabel(regime)}`}
                />
              );
            })}
          </div>
          <div className={styles.stripAxis}>
            <span>{fmtUtc(window[0].ts)}</span>
            <span>{fmtUtc(window[window.length - 1].ts)}</span>
          </div>
        </>
      )}
    </Card>
  );
}
