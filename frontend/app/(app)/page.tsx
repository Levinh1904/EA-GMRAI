'use client';

// Overview — deliberately compact.
//
// Layout principle: the three things an operator checks first are at the top in
// one row (current regime · live price · freshness). Everything diagnostic
// (candle counts, gauges, sync/quality tables, model registry) is collapsed into
// <details> sections that cost no vertical space until opened. The previous
// version stacked ~7 full-width cards and the important numbers were buried.

import { useState } from 'react';
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
import type {
  DashboardStats,
  DurationStatsResponse,
  MarketLatest,
  MarketTick,
  Timeframe,
} from '@/lib/types';
import { REGIME_ORDER } from './history/shared';
import styles from './pages.module.css';

const TIMEFRAMES: Timeframe[] = ['M5', 'M15', 'H1'];

function Section({
  title,
  summary,
  children,
  defaultOpen = false,
}: {
  title: string;
  summary?: string;
  children: React.ReactNode;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <section className={styles.collapse}>
      <button
        type="button"
        className={styles.collapseHead}
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <span className={styles.collapseCaret}>{open ? '▾' : '▸'}</span>
        <span className={styles.collapseTitle}>{title}</span>
        {summary && <span className={styles.collapseSummary}>{summary}</span>}
      </button>
      {open && <div className={styles.collapseBody}>{children}</div>}
    </section>
  );
}

export default function OverviewPage() {
  const { data, error, isLoading, mutate } = useApi<DashboardStats>('/stats/dashboard', {
    refreshInterval: 10000,
    revalidateOnFocus: true,
  });
  const latest = useApi<MarketLatest>('/market/latest', {
    refreshInterval: 5000,
    revalidateOnFocus: true,
  });
  const tick = useApi<MarketTick>('/market/tick', { refreshInterval: 2000 });

  const doneRun = useLatestDoneRun();
  const duration = useApi<DurationStatsResponse>(
    doneRun ? `/history/runs/${doneRun.id}/stats/duration` : null,
    { refreshInterval: 60000, revalidateOnFocus: false }
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
  const m15 = latest.data?.latest?.M15;
  const liveBid = tick.data?.live ? tick.data.bid : null;

  const dominant = duration.data
    ? REGIME_ORDER.reduce((best, r) =>
        (duration.data!.regimes[r.key]?.occupancy_pct ?? 0) >
        (duration.data!.regimes[best.key]?.occupancy_pct ?? 0)
          ? r
          : best
      )
    : null;

  return (
    <div className={styles.stack}>
      <PageHeader
        title="Tổng quan"
        subtitle={`${data.symbol} · ${regime.timeframe} · AI regime`}
        right={
          <span className={styles.muted} style={{ fontSize: 12 }}>
            {fmtUtcSec(data.generated_at)}
          </span>
        }
      />

      {staleTfs.length > 0 && (
        <Notice tone="danger">
          Dữ liệu cũ: {staleTfs.join(', ')} — kết quả có thể không phản ánh thị trường hiện tại.
        </Notice>
      )}
      {regime.engine === 'trade_ens' && (
        <Notice tone="info">
          {regime.message ?? 'HMM/RF đã tắt; chỉ trade_ens đang hoạt động.'}{' '}
          Tín hiệu trade_ens:{' '}
          <strong>{regime.trade_ens?.signal ?? 'NO_TRADE'}</strong>.{' '}
          <Link href="/signals">Mở trang Trade Ens</Link>.
        </Notice>
      )}
      {isEarlyTrend(regime.regime) && (
        <Notice tone="warn">
          Tín hiệu EARLY ({regime.regime}) — xu hướng mới ở giai đoạn sớm, chưa xác nhận.
        </Notice>
      )}

      {/* ---------- Top row: the three numbers that matter ---------- */}
      <div className={`${styles.grid} ${styles.cols3}`}>
        <Card
          title="Chế độ hiện tại"
          subtitle={`cập nhật ${fmtUtc(regime.timestamp)}`}
          tone={staleTfs.length > 0 ? 'warn' : 'default'}
        >
          <div className={styles.bigBadgeWrap}>
            <RegimeBadge regime={regime.regime} large />
          </div>
          <div className={`${styles.grid} ${styles.cols3}`} style={{ marginTop: 12 }}>
            <Stat label="Tin cậy" value={fmtPct(regime.confidence)} />
            <Stat
              label="Tuổi dữ liệu"
              value={`${fmtNum(regime.data_age_minutes, 0)}p`}
              sub={fmtAge(regime.data_age_minutes)}
              tone={staleTfs.length > 0 ? 'warn' : 'neutral'}
            />
            <Stat
              label="Quyền"
              value={permissionLabel(regime.permission)}
              tone={permissionTone(regime.permission)}
            />
          </div>
        </Card>

        <Card title="Giá trực tiếp" subtitle="chỉ hiển thị — không dùng cho phân tích">
          {liveBid != null ? (
            <>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
                <span className="mono" style={{ fontSize: 28, fontWeight: 700 }}>
                  {fmtPrice(liveBid)}
                </span>
                <Badge tone="success">LIVE</Badge>
              </div>
              <div className={styles.muted} style={{ fontSize: 11.5, marginTop: 4 }}>
                Ask {fmtPrice(tick.data?.ask)} · spread {tick.data?.spread} ·{' '}
                {tick.data?.age_seconds != null ? `${tick.data.age_seconds.toFixed(0)}s trước` : '—'}
              </div>
            </>
          ) : (
            <div className={styles.muted} style={{ fontSize: 13 }}>
              Chưa có tick trực tiếp. Giá nến đóng M15: <strong>{fmtPrice(m15?.close)}</strong>
            </div>
          )}
          <hr className={styles.rule} />
          <div className={`${styles.grid} ${styles.cols3}`} style={{ gap: 8 }}>
            {TIMEFRAMES.map((tf) => {
              const c = latest.data?.latest[tf];
              if (!c) return null;
              const pct = c.open ? ((c.close - c.open) / c.open) * 100 : 0;
              return (
                <div key={tf}>
                  <div className={styles.muted} style={{ fontSize: 10.5 }}>
                    {tf}
                  </div>
                  <div className="mono" style={{ fontSize: 13 }}>
                    {fmtPrice(c.close)}
                  </div>
                  <div
                    className="mono"
                    style={{
                      fontSize: 11,
                      color: pct >= 0 ? 'var(--status-ok)' : 'var(--status-danger)',
                    }}
                  >
                    {pct >= 0 ? '+' : ''}
                    {pct.toFixed(2)}%
                  </div>
                </div>
              );
            })}
          </div>
        </Card>

        <Card
          title="Sức khoẻ dữ liệu"
          subtitle={doneRun ? `phân bố theo run #${doneRun.id}` : 'chưa có run lịch sử'}
        >
          <div className={styles.stack} style={{ gap: 8 }}>
            {TIMEFRAMES.map((tf) => {
              const st = data.candles[tf];
              const f = data.data_freshness[tf];
              return (
                <div
                  key={tf}
                  style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12 }}
                >
                  <Badge tone="neutral">{tf}</Badge>
                  <span className="mono">{fmtNum(st?.count ?? 0, 0)}</span>
                  <span style={{ marginLeft: 'auto' }}>
                    <FreshnessPill
                      ageMinutes={f?.age_minutes}
                      stale={f?.stale}
                      thresholdMinutes={f?.threshold_minutes}
                    />
                  </span>
                </div>
              );
            })}
          </div>
          {duration.data && dominant && (
            <>
              <hr className={styles.rule} />
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <Badge tone="teal">{regimeShortLabel(dominant.key)}</Badge>
                <span className={styles.muted} style={{ fontSize: 11.5 }}>
                  chế độ chiếm nhiều nhất ·{' '}
                  {fmtNum(duration.data.regimes[dominant.key]?.occupancy_pct ?? 0, 1)}% thời gian
                </span>
              </div>
            </>
          )}
        </Card>
      </div>

      {/* ---------- Probabilities: one compact row ---------- */}
      <Card title="Xác suất chế độ" subtitle="HMM · Random Forest">
        <div className={styles.probCols}>
          <div className={styles.probCol}>
            <div className={styles.probTitle}>HMM</div>
            {hmmProbs.slice(0, 4).map(([label, v]) => (
              <ProbRow key={label} label={label} value={v} color={regimeColor(label)} />
            ))}
          </div>
          <div className={styles.probCol}>
            <div className={styles.probTitle}>Random Forest</div>
            {rfProbs.map(([label, v]) => (
              <ProbRow key={label} label={label} value={v} color={regimeColor(label)} />
            ))}
          </div>
        </div>
        {regime.reason_codes.length > 0 && (
          <div className={styles.chips} style={{ marginTop: 10 }}>
            {regime.reason_codes.map((code) => (
              <Badge key={code} tone="warning" title={code}>
                {reasonCodeLabel(code)}
              </Badge>
            ))}
          </div>
        )}
      </Card>

      {/* ---------- Everything diagnostic, collapsed ---------- */}
      <Section
        title="Chi tiết tín hiệu"
        summary={`model v${regime.model_version} · ${regime.feature_version} · ${regime.data_source}`}
      >
        <KV
          items={[
            { label: 'Khung thời gian', value: regime.timeframe },
            { label: 'Dữ liệu lúc', value: fmtUtc(regime.data_timestamp) },
            { label: 'Hết hạn', value: fmtUtc(regime.expiry) },
            { label: 'Model version', value: `v${regime.model_version}` },
            { label: 'Feature version', value: regime.feature_version },
            { label: 'Nguồn dữ liệu', value: regime.data_source },
          ]}
        />
        <div style={{ marginTop: 12 }}>
          <Notice tone="warn">
            <strong>Nghiên cứu — không phải lệnh giao dịch.</strong> Quyền{' '}
            {permissionLabel(regime.permission)} là đầu ra phân tích, không phải khuyến nghị
            mua/bán.
          </Notice>
        </div>
      </Section>

      <Section title="Đồng hồ đo độ tươi dữ liệu" summary="tuổi nến so với ngưỡng cảnh báo">
        <div className={styles.gaugesRowLocal}>
          {TIMEFRAMES.map((tf) => (
            <FreshnessGauge key={tf} tf={tf} info={data.data_freshness[tf]} />
          ))}
        </div>
      </Section>

      {duration.data && (
        <Section title="Phân bố chế độ thị trường" summary={doneRun ? `run #${doneRun.id}` : ''}>
          <RegimeDonut
            slices={REGIME_ORDER.map((r) => ({
              key: r.key,
              label: r.label,
              value: duration.data!.regimes[r.key]?.occupancy_pct ?? 0,
              color: r.color,
            }))}
            centerValue={dominant ? regimeShortLabel(dominant.key) : '—'}
            centerLabel="chế độ chính"
          />
          <div className={styles.muted} style={{ fontSize: 12, marginTop: 10 }}>
            {fmtNum(duration.data.total_transitions, 0)} lần chuyển chế độ trong toàn bộ dữ liệu.
          </div>
        </Section>
      )}

      <Section
        title="Đồng bộ dữ liệu gần nhất"
        summary={`${data.last_sync.length} bản ghi`}
      >
        {data.last_sync.length === 0 ? (
          <div className={styles.muted} style={{ fontSize: 12.5 }}>
            Chưa có lần đồng bộ nào.
          </div>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Collector</th>
                  <th>TF</th>
                  <th>Hoàn tất</th>
                  <th>Trạng thái</th>
                  <th className="num">Mới</th>
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
        )}
      </Section>

      <Section title="Mô hình đang hoạt động" summary={`${data.active_models.hmm.length + data.active_models.random_forest.length + data.active_models.trade_ens.length} model`}>
        <div className={`${styles.grid} ${styles.cols3}`}>
          <div>
            <div className={styles.probTitle}>HMM</div>
            {data.active_models.hmm.length === 0 ? (
              <div className={styles.muted}>Không có mô hình HMM hoạt động</div>
            ) : (
              data.active_models.hmm.map((m) => (
                <div key={`hmm-${m.id}`} className={styles.chips}>
                  <Badge tone="teal">hmm</Badge>
                  <span className="mono">
                    model {m.model_id ?? '—'} · v{m.version ?? '—'}
                  </span>
                </div>
              ))
            )}
          </div>
          <div>
            <div className={styles.probTitle}>Random Forest</div>
            {data.active_models.random_forest.length === 0 ? (
              <div className={styles.muted}>Không có mô hình RF hoạt động</div>
            ) : (
              data.active_models.random_forest.map((m) => (
                <div key={`rf-${m.id}`} className={styles.chips}>
                  <Badge tone="purple">random_forest</Badge>
                  <span className="mono">
                    model {m.model_id ?? '—'} · v{m.version ?? '—'}
                  </span>
                </div>
              ))
            )}
          </div>
          <div>
            <div className={styles.probTitle}>Trade Ens</div>
            {data.active_models.trade_ens.length === 0 ? (
              <div className={styles.muted}>Không có trade_ens hoạt động</div>
            ) : (
              data.active_models.trade_ens.map((m) => (
                <div key={`te-${m.id}`} className={styles.chips}>
                  <Badge tone="teal">trade_ens</Badge>
                  <span className="mono">
                    model {m.model_id ?? '—'} · v{m.version ?? '—'}
                  </span>
                  <Link href="/signals">chi tiết</Link>
                </div>
              ))
            )}
          </div>
        </div>
      </Section>

      <Section
        title="Báo cáo chất lượng dữ liệu"
        summary={`${data.last_quality_reports.length} báo cáo`}
      >
        {data.last_quality_reports.length === 0 ? (
          <div className={styles.muted} style={{ fontSize: 12.5 }}>
            Chưa có báo cáo chất lượng.
          </div>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>TF</th>
                  <th>Kiểm tra</th>
                  <th className="num">Tổng nến</th>
                  <th className="num">Thiếu</th>
                  <th className="num">Trùng</th>
                  <th className="num">Gap</th>
                  <th className="num">Lỗi</th>
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
                    <td>
                      {q.stale ? <Badge tone="danger">Cũ</Badge> : <Badge tone="success">OK</Badge>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>
    </div>
  );
}
