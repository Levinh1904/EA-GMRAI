'use client';

import { useMemo } from 'react';
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
import { fmtNum, fmtPct, fmtPrice } from '@/lib/format';
import type { TradeHistory, TradeHistoryTrade, TradeMetrics } from '@/lib/types';
import styles from '../../pages.module.css';

type Bucket = { n: number; wins: number; pnl: number };
type Row = [string, Bucket];

function bucketRows(trades: TradeHistoryTrade[], keyFn: (t: TradeHistoryTrade) => string): Row[] {
  const map = new Map<string, Bucket>();
  for (const t of trades) {
    const key = keyFn(t);
    const b = map.get(key) ?? { n: 0, wins: 0, pnl: 0 };
    b.n += 1;
    b.wins += t.pnl > 0 ? 1 : 0;
    b.pnl += t.pnl;
    map.set(key, b);
  }
  return Array.from(map.entries()).sort((a, b) => a[0].localeCompare(b[0]));
}

function Table({ rows, firstLabel }: { rows: Row[]; firstLabel: string }) {
  if (rows.length === 0) return <EmptyState title="Không có dữ liệu" />;
  return (
    <div className="table-wrap">
      <table className="table">
        <thead>
          <tr>
            <th>{firstLabel}</th>
            <th className="num">Lệnh</th>
            <th className="num">Win rate</th>
            <th className="num">Mean PnL</th>
            <th className="num">Total PnL</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(([key, b]) => (
            <tr key={key}>
              <td>{key}</td>
              <td className="num">{fmtNum(b.n, 0)}</td>
              <td className="num">{fmtPct(b.n ? b.wins / b.n : null)}</td>
              <td className="num">{fmtNum(b.n ? b.pnl / b.n : null, 3)}</td>
              <td className="num">{fmtNum(b.pnl, 2)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Equity({ points }: { points: number[] }) {
  if (points.length < 2) return <EmptyState title="Không có equity curve" />;
  const width = 900;
  const height = 220;
  const min = Math.min(...points, 0);
  const max = Math.max(...points, 0);
  const span = max - min || 1;
  const step = Math.max(1, Math.ceil(points.length / 300));
  const sampled = points.filter((_, i) => i % step === 0 || i === points.length - 1);
  const path = sampled
    .map((v, i) => {
      const x = (i / Math.max(1, sampled.length - 1)) * width;
      const y = height - ((v - min) / span) * height;
      return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(' ');
  const zeroY = height - ((0 - min) / span) * height;
  return (
    <svg viewBox={`0 0 ${width} ${height}`} width="100%" height={height} role="img" aria-label="Equity curve">
      <line x1="0" x2={width} y1={zeroY} y2={zeroY} stroke="var(--border)" strokeDasharray="4 4" />
      <path d={path} fill="none" stroke="var(--accent, #4c8dff)" strokeWidth="2" />
    </svg>
  );
}

function Metrics({ m }: { m: TradeMetrics }) {
  return (
    <div className={`${styles.grid} ${styles.cols4}`}>
      <Stat label="Lệnh" value={fmtNum(m.n, 0)} />
      <Stat label="Win rate" value={fmtPct(m.win_rate)} />
      <Stat label="Mean PnL" value={fmtNum(m.mean_pnl, 3)} tone={m.mean_pnl >= 0 ? 'up' : 'down'} />
      <Stat label="Total PnL" value={fmtNum(m.total_pnl, 2)} tone={m.total_pnl >= 0 ? 'up' : 'down'} />
      <Stat label="Profit factor" value={fmtNum(m.profit_factor, 3)} />
      <Stat label="Max drawdown" value={fmtNum(m.max_drawdown, 2)} />
      <Stat label="Avg win" value={fmtNum(m.avg_win, 3)} />
      <Stat label="Breakeven" value={fmtPct(m.breakeven_win_rate)} />
    </div>
  );
}

export default function HistoryStatsPage() {
  const { data, error, isLoading, mutate } = useApi<TradeHistory>('/trade-model/history?limit=5000', {
    refreshInterval: 60000,
  });

  const groups = useMemo(() => {
    const trades = data?.trades ?? [];
    return {
      direction: bucketRows(trades, (t) => t.direction),
      hour: bucketRows(trades, (t) => `${new Date(t.entry_ts).getUTCHours().toString().padStart(2, '0')}:00 UTC`),
      weekday: bucketRows(trades, (t) => {
        const d = new Date(t.entry_ts).getUTCDay();
        return ['CN', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7'][d];
      }),
      month: bucketRows(trades, (t) => t.entry_ts.slice(0, 7)),
      exit: bucketRows(trades, (t) => t.exit_reason ?? 'UNKNOWN'),
    };
  }, [data?.trades]);

  if (isLoading) return <Loading label="Đang tính thống kê TRADE_ENS…" />;
  if (error) return <ErrorState error={error} onRetry={() => mutate()} />;
  if (!data) return <EmptyState title="Không có dữ liệu" />;

  return (
    <div className={styles.stack}>
      <PageHeader
        title="Thống kê TRADE_ENS"
        subtitle="In-sample replay · chỉ LONG / SHORT / NO_TRADE"
        right={<Badge tone="teal">model v{data.model_version_id}</Badge>}
      />

      <Notice tone="warn">
        Số liệu dưới đây là in-sample replay, không phải live track record.
      </Notice>

      <Card title="Tổng quan" subtitle={`${data.metrics.n} lệnh · threshold SHORT ${fmtNum(data.thresholds?.SHORT ?? data.threshold, 4)}`}>
        <Metrics m={data.metrics} />
      </Card>

      <Card title="Equity curve" subtitle="tổng PnL lũy kế theo lệnh (USD/oz)">
        <Equity points={data.metrics.equity_curve} />
      </Card>

      <div className={`${styles.grid} ${styles.cols2}`}>
        <Card title="Theo hướng"><Table rows={groups.direction} firstLabel="Hướng" /></Card>
        <Card title="Theo exit reason"><Table rows={groups.exit} firstLabel="Lý do" /></Card>
      </div>

      <div className={`${styles.grid} ${styles.cols2}`}>
        <Card title="Theo giờ entry (UTC)"><Table rows={groups.hour} firstLabel="Giờ" /></Card>
        <Card title="Theo thứ"><Table rows={groups.weekday} firstLabel="Thứ" /></Card>
      </div>

      <Card title="Theo tháng"><Table rows={groups.month} firstLabel="Tháng" /></Card>

      <Card title="Giá close gần nhất" subtitle="không phải tín hiệu vào lệnh">
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th>Thời gian</th><th className="num">Close</th><th className="num">p(LONG)</th><th className="num">p(SHORT)</th><th>Tín hiệu</th></tr></thead>
            <tbody>
              {data.bars.slice(-20).reverse().map((b) => (
                <tr key={b.ts}>
                  <td className="mono">{b.ts}</td>
                  <td className="num">{fmtPrice(b.close)}</td>
                  <td className="num">{fmtNum(b.p_long, 4)}</td>
                  <td className="num">{fmtNum(b.p_short, 4)}</td>
                  <td><Badge tone={b.signal === 'LONG' ? 'teal' : b.signal === 'SHORT' ? 'danger' : 'neutral'}>{b.signal}</Badge></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <div className={styles.chips}>
        <Link href="/history">Lịch sử tổng</Link>
        <Link href="/history/day">Theo ngày</Link>
        <Link href="/backtesting">OOS backtest</Link>
      </div>
    </div>
  );
}
