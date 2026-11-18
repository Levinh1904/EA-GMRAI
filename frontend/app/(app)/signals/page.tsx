'use client';

import { useState } from 'react';
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
  Stat,
} from '@/components/ui/ui';
import { ApiError, api } from '@/lib/api';
import { fmtNum, fmtPct, fmtPrice, fmtUtcSec } from '@/lib/format';
import { useApi } from '@/lib/swr';
import type { TradeDeployability, TradeHistory, TradeMetrics, TradeModelStatus, TradeSignal } from '@/lib/types';
import styles from '../pages.module.css';

function metricTone(m: TradeMetrics | null | undefined): 'up' | 'down' | 'warn' {
  if (!m || m.mean_pnl == null) return 'warn';
  return m.mean_pnl > 0 ? 'up' : 'down';
}

function MetricsCard({ title, metrics }: { title: string; metrics: TradeMetrics | null | undefined }) {
  if (!metrics || metrics.n === 0) {
    return (
      <Card title={title}>
        <EmptyState title="Không có lệnh" hint="Model không mở lệnh nào trên tập này." />
      </Card>
    );
  }
  return (
    <Card title={title} subtitle={`${metrics.n} lệnh · win ${fmtPct(metrics.win_rate)} · Wilson ${fmtPct(metrics.wilson_low)} – ${fmtPct(metrics.wilson_high)}`}>
      <div className={`${styles.grid} ${styles.cols4}`}>
        <Stat label="Win rate" value={fmtPct(metrics.win_rate)} tone={metricTone(metrics)} />
        <Stat label="Mean PnL" value={fmtNum(metrics.mean_pnl, 3)} tone={metricTone(metrics)} sub="USD/oz mỗi lệnh" />
        <Stat label="Total PnL" value={fmtNum(metrics.total_pnl, 2)} tone={metricTone(metrics)} />
        <Stat label="Profit factor" value={fmtNum(metrics.profit_factor, 3)} tone={metricTone(metrics)} />
        <Stat label="Breakeven win rate" value={fmtPct(metrics.breakeven_win_rate)} />
        <Stat label="Max drawdown" value={fmtNum(metrics.max_drawdown, 2)} />
        <Stat label="Avg win" value={fmtNum(metrics.avg_win, 3)} />
        <Stat label="Avg loss" value={fmtNum(metrics.avg_loss, 3)} />
      </div>
    </Card>
  );
}

function SignalCard({ signal }: { signal: TradeSignal }) {
  const tone = signal.signal === 'LONG' ? 'teal' : signal.signal === 'SHORT' ? 'danger' : 'neutral';
  return (
    <Card
      title="Tín hiệu mới nhất"
      subtitle={`${signal.symbol} · ${signal.timeframe} · model v${signal.model_version_id}`}
      right={<Badge tone={tone}>{signal.signal}</Badge>}
    >
      <div className={`${styles.grid} ${styles.cols4}`}>
        <Stat label="p(LONG)" value={fmtNum(signal.p_long, 4)} />
        <Stat label="p(SHORT)" value={fmtNum(signal.p_short, 4)} />
        <Stat label="Threshold SHORT" value={fmtNum(signal.thresholds?.SHORT ?? signal.threshold, 4)} />
        <Stat label="ATR" value={fmtNum(signal.atr, 3)} />
      </div>
      <div className={styles.chips} style={{ marginBottom: 10 }}>
        <span className={styles.muted}>Được phép:</span>
        {(signal.allowed_sides ?? ['LONG', 'SHORT']).map((side) => (
          <Badge key={side} tone={side === 'SHORT' ? 'danger' : 'teal'}>
            {side}
          </Badge>
        ))}
      </div>
      <KV
        items={[
          { label: 'Giá tham chiếu', value: `${fmtPrice(signal.price)} USD` },
          { label: 'Entry tham chiếu', value: `${fmtPrice(signal.entry_price)} USD` },
          { label: 'TP (0.5 ATR)', value: signal.tp_price == null ? '—' : `${fmtPrice(signal.tp_price)} USD` },
          { label: 'SL (2.0 ATR)', value: signal.sl_price == null ? '—' : `${fmtPrice(signal.sl_price)} USD` },
          { label: 'Nến M15', value: fmtUtcSec(signal.bar_ts) },
          { label: 'Hết hạn', value: fmtUtcSec(signal.expires_at) },
          { label: 'Spread', value: `${fmtNum(signal.spread_usd, 3)} USD` },
          { label: 'Nguồn', value: signal.source },
        ]}
      />
      {signal.stale && (
        <Notice tone="warn">
          Dữ liệu đã cũ ({Math.round(signal.data_age_seconds / 60)} phút). Không coi đây là tín hiệu vào lệnh.
        </Notice>
      )}
      <Notice tone="info">Research-only: GMRAI không gửi lệnh sang MT5. EA/người dùng là bên thực thi duy nhất.</Notice>
    </Card>
  );
}

export default function TradeEnsPage() {
  const { isAdmin } = useAuth();
  const [training, setTraining] = useState(false);
  const [trainMsg, setTrainMsg] = useState<string | null>(null);
  const status = useApi<TradeModelStatus>('/trade-model/status');
  const deploy = useApi<TradeDeployability>('/trade-model/deployability', { refreshInterval: 60000 });
  const signal = useApi<TradeSignal>('/trade-model/signal', { refreshInterval: 15000 });
  const history = useApi<TradeHistory>('/trade-model/history?limit=300', { refreshInterval: 60000 });

  async function startTraining() {
    setTraining(true);
    setTrainMsg(null);
    try {
      const res = await api.startTradeModelTraining();
      setTrainMsg(`Đã xếp lịch training: run #${res.run_id}, job #${res.job_id}. Theo dõi ở trang Training/Jobs.`);
      await status.mutate();
    } catch (e) {
      setTrainMsg(e instanceof ApiError ? e.message : String(e));
    } finally {
      setTraining(false);
    }
  }

  if (status.isLoading) return <Loading label="Đang tải trạng thái trade_ens…" />;
  if (status.error) return <ErrorState title="Không tải được trade_ens" error={status.error} onRetry={() => status.mutate()} />;

  const s = status.data;
  const oos = s?.walk_forward?.oos_metrics;

  return (
    <div className={styles.stack}>
      <PageHeader
        title="Trade Ens · XAUUSD M15"
        subtitle="LightGBM + RandomForest + Logistic, ensemble xác suất LONG/SHORT. Không phải HMM/RF regime cũ."
        right={
          isAdmin ? (
            <Button variant="primary" onClick={startTraining} disabled={training}>
              {training ? 'Đang xếp lịch…' : 'Train trade_ens'}
            </Button>
          ) : undefined
        }
      />

      {trainMsg && <Notice tone="info">{trainMsg}</Notice>}

      {!s?.approved ? (
        <Notice tone="warn">
          Chưa có model trade_ens approved. {s?.code === 'NO_APPROVED_MODEL' ? 'Hãy train trước.' : null}
        </Notice>
      ) : (
        <>
          {deploy.data && (
            <Card
              title="Điều kiện deploy"
              subtitle="Model gate do GMRAI kiểm; risk/lệnh và max daily loss do EA xử lý."
              right={
                <div className={styles.chips}>
                  <Badge tone={deploy.data.demo_ready ? 'success' : 'warning'}>demo</Badge>
                  <Badge tone={deploy.data.live_ready ? 'success' : 'danger'}>live</Badge>
                </div>
              }
            >
              <KV
                items={[
                  { label: 'Model gate', value: deploy.data.model_ready ? 'PASS' : 'FAIL' },
                  { label: 'Dữ liệu mới', value: deploy.data.data_fresh ? 'PASS' : 'STALE' },
                  { label: 'Bar cuối', value: fmtUtcSec(deploy.data.latest_bar_ts) },
                  { label: 'Tuổi dữ liệu', value: deploy.data.data_age_minutes == null ? '—' : `${fmtNum(deploy.data.data_age_minutes, 1)} phút` },
                ]}
              />
              {deploy.data.blockers.length > 0 && (
                <Notice tone="danger">Blockers: {deploy.data.blockers.join(', ')}</Notice>
              )}
              {deploy.data.warnings.length > 0 && (
                <Notice tone="warn">Warnings: {deploy.data.warnings.join(', ')}</Notice>
              )}
            </Card>
          )}
          <Card
            title="Trạng thái model"
            subtitle={`Version #${s.model_version_id} · feature ${s.feature_version} · trained until ${fmtUtcSec(s.trained_until)}`}
            right={<Badge tone="success">approved</Badge>}
          >
            <KV
              items={[
                { label: 'Allowed sides', value: (s.allowed_sides ?? ['LONG', 'SHORT']).join(', ') },
                { label: 'Threshold SHORT', value: fmtNum(s.thresholds?.SHORT ?? s.threshold, 6) },
                { label: 'Quantile', value: fmtNum(s.quantile, 2) },
                { label: 'Artifact', value: <span className="mono">{s.artifact_path ?? '—'}</span> },
                {
                  label: 'Gate',
                  value: s.walk_forward?.gate
                    ? `${s.walk_forward.gate.min_trades} lệnh · mean PnL > 0 · PF > ${
                        s.walk_forward.gate.min_profit_factor ?? 1
                      } · Wilson ≥ breakeven ${fmtPct(s.walk_forward.gate.breakeven_win_rate)}`
                    : '—',
                },
              ]}
            />
          </Card>

          {oos && oos.mean_pnl <= 0 && (
            <Notice tone="danger">
              Cảnh báo thật: OOS win-rate {fmtPct(oos.win_rate)} nhưng mean PnL {fmtNum(oos.mean_pnl, 3)} USD/oz.
              Win-rate không đồng nghĩa có lãi; không dùng số này để quảng cáo.
            </Notice>
          )}
          {s.holdout_metrics && s.holdout_metrics.n === 0 && (
            <Notice tone="warn">
              Holdout không mở lệnh nào tại threshold đã đóng băng; không có bằng chứng PnL out-of-sample cho version này.
            </Notice>
          )}
          {s.warnings && s.warnings.length > 0 && (
            <Notice tone="warn">
              {s.warnings.map((w) => (
                <div key={w}>{w}</div>
              ))}
            </Notice>
          )}
          <MetricsCard title="Out-of-sample (4 fold walk-forward)" metrics={oos} />
          <MetricsCard title="Holdout cuối (480 nến, chỉ chấm một lần)" metrics={s.holdout_metrics} />
        </>
      )}

      {signal.error ? (
        <Card title="Tín hiệu mới nhất">
          <Notice tone="warn">
            {signal.error instanceof ApiError ? signal.error.message : String(signal.error)}
          </Notice>
        </Card>
      ) : signal.isLoading ? (
        <Loading label="Đang tính tín hiệu…" />
      ) : signal.data ? (
        <SignalCard signal={signal.data} />
      ) : null}

      {history.error ? (
        <Card title="Lịch sử in-sample">
          <Notice tone="warn">
            {history.error instanceof ApiError ? history.error.message : String(history.error)}
          </Notice>
        </Card>
      ) : history.isLoading ? (
        <Loading label="Đang replay lịch sử…" />
      ) : history.data ? (
        <>
          <MetricsCard title="In-sample replay (KHÔNG phải live track record)" metrics={history.data.metrics} />
          <Card
            title="Nến gần nhất"
            subtitle={`Threshold ${fmtNum(history.data.threshold, 6)} · ${history.data.bars.length} nến`}
          >
            {history.data.bars.length === 0 ? (
              <EmptyState title="Không có nến" />
            ) : (
              <div className="table-wrap">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Thời gian (UTC)</th>
                      <th className="num">Close</th>
                      <th className="num">p(LONG)</th>
                      <th className="num">p(SHORT)</th>
                      <th>Tín hiệu</th>
                      <th>Context ref_v1</th>
                    </tr>
                  </thead>
                  <tbody>
                    {history.data.bars.slice(-25).reverse().map((b) => (
                      <tr key={b.ts}>
                        <td className="mono">{fmtUtcSec(b.ts)}</td>
                        <td className="num">{fmtPrice(b.close)}</td>
                        <td className="num">{fmtNum(b.p_long, 4)}</td>
                        <td className="num">{fmtNum(b.p_short, 4)}</td>
                        <td>
                          <Badge tone={b.signal === 'LONG' ? 'teal' : b.signal === 'SHORT' ? 'danger' : 'neutral'}>
                            {b.signal}
                          </Badge>
                        </td>
                        <td>{b.reference_regime ?? '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
          <Card title="Lệnh in-sample gần nhất" subtitle="Một vị thế tại một thời điểm; đã trừ spread.">
            {history.data.trades.length === 0 ? (
              <EmptyState title="Không có lệnh" />
            ) : (
              <div className="table-wrap">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Hướng</th>
                      <th>Entry (UTC)</th>
                      <th>Exit (UTC)</th>
                      <th className="num">Bars</th>
                      <th className="num">PnL USD/oz</th>
                      <th>Lý do</th>
                    </tr>
                  </thead>
                  <tbody>
                    {history.data.trades.slice(-25).reverse().map((t, i) => (
                      <tr key={`${t.entry_ts}-${i}`}>
                        <td><Badge tone={t.direction === 'LONG' ? 'teal' : 'danger'}>{t.direction}</Badge></td>
                        <td className="mono">{fmtUtcSec(t.entry_ts)}</td>
                        <td className="mono">{fmtUtcSec(t.exit_ts)}</td>
                        <td className="num">{t.bars}</td>
                        <td className="num">{fmtNum(t.pnl, 3)}</td>
                        <td>{t.exit_reason ?? '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
          <Notice tone="warn">
            In-sample replay dùng chính model đã fit trên quá khứ; không phải bằng chứng lợi nhuận tương lai.
            Luôn shadow → demo trước khi cho EA thực thi.
          </Notice>
        </>
      ) : null}
    </div>
  );
}
