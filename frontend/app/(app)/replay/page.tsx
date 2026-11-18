'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
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
  Stat,
} from '@/components/ui/ui';
import { useApi } from '@/lib/swr';
import { fmtNum, fmtPrice, fmtUtcSec } from '@/lib/format';
import type { TradeHistory } from '@/lib/types';
import styles from '../pages.module.css';

export default function ReplayPage() {
  const { data, error, isLoading, mutate } = useApi<TradeHistory>('/trade-model/history?limit=5000', {
    refreshInterval: 0,
  });
  const [idx, setIdx] = useState(0);
  const [playing, setPlaying] = useState(false);

  const bars = data?.bars ?? [];
  useEffect(() => {
    if (data?.bars.length) setIdx(Math.max(0, data.bars.length - 1));
  }, [data?.bars.length]);

  useEffect(() => {
    if (!playing || bars.length === 0) return;
    const timer = setInterval(() => {
      setIdx((i) => {
        if (i >= bars.length - 1) {
          setPlaying(false);
          return i;
        }
        return i + 1;
      });
    }, 500);
    return () => clearInterval(timer);
  }, [playing, bars.length]);

  const current = bars[idx];
  const trades = useMemo(
    () => (data?.trades ?? []).filter((t) => t.entry_ts <= (current?.ts ?? '')),
    [data?.trades, current?.ts]
  );
  const pnl = trades.reduce((sum, t) => sum + t.pnl, 0);

  if (isLoading) return <Loading label="Đang tải replay TRADE_ENS…" />;
  if (error) return <ErrorState error={error} onRetry={() => mutate()} />;
  if (!data || bars.length === 0) return <EmptyState title="Không có dữ liệu replay" />;

  return (
    <div className={styles.stack}>
      <PageHeader
        title="Replay tín hiệu · TRADE_ENS"
        subtitle="Bước qua từng nến M15; chỉ hiển thị LONG / SHORT / NO_TRADE"
        right={<Link href="/history">← Lịch sử</Link>}
      />

      <Card title="Điều khiển" subtitle={`${idx + 1} / ${bars.length} nến`}>
        <div className={styles.btnRow}>
          <Button onClick={() => setIdx(0)}>Đầu</Button>
          <Button onClick={() => setIdx((i) => Math.max(0, i - 1))}>← Trước</Button>
          <Button variant="primary" onClick={() => setPlaying((v) => !v)}>
            {playing ? 'Tạm dừng' : 'Phát'}
          </Button>
          <Button onClick={() => setIdx((i) => Math.min(bars.length - 1, i + 1))}>Sau →</Button>
          <Button onClick={() => setIdx(bars.length - 1)}>Cuối</Button>
        </div>
        <input
          type="range"
          min={0}
          max={Math.max(0, bars.length - 1)}
          value={idx}
          onChange={(e) => setIdx(Number(e.target.value))}
          style={{ width: '100%', marginTop: 14 }}
        />
      </Card>

      <div className={`${styles.grid} ${styles.cols4}`}>
        <Stat label="Thời gian" value={fmtUtcSec(current.ts)} />
        <Stat label="Close" value={fmtPrice(current.close)} />
        <Stat label="Tín hiệu" value={current.signal} />
        <Stat label="PnL lũy kế" value={fmtNum(pnl, 2)} tone={pnl >= 0 ? 'up' : 'down'} />
      </div>

      <Card title="Nến hiện tại" right={<Badge tone={current.signal === 'LONG' ? 'teal' : current.signal === 'SHORT' ? 'danger' : 'neutral'}>{current.signal}</Badge>}>
        <KV
          items={[
            { label: 'Open', value: fmtPrice(current.open) },
            { label: 'High', value: fmtPrice(current.high) },
            { label: 'Low', value: fmtPrice(current.low) },
            { label: 'Close', value: fmtPrice(current.close) },
            { label: 'p(LONG)', value: fmtNum(current.p_long, 4) },
            { label: 'p(SHORT)', value: fmtNum(current.p_short, 4) },
            { label: 'ATR', value: fmtNum(current.atr, 3) },
            { label: 'Lệnh đã đóng', value: fmtNum(trades.length, 0) },
          ]}
        />
      </Card>

      <Notice tone="info">
        Replay từ lịch sử in-sample của model.
      </Notice>
    </div>
  );
}
