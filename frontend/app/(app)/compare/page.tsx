'use client';

import Link from 'next/link';
import { Badge, Card, EmptyState, ErrorState, Loading, PageHeader, Stat } from '@/components/ui/ui';
import { useApi } from '@/lib/swr';
import { fmtNum, fmtPct, fmtUtcSec } from '@/lib/format';
import type { ModelListResponse, ModelRow } from '@/lib/types';
import styles from '../pages.module.css';

type Oos = { n?: number; win_rate?: number | null; mean_pnl?: number; profit_factor?: number | null; total_pnl?: number };

function oosOf(row: ModelRow): Oos {
  return (((row.metrics ?? {}) as { walk_forward?: { oos_metrics?: Oos } }).walk_forward?.oos_metrics) ?? {};
}

export default function ComparePage() {
  const { data, error, isLoading, mutate } = useApi<ModelListResponse>('/models?model_type=trade_ens&limit=100', {
    refreshInterval: 60000,
  });

  if (isLoading) return <Loading label="Đang tải các version TRADE_ENS…" />;
  if (error) return <ErrorState error={error} onRetry={() => mutate()} />;

  return (
    <div className={styles.stack}>
      <PageHeader
        title="So sánh version · TRADE_ENS"
        subtitle="So sánh các version TRADE_ENS"
        right={<Link href="/backtesting">Backtest →</Link>}
      />

      {!data || data.models.length === 0 ? (
        <EmptyState title="Chưa có version trade_ens" />
      ) : (
        <div className={styles.stack}>
          {data.models.map((m) => {
            const oos = oosOf(m);
            return (
              <Card
                key={m.version_id}
                title={`Version #${m.version_id} · v${m.version}`}
                subtitle={`${m.model_type} · ${fmtUtcSec(m.created_at)}`}
                right={<Badge tone={m.status === 'approved' ? 'success' : 'neutral'}>{m.status}</Badge>}
              >
                <div className={`${styles.grid} ${styles.cols4}`}>
                  <Stat label="OOS lệnh" value={fmtNum(oos.n, 0)} />
                  <Stat label="Win rate" value={fmtPct(oos.win_rate)} />
                  <Stat label="Mean PnL" value={fmtNum(oos.mean_pnl, 3)} tone={(oos.mean_pnl ?? 0) >= 0 ? 'up' : 'down'} />
                  <Stat label="Profit factor" value={fmtNum(oos.profit_factor, 3)} />
                </div>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
