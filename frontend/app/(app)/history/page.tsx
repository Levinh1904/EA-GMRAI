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
import { fmtNum, fmtPct, fmtPrice, fmtUtcSec } from '@/lib/format';
import type { TradeHistory, TradeMetrics } from '@/lib/types';
import styles from '../pages.module.css';

function Metrics({ m }: { m: TradeMetrics }) {
  return (
    <div className={`${styles.grid} ${styles.cols4}`}>
      <Stat label="Lệnh" value={fmtNum(m.n, 0)} />
      <Stat label="Win rate" value={fmtPct(m.win_rate)} />
      <Stat label="Mean PnL" value={fmtNum(m.mean_pnl, 3)} tone={m.mean_pnl >= 0 ? 'up' : 'down'} />
      <Stat label="Total PnL" value={fmtNum(m.total_pnl, 2)} tone={m.total_pnl >= 0 ? 'up' : 'down'} />
      <Stat label="Profit factor" value={fmtNum(m.profit_factor, 3)} />
      <Stat label="Max DD" value={fmtNum(m.max_drawdown, 2)} />
      <Stat label="Avg win" value={fmtNum(m.avg_win, 3)} />
      <Stat label="Avg loss" value={fmtNum(m.avg_loss, 3)} />
    </div>
  );
}

export default function HistoryPage() {
  const { data, error, isLoading, mutate } = useApi<TradeHistory>('/trade-model/history?limit=500', {
    refreshInterval: 60000,
  });

  if (isLoading) return <Loading label="Đang tải lịch sử TRADE_ENS…" />;
  if (error) return <ErrorState error={error} onRetry={() => mutate()} />;
  if (!data) return <EmptyState title="Không có lịch sử" />;

  return (
    <div className={styles.stack}>
      <PageHeader
        title="Lịch sử TRADE_ENS"
        subtitle="In-sample replay của model đã approved — chỉ LONG / SHORT / NO_TRADE"
        right={<Badge tone="teal">TRADE_ENS v{data.model_version_id}</Badge>}
      />

      <Notice tone="warn">
        Đây là in-sample replay, không phải live track record. Chỉ hiển thị tín hiệu
        LONG / SHORT / NO_TRADE.
      </Notice>

      <Card title="Hiệu quả replay" subtitle={`${data.metrics.n} lệnh · threshold SHORT ${fmtNum(data.thresholds?.SHORT ?? data.threshold, 4)}`}>
        <Metrics m={data.metrics} />
      </Card>

      <Card title="Theo hướng" subtitle="chỉ LONG / SHORT">
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Hướng</th>
                <th className="num">Số lệnh</th>
                <th className="num">Win rate</th>
                <th className="num">Mean PnL</th>
                <th className="num">Total PnL</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(data.by_direction).map(([dir, v]) => (
                <tr key={dir}>
                  <td><Badge tone={dir === 'LONG' ? 'teal' : 'danger'}>{dir}</Badge></td>
                  <td className="num">{fmtNum(v.n, 0)}</td>
                  <td className="num">{fmtPct(v.win_rate)}</td>
                  <td className="num">{fmtNum(v.mean_pnl, 3)}</td>
                  <td className="num">{fmtNum(v.total_pnl, 2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <Card title="Nến gần nhất" subtitle="tín hiệu LONG/SHORT/NO_TRADE">
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Thời gian (UTC)</th>
                <th className="num">Close</th>
                <th className="num">p(LONG)</th>
                <th className="num">p(SHORT)</th>
                <th>Tín hiệu</th>
              </tr>
            </thead>
            <tbody>
              {data.bars.slice(-50).reverse().map((b) => (
                <tr key={b.ts}>
                  <td className="mono">{fmtUtcSec(b.ts)}</td>
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

      <Card title="Lệnh gần nhất" subtitle="một vị thế tại một thời điểm">
        {data.trades.length === 0 ? (
          <EmptyState title="Không có lệnh" />
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Hướng</th>
                  <th>Entry</th>
                  <th>Exit</th>
                  <th className="num">PnL</th>
                  <th>Lý do</th>
                </tr>
              </thead>
              <tbody>
                {data.trades.slice(-50).reverse().map((t, i) => (
                  <tr key={`${t.entry_ts}-${i}`}>
                    <td><Badge tone={t.direction === 'LONG' ? 'teal' : 'danger'}>{t.direction}</Badge></td>
                    <td className="mono">{fmtUtcSec(t.entry_ts)}</td>
                    <td className="mono">{fmtUtcSec(t.exit_ts)}</td>
                    <td className="num">{fmtNum(t.pnl, 3)}</td>
                    <td>{t.exit_reason ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <div className={styles.chips}>
        <Link href="/history/day">Xem theo ngày</Link>
        <Link href="/replay">Replay tín hiệu</Link>
        <Link href="/signals">Model & deployability</Link>
      </div>
    </div>
  );
}
