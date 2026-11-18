'use client';

import Link from 'next/link';
import {
  Badge,
  Card,
  ErrorState,
  FreshnessPill,
  KV,
  Loading,
  Notice,
  PageHeader,
  Stat,
} from '@/components/ui/ui';
import { fmtNum, fmtPct, fmtPrice, fmtUtc } from '@/lib/format';
import { useApi } from '@/lib/swr';
import type { DashboardStats, Timeframe } from '@/lib/types';
import styles from './pages.module.css';

const TIMEFRAMES: Timeframe[] = ['M5', 'M15', 'H1'];

export default function OverviewPage() {
  const { data, error, isLoading, mutate } = useApi<DashboardStats>('/stats/dashboard', {
    refreshInterval: 15000,
    revalidateOnFocus: true,
  });

  if (isLoading) return <Loading label="Đang tải tổng quan trade_ens…" />;
  if (error) return <ErrorState error={error} onRetry={() => void mutate()} />;
  if (!data) return <ErrorState title="Không có dữ liệu tổng quan" />;

  const signal = data.trade_ens;
  const model = data.active_models.trade_ens[0];
  const staleTfs = TIMEFRAMES.filter((tf) => data.data_freshness[tf]?.stale);
  const signalTone =
    signal?.signal === 'LONG' ? 'success' : signal?.signal === 'SHORT' ? 'danger' : 'neutral';

  return (
    <div className={styles.stack}>
      <PageHeader
        title="Tổng quan"
        subtitle="XAUUSD · M15 · trade_ens — chỉ tín hiệu nghiên cứu, không gửi lệnh"
        right={<span className={styles.muted}>{fmtUtc(data.generated_at)}</span>}
      />

      {staleTfs.length > 0 && (
        <Notice tone="danger">
          Dữ liệu cũ: {staleTfs.join(', ')}. Không dùng tín hiệu hiện tại cho live.
        </Notice>
      )}

      {data.trade_ens_error && !signal && (
        <Notice tone="warn">trade_ens chưa sẵn sàng: {data.trade_ens_error}</Notice>
      )}

      <div className={`${styles.grid} ${styles.cols3}`}>
        <Card
          title="Trade Ens"
          subtitle={model ? `version #${model.version_id} · ${data.data_source ?? 'no source'}` : 'chưa có model approved'}
          className={styles.colsSpan2}
          right={<Badge tone={signalTone}>{signal?.signal ?? 'NO_TRADE'}</Badge>}
        >
          {signal ? (
            <>
              <div className={styles.bigBadgeWrap}>
                <Stat label="p(LONG)" value={fmtNum(signal.p_long, 4)} />
                <Stat label="p(SHORT)" value={fmtNum(signal.p_short, 4)} />
                <Stat
                  label="SHORT threshold"
                  value={fmtNum(signal.thresholds?.SHORT ?? signal.threshold, 4)}
                />
                <Stat
                  label="Tradeable"
                  value={signal.tradeable ? 'YES' : 'NO'}
                  tone={signal.tradeable ? 'up' : 'warn'}
                />
              </div>
              <KV
                items={[
                  { label: 'Giá tham chiếu', value: `${fmtPrice(signal.price)} USD` },
                  { label: 'Entry tham chiếu', value: `${fmtPrice(signal.entry_price)} USD` },
                  { label: 'TP', value: signal.tp_price == null ? '—' : `${fmtPrice(signal.tp_price)} USD` },
                  { label: 'SL', value: signal.sl_price == null ? '—' : `${fmtPrice(signal.sl_price)} USD` },
                  { label: 'Allowed sides', value: (signal.allowed_sides ?? []).join(', ') || '—' },
                  { label: 'Bar', value: fmtUtc(signal.bar_ts) },
                  { label: 'Độ trễ dữ liệu', value: `${fmtNum(signal.data_age_seconds / 60, 1)} phút` },
                  { label: 'Stale', value: signal.stale ? 'YES' : 'NO' },
                ]}
              />
              <div className={styles.chips} style={{ marginTop: 12 }}>
                <Link href="/signals">Chi tiết & lịch sử trade_ens</Link>
                <Link href="/market">Xem biểu đồ nến</Link>
              </div>
            </>
          ) : (
            <Notice tone="warn">
              Chưa có tín hiệu. Kiểm tra model approved và dữ liệu M15.
            </Notice>
          )}
        </Card>

        <Card title="Mô hình đang hoạt động" subtitle="chỉ trade_ens">
          {model ? (
            <KV
              items={[
                { label: 'Model', value: model.model_type ?? 'trade_ens' },
                { label: 'Version ID', value: model.version_id },
                { label: 'Version', value: `v${model.version}` },
                { label: 'Tạo lúc', value: fmtUtc(model.created_at) },
              ]}
            />
          ) : (
            <Notice tone="warn">Chưa có trade_ens approved.</Notice>
          )}
          <div style={{ marginTop: 12 }}>
            <Link href="/models">Mở kho mô hình</Link>
          </div>
        </Card>
      </div>

      <Card title="Độ tươi dữ liệu" subtitle="collector chỉ gửi nến đã đóng">
        <div className={`${styles.grid} ${styles.cols3}`}>
          {TIMEFRAMES.map((tf) => {
            const candle = data.candles[tf];
            const fresh = data.data_freshness[tf];
            return (
              <div key={tf}>
                <div className={styles.probTitle}>{tf}</div>
                <Stat
                  label="Số nến"
                  value={fmtNum(candle?.count ?? 0, 0)}
                  sub={candle?.latest_ts ? `mới nhất ${fmtUtc(candle.latest_ts)}` : '—'}
                />
                <div style={{ marginTop: 8 }}>
                  <FreshnessPill
                    ageMinutes={fresh?.age_minutes}
                    stale={fresh?.stale}
                    thresholdMinutes={fresh?.threshold_minutes}
                  />
                </div>
              </div>
            );
          })}
        </div>
      </Card>

      <div className={`${styles.grid} ${styles.cols2}`}>
        <Card title="Đồng bộ gần đây" subtitle="/ingest/status">
          {data.last_sync.length === 0 ? (
            <div className={styles.muted}>Chưa có log đồng bộ.</div>
          ) : (
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>TF</th>
                    <th>Collector</th>
                    <th>Lúc</th>
                    <th className="num">Ghi mới</th>
                    <th>Trạng thái</th>
                  </tr>
                </thead>
                <tbody>
                  {data.last_sync.slice(0, 6).map((s) => (
                    <tr key={s.id}>
                      <td>{s.timeframe}</td>
                      <td className="mono">{s.collector_id}</td>
                      <td className="mono">{fmtUtc(s.finished_at)}</td>
                      <td className="num">{fmtNum(s.inserted, 0)}</td>
                      <td>
                        <Badge tone={s.status === 'ok' ? 'success' : s.status === 'failed' ? 'danger' : 'warning'}>
                          {s.status}
                        </Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        <Card title="Chất lượng dữ liệu" subtitle="gap / duplicate / bad candle">
          {data.last_quality_reports.length === 0 ? (
            <div className={styles.muted}>Chưa có báo cáo chất lượng.</div>
          ) : (
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>TF</th>
                    <th className="num">Tổng</th>
                    <th className="num">Gap</th>
                    <th className="num">Dup</th>
                    <th className="num">Bad</th>
                  </tr>
                </thead>
                <tbody>
                  {data.last_quality_reports.slice(0, 6).map((q) => (
                    <tr key={q.id}>
                      <td>{q.timeframe}</td>
                      <td className="num">{fmtNum(q.total_candles, 0)}</td>
                      <td className="num">{fmtNum(q.gap_count, 0)}</td>
                      <td className="num">{fmtNum(q.duplicate_count, 0)}</td>
                      <td className="num">{fmtNum(q.bad_candle_count, 0)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>

      <Notice tone="info">
        GMRAI là công cụ nghiên cứu. API chỉ trả tín hiệu trade_ens; mọi giới hạn risk/lệnh và
        max daily loss do EA thực thi xử lý.
      </Notice>
    </div>
  );
}
