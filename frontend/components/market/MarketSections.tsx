'use client';

// Bottom sections of the Live Market page:
//  - MarketStatsCard: candle counts per timeframe + freshness (from /stats/dashboard)
//  - RecentTransitionsCard: the most recent regime transitions from the
//    latest done history run (segments)

import { Badge, Card, EmptyState, ErrorState, Loading } from '@/components/ui/ui';
import { fmtNum, fmtUtc } from '@/lib/format';
import { regimeColor, regimeLabel } from '@/lib/regime';
import type { DashboardStats, HistorySegment, Timeframe } from '@/lib/types';
import styles from './market.module.css';

const TIMEFRAMES: Timeframe[] = ['M5', 'M15', 'H1'];

export function MarketStatsCard({
  dashboard,
  loading,
  error,
}: {
  dashboard: DashboardStats | null;
  loading: boolean;
  error: unknown;
}) {
  return (
    <Card title="Thống kê dữ liệu thị trường" subtitle="/stats/dashboard">
      {loading && !dashboard && <Loading label="Đang tải thống kê dữ liệu…" />}
      {error != null && !dashboard && <ErrorState error={error} />}
      {dashboard && (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>TF</th>
                <th className="num">Số nến</th>
                <th>Nến mới nhất (UTC)</th>
                <th>Tuổi</th>
                <th>Trạng thái</th>
              </tr>
            </thead>
            <tbody>
              {TIMEFRAMES.map((tf) => {
                const st = dashboard.candles[tf];
                const f = dashboard.data_freshness[tf];
                return (
                  <tr key={tf}>
                    <td>
                      <Badge tone="neutral">{tf}</Badge>
                    </td>
                    <td className="num">{fmtNum(st?.count ?? 0, 0)}</td>
                    <td className="mono">{fmtUtc(st?.latest_ts)}</td>
                    <td className="num">{f ? `${fmtNum(f.age_minutes, 0)} phút` : '—'}</td>
                    <td>
                      {f?.stale ? (
                        <Badge tone="danger" title={`Ngưỡng ${f.threshold_minutes} phút`}>
                          Cũ
                        </Badge>
                      ) : f ? (
                        <Badge tone="success">Mới</Badge>
                      ) : (
                        <Badge tone="neutral">—</Badge>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}

export function RecentTransitionsCard({
  segments,
  loading,
  error,
}: {
  segments: HistorySegment[];
  loading: boolean;
  error: unknown;
}) {
  const recent = segments.slice(-10).reverse();
  return (
    <Card
      title="Chuyển chế độ gần đây"
      subtitle="10 đoạn regime mới nhất của run lịch sử (theo thứ tự mới → cũ)"
    >
      {loading && !segments.length && <Loading label="Đang tải các chuyển chế độ…" />}
      {error != null && !segments.length && <ErrorState error={error} />}
      {!loading && !error && segments.length === 0 && (
        <EmptyState title="Chưa có dữ liệu segments" />
      )}
      {recent.length > 0 && (
        <div className={styles.transitionList}>
          {recent.map((s) => {
            const change = s.net_change ?? 0;
            return (
              <div key={s.id} className={styles.transitionRow}>
                <span className={styles.transitionDot} style={{ background: regimeColor(s.regime) }} />
                <span className={styles.transitionRegime} style={{ color: regimeColor(s.regime) }}>
                  {regimeLabel(s.regime)}
                </span>
                <span className={styles.transitionTime}>
                  {fmtUtc(s.start_ts)} → {fmtUtc(s.end_ts)}
                </span>
                <span className={styles.transitionDur}>{s.duration_minutes} phút</span>
                <span
                  className={`num ${change >= 0 ? styles.transitionUp : styles.transitionDown}`}
                  title="Thay đổi giá ròng trong đoạn"
                >
                  {change >= 0 ? '+' : ''}
                  {fmtNum(change, 2)} USD
                </span>
              </div>
            );
          })}
        </div>
      )}
    </Card>
  );
}
