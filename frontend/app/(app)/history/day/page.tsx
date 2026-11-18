'use client';

import { useMemo, useState } from 'react';
import Link from 'next/link';
import {
  Badge,
  Card,
  EmptyState,
  ErrorState,
  Loading,
  Notice,
  PageHeader,
  Stat,
} from '@/components/ui/ui';
import { useApi } from '@/lib/swr';
import { fmtNum, fmtUtcSec } from '@/lib/format';
import type { TradeHistory } from '@/lib/types';
import styles from '../../pages.module.css';

export default function HistoryDayPage() {
  const { data, error, isLoading, mutate } = useApi<TradeHistory>('/trade-model/history?limit=5000', {
    refreshInterval: 60000,
  });
  const [date, setDate] = useState('');

  const currentDate = date || data?.bars[data.bars.length - 1]?.ts.slice(0, 10) || '';
  const bars = useMemo(
    () => (data?.bars ?? []).filter((b) => b.ts.slice(0, 10) === currentDate),
    [data, currentDate]
  );
  const trades = useMemo(
    () => (data?.trades ?? []).filter((t) => t.entry_ts.slice(0, 10) === currentDate),
    [data, currentDate]
  );
  const days = useMemo(() => {
    const set = new Set((data?.bars ?? []).map((b) => b.ts.slice(0, 10)));
    return Array.from(set).sort().reverse();
  }, [data]);
  const counts = bars.reduce<Record<string, number>>(
    (acc, b) => ({ ...acc, [b.signal]: (acc[b.signal] ?? 0) + 1 }),
    { LONG: 0, SHORT: 0, NO_TRADE: 0 }
  );
  const pnl = trades.reduce((sum, t) => sum + t.pnl, 0);

  if (isLoading) return <Loading label="Đang tải lịch sử theo ngày…" />;
  if (error) return <ErrorState error={error} onRetry={() => mutate()} />;
  if (!data) return <EmptyState title="Không có lịch sử" />;

  return (
    <div className={styles.stack}>
      <PageHeader
        title="Lịch sử theo ngày · TRADE_ENS"
        subtitle="Chỉ LONG / SHORT / NO_TRADE"
      />

      <Card title="Chọn ngày" subtitle="UTC">
        <div className={styles.toolbar}>
          <select
            value={currentDate}
            onChange={(e) => setDate(e.target.value)}
            style={{ background: 'var(--bg-elev)', border: '1px solid var(--border)', borderRadius: 8, color: 'var(--text)', padding: '6px 10px' }}
          >
            {days.map((d) => (
              <option key={d} value={d}>{d}</option>
            ))}
          </select>
          <Link href="/history">← Lịch sử tổng</Link>
        </div>
      </Card>

      <div className={`${styles.grid} ${styles.cols4}`}>
        <Stat label="Tín hiệu LONG" value={fmtNum(counts.LONG ?? 0, 0)} />
        <Stat label="Tín hiệu SHORT" value={fmtNum(counts.SHORT ?? 0, 0)} />
        <Stat label="NO_TRADE" value={fmtNum(counts.NO_TRADE ?? 0, 0)} />
        <Stat label="PnL lệnh trong ngày" value={fmtNum(pnl, 2)} tone={pnl >= 0 ? 'up' : 'down'} />
      </div>

      <Card title={`Nến ngày ${currentDate}`} subtitle={`${bars.length} nến M15`}>
        {bars.length === 0 ? <EmptyState title="Không có nến" /> : (
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>Thời gian</th><th className="num">Close</th><th className="num">p(LONG)</th><th className="num">p(SHORT)</th><th>Tín hiệu</th></tr></thead>
              <tbody>
                {bars.slice(-96).reverse().map((b) => (
                  <tr key={b.ts}>
                    <td className="mono">{fmtUtcSec(b.ts)}</td>
                    <td className="num">{fmtNum(b.close, 2)}</td>
                    <td className="num">{fmtNum(b.p_long, 4)}</td>
                    <td className="num">{fmtNum(b.p_short, 4)}</td>
                    <td><Badge tone={b.signal === 'LONG' ? 'teal' : b.signal === 'SHORT' ? 'danger' : 'neutral'}>{b.signal}</Badge></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card title={`Lệnh ngày ${currentDate}`} subtitle={`${trades.length} lệnh`}>
        {trades.length === 0 ? <EmptyState title="Không có lệnh" /> : (
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>Hướng</th><th>Entry</th><th className="num">PnL</th><th>Lý do</th></tr></thead>
              <tbody>
                {trades.map((t, i) => (
                  <tr key={`${t.entry_ts}-${i}`}>
                    <td><Badge tone={t.direction === 'LONG' ? 'teal' : 'danger'}>{t.direction}</Badge></td>
                    <td className="mono">{fmtUtcSec(t.entry_ts)}</td>
                    <td className="num">{fmtNum(t.pnl, 3)}</td>
                    <td>{t.exit_reason ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Notice tone="info">In-sample replay; không phải live track record.</Notice>
    </div>
  );
}
