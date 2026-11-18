'use client';

import { useState } from 'react';
import {
  Badge,
  Button,
  Card,
  ErrorState,
  KV,
  Loading,
  Notice,
  PageHeader,
  Stat,
} from '@/components/ui/ui';
import { useAuth } from '@/components/AuthProvider';
import { ApiError, api } from '@/lib/api';
import { useApi } from '@/lib/swr';
import { fmtNum, fmtUtcSec } from '@/lib/format';
import type { TelegramStatusResponse, TradeSignal } from '@/lib/types';
import styles from '../pages.module.css';

interface Forecast {
  signal: 'LONG' | 'SHORT' | 'NO_TRADE';
  probability_long: number;
  probability_short: number;
  threshold: number | null;
  bar_ts: string | null;
  target_ts: string | null;
  stale: boolean;
  note: string;
}

export default function TelegramPage() {
  const { isAdmin } = useAuth();
  const status = useApi<TelegramStatusResponse>('/telegram/status', { refreshInterval: 30000 });
  const forecast = useApi<Forecast>('/forecast/next', { refreshInterval: 30000 });
  const signal = useApi<TradeSignal>('/trade-model/signal', { refreshInterval: 15000 });
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ tone: 'info' | 'warn' | 'danger'; text: string } | null>(null);

  async function act(fn: () => Promise<{ status?: string; reason?: string; error?: string | null }>) {
    setBusy(true);
    setMsg(null);
    try {
      const res = await fn();
      setMsg({
        tone: res.status === 'sent' ? 'info' : res.status === 'skipped' ? 'warn' : 'danger',
        text: `Kết quả: ${res.status ?? '—'}${res.reason ? ` · ${res.reason}` : ''}${res.error ? ` · ${res.error}` : ''}`,
      });
      await status.mutate();
    } catch (e) {
      setMsg({ tone: 'danger', text: e instanceof ApiError ? e.message : 'Thao tác thất bại' });
    } finally {
      setBusy(false);
    }
  }

  if (status.isLoading) return <Loading label="Đang tải Telegram…" />;
  if (status.error) return <ErrorState error={status.error} onRetry={() => status.mutate()} />;

  const st = status.data;
  const latest = st?.latest_signal;

  return (
    <div className={styles.stack}>
      <PageHeader
        title="Telegram & Forecast · TRADE_ENS"
        subtitle="Chỉ gửi LONG / SHORT / NO_TRADE"
      />

      {msg && <Notice tone={msg.tone}>{msg.text}</Notice>}

      <div className={`${styles.grid} ${styles.cols3}`}>
        <Card title="Kênh Telegram">
          <KV
            items={[
              { label: 'Enabled', value: st?.enabled ? 'YES' : 'NO' },
              { label: 'Configured', value: st?.configured ? 'YES' : 'NO' },
              { label: 'Chat ID', value: st?.chat_id ?? '—' },
              { label: 'Đã gửi', value: fmtNum(st?.counts.sent ?? 0, 0) },
              { label: 'Bỏ qua', value: fmtNum(st?.counts.skipped ?? 0, 0) },
              { label: 'Lỗi', value: fmtNum(st?.counts.failed ?? 0, 0) },
            ]}
          />
          <div className={styles.btnRow} style={{ marginTop: 12 }}>
            <Button variant="primary" disabled={!isAdmin || busy} onClick={() => act(api.sendTelegramTest)}>
              Gửi test
            </Button>
            <Button disabled={!isAdmin || busy} onClick={() => act(() => api.notifyTelegram({ includeForecast: false }))}>
              Gửi tín hiệu hiện tại
            </Button>
          </div>
        </Card>

        <Card title="Tín hiệu hiện tại" right={<Badge tone={latest?.signal === 'LONG' ? 'teal' : latest?.signal === 'SHORT' ? 'danger' : 'neutral'}>{latest?.signal ?? 'NO_TRADE'}</Badge>}>
          {latest ? (
            <KV
              items={[
                { label: 'Bar M15', value: fmtUtcSec(latest.bar_ts) },
                { label: 'p(LONG)', value: fmtNum(latest.p_long, 4) },
                { label: 'p(SHORT)', value: fmtNum(latest.p_short, 4) },
                { label: 'Threshold SHORT', value: fmtNum(latest.threshold, 4) },
                { label: 'Stale', value: latest.stale ? 'YES' : 'NO' },
                { label: 'Model version', value: signal.data?.model_version_id ?? '—' },
              ]}
            />
          ) : (
            <Notice tone="warn">Chưa có tín hiệu.</Notice>
          )}
        </Card>

        <Card title="Forecast" subtitle="TRADE_ENS signal">
          {forecast.error ? (
            <Notice tone="warn">{forecast.error instanceof Error ? forecast.error.message : String(forecast.error)}</Notice>
          ) : forecast.data ? (
            <>
              <Badge tone={forecast.data.signal === 'LONG' ? 'teal' : forecast.data.signal === 'SHORT' ? 'danger' : 'neutral'}>
                {forecast.data.signal}
              </Badge>
              <div className={`${styles.grid} ${styles.cols2}`} style={{ marginTop: 10 }}>
                <Stat label="p(LONG)" value={fmtNum(forecast.data.probability_long, 4)} />
                <Stat label="p(SHORT)" value={fmtNum(forecast.data.probability_short, 4)} />
              </div>
              <div className={styles.muted} style={{ marginTop: 8 }}>
                {forecast.data.note}
              </div>
            </>
          ) : (
            <Loading label="Đang tải forecast…" />
          )}
        </Card>
      </div>

      <Notice tone="info">
        Telegram chỉ nhận output TRADE_ENS: LONG, SHORT hoặc NO_TRADE.
      </Notice>
    </div>
  );
}
