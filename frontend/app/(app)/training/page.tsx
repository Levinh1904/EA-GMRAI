'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useAuth } from '@/components/AuthProvider';
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorState,
  KV,
  Loading,
  Notice,
  PageHeader,
} from '@/components/ui/ui';
import { ApiError, api } from '@/lib/api';
import { useApi } from '@/lib/swr';
import { fmtNum, fmtUtcSec } from '@/lib/format';
import type { TradeModelStatus } from '@/lib/types';
import styles from '../pages.module.css';

export default function TrainingPage() {
  const { isAdmin } = useAuth();
  const status = useApi<TradeModelStatus>('/trade-model/status', { refreshInterval: 30000 });
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ tone: 'info' | 'danger'; text: string } | null>(null);

  async function train() {
    setBusy(true);
    setMsg(null);
    try {
      const res = await api.startTradeModelTraining();
      setMsg({ tone: 'info', text: `Đã xếp lịch training trade_ens: run #${res.run_id}, job #${res.job_id}.` });
      await status.mutate();
    } catch (e) {
      setMsg({ tone: 'danger', text: e instanceof ApiError ? e.message : 'Không thể bắt đầu training' });
    } finally {
      setBusy(false);
    }
  }

  if (status.isLoading) return <Loading label="Đang tải trạng thái model…" />;
  if (status.error) return <ErrorState error={status.error} onRetry={() => status.mutate()} />;

  const s = status.data;

  return (
    <div className={styles.stack}>
      <PageHeader
        title="Training · TRADE_ENS"
        subtitle="Huấn luyện model TRADE_ENS"
        right={<Link href="/backtesting">Backtest →</Link>}
      />

      {msg && <Notice tone={msg.tone}>{msg.text}</Notice>}

      <Card
        title="Model hiện tại"
        right={<Badge tone={s?.approved ? 'success' : 'warning'}>{s?.approved ? 'approved' : 'no model'}</Badge>}
      >
        {!s?.approved ? (
          <EmptyState title="Chưa có model approved" hint="Bấm Train để huấn luyện trade_ens." />
        ) : (
          <KV
            items={[
              { label: 'Version ID', value: s.model_version_id },
              { label: 'Version', value: `v${s.version}` },
              { label: 'Allowed sides', value: (s.allowed_sides ?? []).join(', ') || '—' },
              { label: 'Threshold SHORT', value: fmtNum(s.thresholds?.SHORT ?? s.threshold, 6) },
              { label: 'Trained until', value: fmtUtcSec(s.trained_until) },
              { label: 'OOS lệnh', value: fmtNum(s.walk_forward?.oos_metrics?.n, 0) },
              { label: 'OOS mean PnL', value: fmtNum(s.walk_forward?.oos_metrics?.mean_pnl, 3) },
              { label: 'OOS PF', value: fmtNum(s.walk_forward?.oos_metrics?.profit_factor, 3) },
            ]}
          />
        )}
        <div className={styles.formActions} style={{ marginTop: 14 }}>
          <Button variant="primary" onClick={train} disabled={!isAdmin || busy}>
            {busy ? 'Đang xếp lịch…' : 'Train trade_ens'}
          </Button>
          {!isAdmin && <Notice tone="warn">Cần quyền admin để train.</Notice>}
        </div>
      </Card>

      <Notice tone="info">
        Training dùng feature schema v2 và gate lợi nhuận OOS.
      </Notice>
    </div>
  );
}
