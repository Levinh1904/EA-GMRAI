'use client';

import Link from 'next/link';
import {
  Badge,
  Card,
  EmptyState,
  ErrorState,
  KV,
  Loading,
  Notice,
  PageHeader,
  Stat,
} from '@/components/ui/ui';
import { useApi } from '@/lib/swr';
import { fmtNum, fmtPct, fmtUtcSec } from '@/lib/format';
import type { ModelListResponse, ModelRow, TradeModelStatus } from '@/lib/types';
import styles from '../pages.module.css';

type Walk = {
  passed?: boolean;
  oos_metrics?: {
    n?: number;
    win_rate?: number | null;
    mean_pnl?: number;
    total_pnl?: number;
    profit_factor?: number | null;
    max_drawdown?: number;
    wilson_low?: number | null;
  };
  gate?: Record<string, unknown>;
};

function walkOf(row: ModelRow): Walk {
  return ((row.metrics ?? {}) as { walk_forward?: Walk }).walk_forward ?? {};
}

export default function BacktestingPage() {
  const versions = useApi<ModelListResponse>('/models?model_type=trade_ens&limit=100', {
    refreshInterval: 60000,
  });
  const status = useApi<TradeModelStatus>('/trade-model/status', { refreshInterval: 60000 });

  if (versions.isLoading) return <Loading label="Đang tải backtest TRADE_ENS…" />;
  if (versions.error) return <ErrorState error={versions.error} onRetry={() => versions.mutate()} />;
  if (!versions.data) return <EmptyState title="Không có dữ liệu" />;

  const approved = versions.data.models.find((m) => m.status === 'approved') ?? versions.data.models[0];
  const walk = approved ? walkOf(approved) : {};
  const oos = walk.oos_metrics ?? status.data?.walk_forward?.oos_metrics ?? null;

  return (
    <div className={styles.stack}>
      <PageHeader
        title="Backtest · TRADE_ENS"
        subtitle="Walk-forward OOS của model TRADE_ENS"
        right={<Link href="/models">Kho mô hình →</Link>}
      />

      <Notice tone="warn">
        Đây là kết quả OOS/holdout của model version đã train; không phải live track record.
        Chỉ hiển thị LONG / SHORT / NO_TRADE.
      </Notice>

      <Card
        title="Model"
        subtitle={approved ? `version #${approved.version_id} · v${approved.version} · ${approved.model_type}` : '—'}
        right={approved ? <Badge tone={approved.status === 'approved' ? 'success' : 'neutral'}>{approved.status}</Badge> : undefined}
      >
        {approved && (
          <KV
            items={[
              { label: 'Tạo lúc', value: fmtUtcSec(approved.created_at) },
              { label: 'OOS passed', value: walk.passed ? 'YES' : 'NO' },
              { label: 'OOS lệnh', value: fmtNum(oos?.n, 0) },
              { label: 'OOS win rate', value: fmtPct(oos?.win_rate) },
              { label: 'OOS mean PnL', value: fmtNum(oos?.mean_pnl, 3) },
              { label: 'OOS total PnL', value: fmtNum(oos?.total_pnl, 2) },
              { label: 'Profit factor', value: fmtNum(oos?.profit_factor, 3) },
              { label: 'Max drawdown', value: fmtNum(oos?.max_drawdown, 2) },
            ]}
          />
        )}
      </Card>

      {oos && (
        <Card title="OOS metrics" subtitle="walk-forward 4 fold">
          <div className={`${styles.grid} ${styles.cols4}`}>
            <Stat label="Số lệnh" value={fmtNum(oos.n, 0)} />
            <Stat label="Win rate" value={fmtPct(oos.win_rate)} />
            <Stat label="Mean PnL" value={fmtNum(oos.mean_pnl, 3)} tone={(oos.mean_pnl ?? 0) >= 0 ? 'up' : 'down'} />
            <Stat label="Wilson low" value={fmtPct(oos.wilson_low)} />
          </div>
        </Card>
      )}

      <Card title="Version đã lưu" subtitle="chỉ trade_ens">
        {versions.data.models.length === 0 ? <EmptyState title="Chưa có version" /> : (
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>Version ID</th><th>Version</th><th>Trạng thái</th><th className="num">OOS lệnh</th><th className="num">OOS win</th><th className="num">OOS mean PnL</th></tr></thead>
              <tbody>
                {versions.data.models.map((m) => {
                  const w = walkOf(m).oos_metrics;
                  return (
                    <tr key={m.version_id}>
                      <td className="mono">{m.version_id}</td>
                      <td>v{m.version}</td>
                      <td><Badge tone={m.status === 'approved' ? 'success' : m.status === 'rejected' ? 'danger' : 'neutral'}>{m.status}</Badge></td>
                      <td className="num">{fmtNum(w?.n, 0)}</td>
                      <td className="num">{fmtPct(w?.win_rate)}</td>
                      <td className="num">{fmtNum(w?.mean_pnl, 3)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
