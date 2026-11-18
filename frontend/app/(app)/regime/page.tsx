'use client';

import Link from 'next/link';
import {
  Badge,
  Card,
  ErrorState,
  KV,
  Loading,
  Notice,
  PageHeader,
  Stat,
} from '@/components/ui/ui';
import { useApi } from '@/lib/swr';
import { fmtNum, fmtPct, fmtPrice, fmtUtcSec } from '@/lib/format';
import type { TradeDeployability, TradeSignal } from '@/lib/types';
import styles from '../pages.module.css';

export default function RegimePage() {
  const signal = useApi<TradeSignal>('/trade-model/signal', { refreshInterval: 15000 });
  const deploy = useApi<TradeDeployability>('/trade-model/deployability', {
    refreshInterval: 60000,
  });

  if (signal.isLoading) return <Loading label="Đang tải TRADE_ENS…" />;
  if (signal.error) return <ErrorState error={signal.error} onRetry={() => signal.mutate()} />;

  const s = signal.data;
  const tone = s?.signal === 'LONG' ? 'teal' : s?.signal === 'SHORT' ? 'danger' : 'neutral';

  return (
    <div className={styles.stack}>
      <PageHeader
        title="TRADE_ENS"
        subtitle="XAUUSD M15 · LONG / SHORT / NO_TRADE"
      />

      <Card
        title="Tín hiệu hiện tại"
        subtitle={s?.model_name ?? 'trade_ens'}
        right={<Badge tone={tone}>{s?.signal ?? 'NO_TRADE'}</Badge>}
      >
        {s ? (
          <>
            <div className={`${styles.grid} ${styles.cols4}`}>
              <Stat label="p(LONG)" value={fmtNum(s.p_long, 4)} />
              <Stat label="p(SHORT)" value={fmtNum(s.p_short, 4)} />
              <Stat label="Threshold SHORT" value={fmtNum(s.thresholds?.SHORT ?? s.threshold, 4)} />
              <Stat label="Tradeable" value={s.tradeable ? 'YES' : 'NO'} tone={s.tradeable ? 'up' : 'warn'} />
            </div>
            <KV
              items={[
                { label: 'Giá', value: `${fmtPrice(s.price)} USD` },
                { label: 'Entry tham chiếu', value: `${fmtPrice(s.entry_price)} USD` },
                { label: 'TP', value: s.tp_price == null ? '—' : `${fmtPrice(s.tp_price)} USD` },
                { label: 'SL', value: s.sl_price == null ? '—' : `${fmtPrice(s.sl_price)} USD` },
                { label: 'Allowed sides', value: (s.allowed_sides ?? []).join(', ') || '—' },
                { label: 'Bar M15', value: fmtUtcSec(s.bar_ts) },
                { label: 'Tuổi dữ liệu', value: `${fmtNum(s.data_age_seconds / 60, 1)} phút` },
                { label: 'Stale', value: s.stale ? 'YES' : 'NO' },
              ]}
            />
            <Notice tone="info">
              Đây là output duy nhất của model: <strong>{s.signal}</strong>.
            </Notice>
          </>
        ) : (
          <Notice tone="warn">Chưa có tín hiệu trade_ens.</Notice>
        )}
        <div className={styles.chips} style={{ marginTop: 12 }}>
          <Link href="/signals">Chi tiết model</Link>
          <Link href="/history">Lịch sử tín hiệu</Link>
          {deploy.data && (
            <Badge tone={deploy.data.live_ready ? 'success' : 'warning'}>
              live_ready: {deploy.data.live_ready ? 'true' : 'false'}
            </Badge>
          )}
        </div>
      </Card>

      {deploy.data && (
        <Card title="Deployment" subtitle="model gate + dữ liệu">
          <KV
            items={[
              { label: 'Demo ready', value: deploy.data.demo_ready ? 'YES' : 'NO' },
              { label: 'Live ready', value: deploy.data.live_ready ? 'YES' : 'NO' },
              { label: 'Data fresh', value: deploy.data.data_fresh ? 'YES' : 'NO' },
              { label: 'Bar cuối', value: fmtUtcSec(deploy.data.latest_bar_ts) },
              { label: 'Blockers', value: deploy.data.blockers.join(', ') || '—' },
              { label: 'Warnings', value: deploy.data.warnings.join(', ') || '—' },
            ]}
          />
        </Card>
      )}
    </div>
  );
}
