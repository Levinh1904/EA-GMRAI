'use client';

import {
  Badge,
  Card,
  ErrorState,
  FreshnessPill,
  KV,
  Loading,
  Notice,
  PageHeader,
  ProbRow,
  RegimeBadge,
  Stat,
  StatusPill,
} from '@/components/ui/ui';
import { FreshnessGauge } from '@/components/analytics/FreshnessGauge';
import { RegimeDonut } from '@/components/regime/RegimeDonut';
import { useLatestDoneRun } from '@/components/charts/TradingChart/useChartData';
import { fmtAge, fmtNum, fmtPct, fmtPrice, fmtUtc, fmtUtcSec } from '@/lib/format';
import {
  isEarlyTrend,
  permissionLabel,
  permissionTone,
  reasonCodeLabel,
  regimeColor,
  regimeShortLabel,
} from '@/lib/regime';
import { useApi } from '@/lib/swr';
import type { DashboardStats, DurationStatsResponse, MarketLatest, Timeframe } from '@/lib/types';
import { REGIME_ORDER } from './history/shared';
import styles from './pages.module.css';

const TIMEFRAMES: Timeframe[] = ['M5', 'M15', 'H1'];

export default function OverviewPage() {
  const { data, error, isLoading, mutate } = useApi<DashboardStats>('/stats/dashboard', {
    refreshInterval: 30000,
    revalidateOnFocus: true,
  });
  const latest = useApi<MarketLatest>('/market/latest', {
    refreshInterval: 30000,
    revalidateOnFocus: true,
  });

  // Regime distribution from the latest done history run (duration stats).
  const doneRun = useLatestDoneRun();
  const duration = useApi<DurationStatsResponse>(
    doneRun ? `/history/runs/${doneRun.id}/stats/duration` : null,
    { refreshInterval: 120000, revalidateOnFocus: false }
  );

  if (isLoading) return <Loading label="Đang tải tổng quan…" />;
  if (error)
    return (
      <ErrorState
        error={error}
        onRetry={() => {
          void mutate();
        }}
      />
    );
  if (!data) return <ErrorState title="Không có dữ liệu tổng quan" />;

  const { regime } = data;
  const staleTfs = TIMEFRAMES.filter((tf) => data.data_freshness[tf]?.stale);

  const hmmProbs = Object.entries(regime.probabilities.hmm_semantic ?? {}).sort(
    (a, b) => b[1] - a[1]
  );
  const rfProbs = Object.entries(regime.probabilities.rf ?? {}).sort((a, b) => b[1] - a[1]);

  return (
    <div className={styles.stack}>
      <PageHeader
        title="Tổng quan"
        subtitle={`${data.symbol} · Hệ thống phân tích chế độ thị trường bằng AI`}
        right={
          <span className={styles.muted}>
            Sinh lúc <span className="mono">{fmtUtcSec(data.generated_at)}</span>
          </span>
        }
      />

      {staleTfs.length > 0 && (
        <Notice tone="danger">
          Dữ liệu đang cũ: {staleTfs.join(', ')}. Kết quả phân tích có thể không phản ánh thị
          trường hiện tại.
        </Notice>
      )}
      {isEarlyTrend(regime.regime) && (
        <Notice tone="warn">
          Tín hiệu EARLY ({regime.regime}) — xu hướng mới chỉ ở giai đoạn sớm, chưa được xác nhận.
        </Notice>
      )}

      <div className={`${styles.grid} ${styles.cols3}`}>
        {/* Current regime */}
        <Card
          title="Chế độ thị trường hiện tại"
          subtitle={`Cập nhật ${fmtUtc(regime.timestamp)}`}
          className={styles.colsSpan2}
          tone={staleTfs.length > 0 ? 'warn' : 'default'}
        >
          <div className={styles.bigBadgeWrap}>
            <RegimeBadge regime={regime.regime} large />
            <Stat label="Độ tin cậy" value={fmtPct(regime.confidence)} sub="conf của mô hình" />
            <Stat
              label="Tuổi dữ liệu"
              value={`${fmtNum(regime.data_age_minutes, 1)} phút`}
              sub={fmtAge(regime.data_age_minutes)}
              tone={staleTfs.length > 0 ? 'warn' : 'neutral'}
            />
            <Stat
              label="Quyền"
              value={permissionLabel(regime.permission)}
              tone={permissionTone(regime.permission)}
              sub="đầu ra nghiên cứu"
            />
          </div>
          <Notice tone="warn">
            <strong>Nghiên cứu — không phải lệnh giao dịch.</strong> Quyền {permissionLabel(regime.permission)}{' '}
            chỉ là đầu ra phân tích của mô hình, không cấu thành khuyến nghị mua/bán.
          </Notice>
          <hr className={styles.rule} />
          <KV
            items={[
              { label: 'Khung thời gian', value: regime.timeframe },
              { label: 'Dữ liệu lúc', value: fmtUtc(regime.data_timestamp) },
              { label: 'Hết hạn tín hiệu', value: fmtUtc(regime.expiry) },
              { label: 'Model version', value: `v${regime.model_version}` },
              { label: 'Feature version', value: regime.feature_version },
              { label: 'Nguồn dữ liệu', value: regime.data_source },
            ]}
          />
          {regime.reason_codes.length > 0 && (
            <div className={styles.chips} style={{ marginTop: 12 }}>
              {regime.reason_codes.map((code) => (
                <Badge key={code} tone="warning" title={code}>
                  {reasonCodeLabel(code)}
                </Badge>
              ))}
            </div>
          )}
        </Card>

        {/* Market snapshot */}
        <Card title="Giá mới nhất" subtitle={latest.data?.symbol ?? 'XAUUSD'}>
          {latest.isLoading && <Loading />}
          {latest.error && <ErrorState error={latest.error} />}
          {latest.data && (
            <div className={styles.stack}>
              {TIMEFRAMES.map((tf) => {
                const c = latest.data?.latest[tf];
                if (!c) return null;
                const change = c.close - c.open;
                const pct = c.open ? (change / c.open) * 100 : 0;
                return (
                  <div key={tf} className={styles.grid} style={{ gap: 8 }}>
                    <div
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'baseline',
                      }}
                    >
                      <Badge tone="neutral">{tf}</Badge>
                      <span className="mono" style={{ fontSize: 13 }}>
                        {fmtPrice(c.close)}
                      </span>
                    </div>
                    <div
                      className="mono"
                      style={{
                        display: 'flex',
                        gap: 10,
                        fontSize: 11.5,
                        color: change >= 0 ? 'var(--green)' : 'var(--red)',
                      }}
                    >
                      <span>
                        {change >= 0 ? '+' : ''}
                        {fmtPrice(change)}
                      </span>
                      <span>
                        ({change >= 0 ? '+' : ''}
                        {pct.toFixed(2)}%)
                      </span>
                      <span className={styles.muted} style={{ color: 'var(--text-faint)' }}>
                        spread {c.spread}
                      </span>
                    </div>
                    <div className={styles.muted} style={{ fontSize: 11 }}>
                      {fmtUtc(c.ts)} · vol {fmtNum(c.tick_volume, 0)}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </Card>
      </div>

      {/* Candle counts + freshness */}
      <div className={`${styles.grid} ${styles.cols4}`}>
        {TIMEFRAMES.map((tf) => {
          const st = data.candles[tf];
          const f = data.data_freshness[tf];
          return (
            <Card key={tf} title={`Nến ${tf}`}>
              <Stat
                label="Số lượng nến"
                value={fmtNum(st?.count ?? 0, 0)}
                sub={st?.latest_ts ? `mới nhất ${fmtUtc(st.latest_ts)}` : '—'}
              />
              <div style={{ marginTop: 10 }}>
                <FreshnessPill
                  ageMinutes={f?.age_minutes}
                  stale={f?.stale}
                  thresholdMinutes={f?.threshold_minutes}
                />
              </div>
            </Card>
          );
        })}
      </div>

      <div className={`${styles.grid} ${styles.cols2}`}>
        {/* Data freshness gauges */}
        <Card
          title="Đồng hồ đo độ tươi dữ liệu"
          subtitle="Tuổi nến gần nhất so với ngưỡng cảnh báo của từng khung thời gian"
        >
          <div className={styles.gaugesRowLocal}>
            {TIMEFRAMES.map((tf) => (
              <FreshnessGauge key={tf} tf={tf} info={data.data_freshness[tf]} />
            ))}
          </div>
        </Card>

        {/* Regime distribution donut */}
        <Card
          title="Phân bố chế độ thị trường"
          subtitle={
            doneRun
              ? `Thời lượng chiếm dụng theo regime — run lịch sử #${doneRun.id} (${fmtNum(doneRun.bar_count, 0)} nến M15)`
              : 'Từ run phân tích lịch sử mới nhất'
          }
        >
          {duration.isLoading && <Loading label="Đang tải phân bố regime…" />}
          {duration.error && !duration.data && <ErrorState error={duration.error} />}
          {duration.data && (() => {
            const dur = duration.data;
            const dominant = REGIME_ORDER.reduce((best, r) =>
              (dur.regimes[r.key]?.occupancy_pct ?? 0) > (dur.regimes[best.key]?.occupancy_pct ?? 0)
                ? r
                : best
            );
            return (
              <>
                <RegimeDonut
                  slices={REGIME_ORDER.map((r) => ({
                    key: r.key,
                    label: r.label,
                    value: dur.regimes[r.key]?.occupancy_pct ?? 0,
                    color: r.color,
                  }))}
                  centerValue={regimeShortLabel(dominant.key)}
                  centerLabel="chế độ chính"
                />
                <div className={styles.muted} style={{ fontSize: 12, marginTop: 10 }}>
                  Tổng {fmtNum(dur.total_transitions, 0)} lần chuyển chế độ trong toàn bộ dữ liệu
                  lịch sử.
                </div>
              </>
            );
          })()}
          {!duration.isLoading && !duration.data && (
            <ErrorState title="Chưa có run lịch sử" error="Chạy phân tích lịch sử để xem phân bố regime." />
          )}
        </Card>
      </div>

      {/* Probabilities */}
      <Card title="Xác suất chế độ (HMM / Random Forest)">
        <div className={styles.probCols}>
          <div className={styles.probCol}>
            <div className={styles.probTitle}>HMM — hậu nghiệm theo nhãn ngữ nghĩa</div>
            {hmmProbs.map(([label, v]) => (
              <ProbRow key={label} label={label} value={v} color={regimeColor(label)} />
            ))}
          </div>
          <div className={styles.probCol}>
            <div className={styles.probTitle}>Random Forest — xác suất lớp</div>
            {rfProbs.map(([label, v]) => (
              <ProbRow key={label} label={label} value={v} color={regimeColor(label)} />
            ))}
          </div>
        </div>
      </Card>

      <div className={`${styles.grid} ${styles.cols2}`}>
        {/* Last sync */}
        <Card title="Đồng bộ dữ liệu gần nhất">
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Collector</th>
                  <th>TF</th>
                  <th>Hoàn tất (UTC)</th>
                  <th>Trạng thái</th>
                  <th className="num">Thêm mới</th>
                  <th className="num">Cập nhật</th>
                </tr>
              </thead>
              <tbody>
                {data.last_sync.slice(0, 8).map((s) => (
                  <tr key={s.id}>
                    <td className="mono">{s.id}</td>
                    <td className="mono">{s.collector_id}</td>
                    <td>{s.timeframe}</td>
                    <td className="mono">{fmtUtc(s.finished_at)}</td>
                    <td>
                      <StatusPill status={s.status} />
                    </td>
                    <td className="num">{fmtNum(s.inserted, 0)}</td>
                    <td className="num">{fmtNum(s.updated, 0)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>

        {/* Active models */}
        <Card title="Mô hình đang hoạt động">
          <div className={styles.stack}>
            <div>
              <div className={styles.probTitle}>HMM (model_id → version)</div>
              {data.active_models.hmm.map((m) => (
                <div key={`${m.model_type}-${m.id}`} className={styles.chips} style={{ marginBottom: 6 }}>
                  <Badge tone="teal">hmm</Badge>
                  <span className="mono">
                    model_id {m.model_id ?? '—'} · id {m.id ?? '—'} · v{m.version ?? '—'}
                  </span>
                </div>
              ))}
              {data.active_models.hmm.length === 0 && (
                <div className={styles.muted}>Không có mô hình HMM hoạt động</div>
              )}
            </div>
            <div>
              <div className={styles.probTitle}>Random Forest (model_id → version)</div>
              {data.active_models.random_forest.map((m) => (
                <div key={`${m.model_type}-${m.id}`} className={styles.chips} style={{ marginBottom: 6 }}>
                  <Badge tone="purple">random_forest</Badge>
                  <span className="mono">
                    model_id {m.model_id ?? '—'} · id {m.id ?? '—'} · v{m.version ?? '—'}
                  </span>
                </div>
              ))}
              {data.active_models.random_forest.length === 0 && (
                <div className={styles.muted}>Không có mô hình RF hoạt động</div>
              )}
            </div>
          </div>
        </Card>
      </div>

      {/* Last quality reports */}
      <Card title="Báo cáo chất lượng dữ liệu gần nhất">
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>TF</th>
                <th>Kiểm tra lúc (UTC)</th>
                <th className="num">Tổng nến</th>
                <th className="num">Thiếu</th>
                <th className="num">Trùng</th>
                <th className="num">Gap</th>
                <th className="num">Nến lỗi</th>
                <th>Trạng thái</th>
              </tr>
            </thead>
            <tbody>
              {data.last_quality_reports.map((q) => (
                <tr key={q.id}>
                  <td>{q.timeframe}</td>
                  <td className="mono">{fmtUtcSec(q.checked_at)}</td>
                  <td className="num">{fmtNum(q.total_candles, 0)}</td>
                  <td className="num">{fmtNum(q.missing_count, 0)}</td>
                  <td className="num">{fmtNum(q.duplicate_count, 0)}</td>
                  <td className="num">{fmtNum(q.gap_count, 0)}</td>
                  <td className="num">{fmtNum(q.bad_candle_count, 0)}</td>
                  <td>{q.stale ? <Badge tone="danger">Cũ</Badge> : <Badge tone="success">OK</Badge>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
