'use client';

import dynamic from 'next/dynamic';
import { useState } from 'react';
import { useAuth } from '@/components/AuthProvider';
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorState,
  Field,
  KV,
  Loading,
  Notice,
  NumberField,
  PageHeader,
  StatusPill,
} from '@/components/ui/ui';
import { ApiError, api } from '@/lib/api';
import { fmtDuration, fmtNum, fmtUtcSec, variantName } from '@/lib/format';
import { useApi } from '@/lib/swr';
import type {
  BacktestListResponse,
  BacktestRun,
  BacktestStartRequest,
  VariantComparison,
} from '@/lib/types';
import styles from '../pages.module.css';

const VariantCompareChart = dynamic(() => import('@/components/charts/VariantCompareChart'), {
  ssr: false,
  loading: () => <Loading label="Đang tải biểu đồ so sánh…" />,
});

interface NoticeState {
  tone: 'info' | 'warn' | 'danger';
  text: string;
}

function comparisonTable(variant_comparison: Record<string, VariantComparison>) {
  return Object.entries(variant_comparison).map(([variant, v]) => ({
    variant,
    f1Mean: v.macro_f1?.mean ?? 0,
    f1Std: v.macro_f1?.std ?? 0,
    ftrMean: v.false_trend_rate?.mean ?? 0,
    ftrStd: v.false_trend_rate?.std ?? 0,
  }));
}

function RunDetail({ run }: { run: BacktestRun }) {
  const m = run.metrics;
  const rows = m?.variant_comparison ? comparisonTable(m.variant_comparison) : [];
  return (
    <div className={styles.stack}>
      {run.error && <Notice tone="danger">{run.error}</Notice>}
      {m && (
        <div className={styles.chips}>
          <Badge tone="neutral">n_folds: {m.n_folds ?? '—'}</Badge>
          {m.chosen_variant && <Badge tone="teal">chosen: {variantName(m.chosen_variant)}</Badge>}
        </div>
      )}
      {rows.length > 0 && (
        <>
          <div className={styles.chartBox}>
            <VariantCompareChart rows={rows} height={340} />
          </div>
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Biến thể</th>
                  <th className="num">Macro F1 (mean ± std)</th>
                  <th className="num">False trend rate (mean ± std)</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.variant}>
                    <td>{variantName(r.variant)}</td>
                    <td className="num">
                      {fmtNum(r.f1Mean, 4)} ± {fmtNum(r.f1Std, 4)}
                    </td>
                    <td className="num">
                      {fmtNum(r.ftrMean, 4)} ± {fmtNum(r.ftrStd, 4)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
      <KV
        items={[
          { label: 'Bắt đầu', value: fmtUtcSec(run.started_at) },
          { label: 'Kết thúc', value: fmtUtcSec(run.finished_at) },
          { label: 'Thời lượng', value: fmtDuration(run.started_at, run.finished_at) },
        ]}
      />
      <KV
        items={Object.entries(run.config).map(([k, v]) => ({
          label: k,
          value: v == null ? 'null' : typeof v === 'number' ? fmtNum(v, 4) : String(v),
        }))}
      />
      <Notice tone="info">
        Báo cáo walk-forward chi tiết được lưu server-side trong artifacts; API chỉ trả về tóm tắt
        metrics (n_folds, variant_comparison, chosen_variant).
      </Notice>
    </div>
  );
}

export default function BacktestingPage() {
  const { isAdmin } = useAuth();
  const [form, setForm] = useState<BacktestStartRequest>({
    name: 'demo-wf',
    initial_train: 5000,
    test_size: 500,
    embargo: 12,
    hmm_n_states: 5,
    hmm_n_init: 10,
    rf_horizon: 12,
    up_threshold_atr: 0.75,
    cost_usd: 30,
    max_hold: 24,
  });
  const [submitting, setSubmitting] = useState(false);
  const [notice, setNotice] = useState<NoticeState | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);

  const { data, error, isLoading, mutate } = useApi<BacktestListResponse>('/backtests?limit=20', {
    refreshInterval: (latest) =>
      latest?.runs?.some((r) => r.status === 'scheduled' || r.status === 'running') ? 4000 : 15000,
  });

  const detail = useApi<BacktestRun>(selectedId != null ? `/backtests/${selectedId}` : null, {
    refreshInterval: (latest) =>
      latest && (latest.status === 'scheduled' || latest.status === 'running') ? 4000 : 0,
  });

  function setField(key: keyof BacktestStartRequest, value: number | string) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  async function startBacktest() {
    if (submitting) return;
    setSubmitting(true);
    setNotice(null);
    try {
      const res = await api.startBacktest(form);
      setNotice({
        tone: 'info',
        text: `Đã lên lịch backtest — job #${res.job_id} (trạng thái: ${res.status}). Danh sách sẽ tự cập nhật.`,
      });
      await mutate();
    } catch (e) {
      setNotice({
        tone: 'danger',
        text: e instanceof ApiError ? e.message : 'Không thể khởi động backtest',
      });
    } finally {
      setSubmitting(false);
    }
  }

  const activeCount = data?.runs?.filter(
    (r) => r.status === 'scheduled' || r.status === 'running'
  ).length;
  const selected = detail.data;

  return (
    <div className={styles.stack}>
      <PageHeader
        title="Backtesting"
        subtitle="Walk-forward validation đa biến thể: HMM-only vs RF-only vs HMM+RF"
        right={activeCount ? <Badge tone="info">{activeCount} job đang chạy</Badge> : undefined}
      />

      {notice && <Notice tone={notice.tone}>{notice.text}</Notice>}

      <Card
        title="Khởi động backtest mới"
        subtitle="Cấu hình walk-forward (theo mặc định production)"
      >
        {!isAdmin && (
          <Notice tone="warn">
            Cần quyền <strong>admin</strong> để khởi động backtest.
          </Notice>
        )}
        <div className={styles.formGrid}>
          <Field label="name">
            <input
              style={{
                background: 'var(--bg-elev)',
                border: '1px solid var(--border)',
                borderRadius: 8,
                color: 'var(--text)',
                padding: '7px 10px',
                fontSize: 13,
                width: '100%',
              }}
              value={form.name}
              onChange={(e) => setField('name', e.target.value)}
            />
          </Field>
          <NumberField
            label="initial_train"
            value={form.initial_train}
            onChange={(v) => setField('initial_train', v)}
            step={500}
            min={100}
          />
          <NumberField
            label="test_size"
            value={form.test_size}
            onChange={(v) => setField('test_size', v)}
            step={50}
            min={50}
          />
          <NumberField
            label="embargo"
            value={form.embargo}
            onChange={(v) => setField('embargo', v)}
            step={1}
            min={0}
            hint="Nến cách ly giữa train/test"
          />
          <NumberField
            label="hmm_n_states"
            value={form.hmm_n_states}
            onChange={(v) => setField('hmm_n_states', v)}
            step={1}
            min={2}
          />
          <NumberField
            label="hmm_n_init"
            value={form.hmm_n_init}
            onChange={(v) => setField('hmm_n_init', v)}
            step={1}
            min={1}
          />
          <NumberField
            label="rf_horizon"
            value={form.rf_horizon}
            onChange={(v) => setField('rf_horizon', v)}
            step={1}
            min={1}
          />
          <NumberField
            label="up_threshold_atr"
            value={form.up_threshold_atr}
            onChange={(v) => setField('up_threshold_atr', v)}
            step={0.05}
            min={0}
          />
          <NumberField
            label="cost_usd"
            value={form.cost_usd}
            onChange={(v) => setField('cost_usd', v)}
            step={1}
            min={0}
            hint="Phí giao dịch (USD)"
          />
          <NumberField
            label="max_hold"
            value={form.max_hold}
            onChange={(v) => setField('max_hold', v)}
            step={1}
            min={1}
            hint="Thời gian giữ lệnh tối đa (nến)"
          />
        </div>
        <div className={styles.formActions}>
          <Button variant="primary" onClick={startBacktest} disabled={!isAdmin || submitting}>
            {submitting ? 'Đang gửi…' : 'Bắt đầu backtest (admin)'}
          </Button>
          <span className={styles.muted}>
            POST /backtests · polling trạng thái tự động tới khi done/failed
          </span>
        </div>
      </Card>

      <Card title="Danh sách backtest" subtitle="bấm vào dòng để xem chi tiết">
        {isLoading && <Loading />}
        {error && <ErrorState error={error} />}
        {!isLoading && !error && data && data.runs.length === 0 && (
          <EmptyState title="Chưa có backtest nào" hint="Dùng form phía trên để chạy lần đầu" />
        )}
        {data && data.runs.length > 0 && (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Tên</th>
                  <th>Trạng thái</th>
                  <th className="num">Folds</th>
                  <th>Chosen variant</th>
                  <th>Kết thúc (UTC)</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {data.runs.map((run) => (
                  <tr
                    key={run.id}
                    onClick={() => setSelectedId(selectedId === run.id ? null : run.id)}
                    style={{ cursor: 'pointer' }}
                  >
                    <td className="mono">{run.id}</td>
                    <td className="mono">{run.name}</td>
                    <td>
                      <StatusPill status={run.status} />
                    </td>
                    <td className="num">{run.metrics?.n_folds ?? '—'}</td>
                    <td>
                      {run.metrics?.chosen_variant ? (
                        <Badge tone="teal">{variantName(run.metrics.chosen_variant)}</Badge>
                      ) : (
                        '—'
                      )}
                    </td>
                    <td className="mono">{fmtUtcSec(run.finished_at)}</td>
                    <td>
                      <button
                        type="button"
                        className={styles.expandBtn}
                        onClick={(e) => {
                          e.stopPropagation();
                          setSelectedId(selectedId === run.id ? null : run.id);
                        }}
                      >
                        {selectedId === run.id ? 'Thu gọn' : 'Chi tiết'}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {selectedId != null && (
        <Card
          title={`Chi tiết backtest #${selectedId}`}
          subtitle={selected ? `${selected.name} · ${selected.config.test_size ?? '—'} nến test/fold` : 'đang tải…'}
        >
          {detail.isLoading && <Loading />}
          {detail.error && <ErrorState error={detail.error} />}
          {selected && <RunDetail run={selected} />}
        </Card>
      )}
    </div>
  );
}
