'use client';

import { Fragment, useState } from 'react';
import { useAuth } from '@/components/AuthProvider';
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorState,
  JsonBlock,
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
  TrainingRun,
  TrainingRunListResponse,
  TrainingStartRequest,
  VariantResult,
} from '@/lib/types';
import styles from '../pages.module.css';

interface NoticeState {
  tone: 'info' | 'warn' | 'danger';
  text: string;
}

function VariantTable({ results }: { results: Record<string, VariantResult> }) {
  return (
    <div className="table-wrap">
      <table className="table">
        <thead>
          <tr>
            <th>Biến thể</th>
            <th className="num">Validation opt</th>
            <th className="num">Test macro F1</th>
            <th className="num">Test accuracy</th>
            <th className="num">False trend rate</th>
          </tr>
        </thead>
        <tbody>
          {Object.entries(results).map(([variant, v]) => (
            <tr key={variant}>
              <td>{variantName(variant)}</td>
              <td className="num">{fmtNum(v.validation_opt_score, 4)}</td>
              <td className="num">{fmtNum(v.test_macro_f1, 4)}</td>
              <td className="num">{fmtNum(v.test_accuracy, 4)}</td>
              <td className="num">{fmtNum(v.false_trend_rate, 4)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function RunDetail({ run }: { run: TrainingRun }) {
  const m = run.metrics;
  return (
    <div className={styles.stack} style={{ padding: '4px 0 8px' }}>
      {run.error && <Notice tone="danger">{run.error}</Notice>}
      <KV
        items={[
          { label: 'Bắt đầu', value: fmtUtcSec(run.started_at) },
          { label: 'Kết thúc', value: fmtUtcSec(run.finished_at) },
          { label: 'Thời lượng', value: fmtDuration(run.started_at, run.finished_at) },
        ]}
      />
      {run.params && Object.keys(run.params).length > 0 && (
        <KV
          items={Object.entries(run.params).map(([k, v]) => ({
            label: k,
            value: typeof v === 'number' ? fmtNum(v, 4) : String(v),
          }))}
        />
      )}
      {m && (
        <>
          <div className={styles.chips}>
            {m.chosen_variant && <Badge tone="teal">chosen: {variantName(m.chosen_variant)}</Badge>}
            {m.auto_approved != null && (
              <Badge tone={m.auto_approved ? 'success' : 'neutral'}>
                auto_approved: {String(m.auto_approved)}
              </Badge>
            )}
            {m.hmm_model_id != null && <Badge tone="teal">hmm_model_id: {m.hmm_model_id}</Badge>}
            {m.rf_model_id != null && <Badge tone="purple">rf_model_id: {m.rf_model_id}</Badge>}
          </div>
          {m.variant_results && Object.keys(m.variant_results).length > 0 && (
            <div>
              <div className={styles.probTitle}>Variant results</div>
              <VariantTable results={m.variant_results} />
            </div>
          )}
          {m.state_mapping != null && (
            <div>
              <div className={styles.probTitle}>State mapping</div>
              <JsonBlock data={m.state_mapping} maxHeight={220} />
            </div>
          )}
          {m.onnx_parity != null && (
            <div>
              <div className={styles.probTitle}>ONNX parity</div>
              <JsonBlock data={m.onnx_parity} maxHeight={220} />
            </div>
          )}
        </>
      )}
    </div>
  );
}

export default function TrainingPage() {
  const { isAdmin } = useAuth();
  const [params, setParams] = useState<TrainingStartRequest>({
    hmm_n_states: 5,
    hmm_n_init: 10,
    seed: 42,
    train_frac: 0.7,
    val_frac: 0.15,
    rf_horizon: 12,
    up_threshold_atr: 0.75,
    weight_hmm: 0.5,
  });
  const [submitting, setSubmitting] = useState(false);
  const [notice, setNotice] = useState<NoticeState | null>(null);
  const [expandedId, setExpandedId] = useState<number | null>(null);

  const { data, error, isLoading, mutate } = useApi<TrainingRunListResponse>(
    '/training/runs?limit=20',
    {
      refreshInterval: (latest) =>
        latest?.runs?.some((r) => r.status === 'scheduled' || r.status === 'running') ? 4000 : 15000,
    }
  );

  function setParam(key: keyof TrainingStartRequest, value: number) {
    setParams((prev) => ({ ...prev, [key]: value }));
  }

  async function startTraining() {
    if (submitting) return;
    setSubmitting(true);
    setNotice(null);
    try {
      const res = await api.startTraining(params);
      setNotice({
        tone: 'info',
        text: `Đã lên lịch huấn luyện — job #${res.job_id} (trạng thái: ${res.status}). Danh sách sẽ tự cập nhật.`,
      });
      await mutate();
    } catch (e) {
      setNotice({
        tone: 'danger',
        text: e instanceof ApiError ? e.message : 'Không thể khởi động huấn luyện',
      });
    } finally {
      setSubmitting(false);
    }
  }

  const activeCount = data?.runs?.filter(
    (r) => r.status === 'scheduled' || r.status === 'running'
  ).length;

  return (
    <div className={styles.stack}>
      <PageHeader
        title="Trung tâm huấn luyện"
        subtitle="Huấn luyện HMM + Random Forest cho XAUUSD"
        right={activeCount ? <Badge tone="info">{activeCount} job đang chạy</Badge> : undefined}
      />

      {notice && <Notice tone={notice.tone}>{notice.text}</Notice>}

      <Card
        title="Khởi động huấn luyện mới"
        subtitle="Tham số mặc định theo cấu hình production (weight_hmm 0.5, 5 trạng thái HMM)"
      >
        {!isAdmin && (
          <Notice tone="warn">
            Cần quyền <strong>admin</strong> để khởi động huấn luyện. Bạn chỉ có thể xem danh sách
            job.
          </Notice>
        )}
        <div className={styles.formGrid}>
          <NumberField
            label="hmm_n_states"
            value={params.hmm_n_states ?? 5}
            onChange={(v) => setParam('hmm_n_states', v)}
            step={1}
            min={2}
            hint="Số trạng thái ẩn HMM"
          />
          <NumberField
            label="hmm_n_init"
            value={params.hmm_n_init ?? 10}
            onChange={(v) => setParam('hmm_n_init', v)}
            step={1}
            min={1}
            hint="Số lần khởi tạo"
          />
          <NumberField
            label="seed"
            value={params.seed ?? 42}
            onChange={(v) => setParam('seed', v)}
            step={1}
            hint="Hạt ngẫu nhiên"
          />
          <NumberField
            label="train_frac"
            value={params.train_frac ?? 0.7}
            onChange={(v) => setParam('train_frac', v)}
            step={0.05}
            min={0.1}
            max={0.95}
            hint="Tỷ lệ dữ liệu train"
          />
          <NumberField
            label="val_frac"
            value={params.val_frac ?? 0.15}
            onChange={(v) => setParam('val_frac', v)}
            step={0.05}
            min={0.01}
            max={0.5}
            hint="Tỷ lệ dữ liệu validation"
          />
          <NumberField
            label="rf_horizon"
            value={params.rf_horizon ?? 12}
            onChange={(v) => setParam('rf_horizon', v)}
            step={1}
            min={1}
            hint="Horizon nhãn Random Forest (số nến)"
          />
          <NumberField
            label="up_threshold_atr"
            value={params.up_threshold_atr ?? 0.75}
            onChange={(v) => setParam('up_threshold_atr', v)}
            step={0.05}
            min={0}
            hint="Ngưỡng ATR cho xu hướng lên"
          />
          <NumberField
            label="weight_hmm"
            value={params.weight_hmm ?? 0.5}
            onChange={(v) => setParam('weight_hmm', v)}
            step={0.05}
            min={0}
            max={1}
            hint="Trọng số HMM trong ensemble"
          />
        </div>
        <div className={styles.formActions}>
          <Button variant="primary" onClick={startTraining} disabled={!isAdmin || submitting}>
            {submitting ? 'Đang gửi…' : 'Bắt đầu huấn luyện (admin)'}
          </Button>
          <span className={styles.muted}>
            POST /training/run · job chạy bất đồng bộ, polling trạng thái tự động
          </span>
        </div>
      </Card>

      <Card
        title="Danh sách lượt huấn luyện"
        subtitle="tự cập nhật mỗi 4 giây khi có job đang chạy"
      >
        {isLoading && <Loading />}
        {error && <ErrorState error={error} />}
        {!isLoading && !error && data && data.runs.length === 0 && (
          <EmptyState
            title="Chưa có lượt huấn luyện nào"
            hint="Dùng form phía trên để lên lịch lượt đầu tiên"
          />
        )}
        {data && data.runs.length > 0 && (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Loại mô hình</th>
                  <th>Features</th>
                  <th>Trạng thái</th>
                  <th>Bắt đầu (UTC)</th>
                  <th>Kết thúc (UTC)</th>
                  <th>Thời lượng</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {data.runs.map((run) => (
                  <Fragment key={run.id}>
                    <tr>
                      <td className="mono">{run.id}</td>
                      <td className="mono">{run.model_type}</td>
                      <td className="mono">{run.feature_version}</td>
                      <td>
                        <StatusPill status={run.status} />
                      </td>
                      <td className="mono">{fmtUtcSec(run.started_at)}</td>
                      <td className="mono">{fmtUtcSec(run.finished_at)}</td>
                      <td className="mono">{fmtDuration(run.started_at, run.finished_at)}</td>
                      <td>
                        <button
                          type="button"
                          className={styles.expandBtn}
                          onClick={() => setExpandedId(expandedId === run.id ? null : run.id)}
                        >
                          {expandedId === run.id ? 'Thu gọn' : 'Kết quả'}
                        </button>
                      </td>
                    </tr>
                    {expandedId === run.id && (
                      <tr key={`${run.id}-detail`}>
                        <td colSpan={8} style={{ background: 'var(--bg-elev)' }}>
                          <RunDetail run={run} />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
