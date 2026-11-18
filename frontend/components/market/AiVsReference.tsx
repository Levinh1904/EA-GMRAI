'use client';

// AI vs Reference mini comparison: agreement rate over the most recent bars
// of the latest done history run, plus a compact agree/disagree bar.

import { Card, EmptyState, ErrorState, Loading, Segmented } from '@/components/ui/ui';
import { fmtNum, fmtPct } from '@/lib/format';
import { AGREEMENT_NEUTRAL_COLOR, DISAGREEMENT_COLOR } from '@/lib/regime';
import { useState } from 'react';
import type { HistoryRegimeBandBar } from '@/lib/types';
import styles from './market.module.css';

const WINDOW_OPTIONS = [
  { value: '100', label: '100 nến' },
  { value: '250', label: '250 nến' },
  { value: '500', label: '500 nến' },
];

export function AiVsReferenceCard({
  bars,
  loading,
  error,
}: {
  bars: HistoryRegimeBandBar[];
  loading: boolean;
  error: unknown;
}) {
  const [window, setWindow] = useState('250');
  const n = parseInt(window, 10) || 250;
  const slice = bars.slice(-n);

  let agree = 0;
  let disagree = 0;
  let compared = 0;
  for (const b of slice) {
    if (b.reference_regime != null && b.regime != null) {
      compared++;
      if (b.reference_regime === b.regime) agree++;
      else disagree++;
    }
  }
  const agreementRate = compared > 0 ? agree / compared : null;

  return (
    <Card
      title="AI so với Reference — cửa sổ gần nhất"
      subtitle="Đồng thuận giữa mô hình AI và động cơ quy tắc reference trên những nến gần đây"
      right={
        <Segmented
          options={WINDOW_OPTIONS}
          value={window}
          onChange={setWindow}
        />
      }
    >
      {loading && !bars.length && <Loading label="Đang tải so sánh AI vs Reference…" />}
      {error != null && !bars.length && <ErrorState error={error} />}
      {!loading && !error && bars.length === 0 && (
        <EmptyState title="Chưa có dữ liệu reference" hint="Chạy run lịch sử có hỗ trợ reference engine." />
      )}
      {slice.length > 0 && (
        <>
          <div className={styles.agreementHead}>
            <span className={styles.agreementValue}>
              {agreementRate != null ? fmtPct(agreementRate, 1) : '—'}
            </span>
            <span className={styles.agreementSub}>
              đồng thuận trên {fmtNum(compared, 0)} nến so sánh được ({fmtNum(slice.length, 0)} nến gần nhất)
            </span>
          </div>
          <div className={styles.agreementBar}>
            <div
              className={styles.agreementFill}
              style={{
                width: compared > 0 ? `${(agree / compared) * 100}%` : '0%',
                background: AGREEMENT_NEUTRAL_COLOR,
              }}
              title={`Đồng thuận: ${agree} nến`}
            />
            <div
              className={styles.agreementFill}
              style={{
                width: compared > 0 ? `${(disagree / compared) * 100}%` : '0%',
                background: DISAGREEMENT_COLOR,
              }}
              title={`Bất đồng: ${disagree} nến`}
            />
          </div>
          <div className={styles.agreementLegend}>
            <span>
              <span className={styles.agreementDot} style={{ background: AGREEMENT_NEUTRAL_COLOR }} />
              Đồng thuận ({agree})
            </span>
            <span>
              <span className={styles.agreementDot} style={{ background: DISAGREEMENT_COLOR }} />
              Bất đồng ({disagree})
            </span>
          </div>
        </>
      )}
    </Card>
  );
}
