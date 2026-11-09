'use client';

import { useState } from 'react';
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
  PageHeader,
  StatusPill,
} from '@/components/ui/ui';
import { ApiError, api, downloadFile } from '@/lib/api';
import { fmtNum, fmtUtcSec, variantName } from '@/lib/format';
import { statusLabel } from '@/lib/regime';
import { useApi } from '@/lib/swr';
import type { ModelDetail, ModelListResponse, ModelRow, ModelStatus, VariantResult } from '@/lib/types';
import styles from '../pages.module.css';

interface NoticeState {
  tone: 'info' | 'warn' | 'danger';
  text: string;
}

function keyMetric(row: ModelRow): string {
  const m = row.metrics;
  if (m?.test_macro_f1 != null) return `F1 ${fmtNum(m.test_macro_f1, 4)}`;
  const combined = m?.variant_results?.combined;
  if (combined?.test_macro_f1 != null) return `F1 ${fmtNum(combined.test_macro_f1, 4)} (combined)`;
  if (m?.train_loglik != null) return `loglik ${fmtNum(m.train_loglik, 1)}`;
  return '—';
}

function artifactExt(modelType: string): string {
  return modelType === 'random_forest' ? 'joblib' : 'json';
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

function DetailPanel({ detail }: { detail: ModelDetail }) {
  const m = detail.metrics;
  return (
    <div className={styles.stack} style={{ padding: '4px 0 8px' }}>
      <KV
        items={[
          { label: 'Version ID', value: detail.version_id },
          { label: 'Model ID', value: detail.model_id },
          { label: 'Version', value: `v${detail.version}` },
          { label: 'Trạng thái', value: statusLabel(detail.status) },
          { label: 'Tạo lúc', value: fmtUtcSec(detail.created_at) },
          { label: 'Artifact', value: <span className="mono">{detail.artifact_path}</span> },
        ]}
      />
      {m && (
        <>
          <div className={styles.chips}>
            {m.chosen_variant && <Badge tone="teal">chosen: {variantName(m.chosen_variant)}</Badge>}
            {m.train_loglik != null && <Badge tone="neutral">train loglik: {fmtNum(m.train_loglik, 1)}</Badge>}
            {m.val_loglik != null && <Badge tone="neutral">val loglik: {fmtNum(m.val_loglik, 1)}</Badge>}
          </div>
          {m.engine_params && Object.keys(m.engine_params).length > 0 && (
            <div>
              <div className={styles.probTitle}>Engine params</div>
              <KV
                items={Object.entries(m.engine_params).map(([k, v]) => ({
                  label: k,
                  value: typeof v === 'number' ? fmtNum(v, 4) : String(v),
                }))}
              />
            </div>
          )}
          {m.variant_results && Object.keys(m.variant_results).length > 0 && (
            <div>
              <div className={styles.probTitle}>Variant results</div>
              <VariantTable results={m.variant_results} />
            </div>
          )}
          <div>
            <div className={styles.probTitle}>Toàn bộ metrics</div>
            <JsonBlock data={m} maxHeight={240} />
          </div>
        </>
      )}
    </div>
  );
}

export default function ModelsPage() {
  const { isAdmin } = useAuth();
  const [typeFilter, setTypeFilter] = useState('');
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [busy, setBusy] = useState<{ versionId: number; action: string } | null>(null);
  const [notice, setNotice] = useState<NoticeState | null>(null);

  const key = `/models?limit=100${typeFilter ? `&model_type=${encodeURIComponent(typeFilter)}` : ''}`;
  const { data, error, isLoading, mutate } = useApi<ModelListResponse>(key, {
    refreshInterval: 30000,
  });
  const detail = useApi<ModelDetail>(selectedId != null ? `/models/${selectedId}` : null, {
    refreshInterval: 30000,
  });

  async function changeStatus(versionId: number, status: ModelStatus) {
    if (busy) return;
    setBusy({ versionId, action: status });
    setNotice(null);
    try {
      const res = await api.setModelStatus(versionId, status, false);
      setNotice({
        tone: 'info',
        text: `Phiên bản #${res.version_id} → ${statusLabel(res.status)} (${res.status})`,
      });
      await Promise.all([mutate(), detail.data ? detail.mutate() : Promise.resolve()]);
    } catch (e) {
      setNotice({
        tone: 'danger',
        text:
          e instanceof ApiError
            ? `${e.message} (chuyển trạng thái bị chặn server-side?)`
            : 'Cập nhật trạng thái thất bại',
      });
    } finally {
      setBusy(null);
    }
  }

  async function onDownload(row: ModelRow) {
    setNotice(null);
    try {
      await downloadFile(
        `/models/${row.version_id}/download`,
        `gmrai-${row.model_type}-v${row.version}.${artifactExt(row.model_type)}`
      );
    } catch (e) {
      setNotice({
        tone: 'danger',
        text: e instanceof ApiError ? e.message : 'Tải artifact thất bại',
      });
    }
  }

  async function onDownloadOnnx(row: ModelRow) {
    setNotice(null);
    try {
      await downloadFile(`/models/${row.version_id}/onnx`, `gmrai-rf-v${row.version}.onnx`);
    } catch (e) {
      setNotice({
        tone: 'danger',
        text:
          e instanceof ApiError
            ? `${e.message} — ONNX có thể chưa được xuất cho phiên bản này`
            : 'Tải ONNX thất bại',
      });
    }
  }

  return (
    <div className={styles.stack}>
      <PageHeader
        title="Kho mô hình"
        subtitle="Quản lý phiên bản HMM và Random Forest (training → validating → candidate → approved/rejected/archived)"
      />

      {notice && <Notice tone={notice.tone}>{notice.text}</Notice>}

      <div className={styles.toolbar}>
        <label className={styles.small} style={{ color: 'var(--text-muted)' }}>
          Loại mô hình:{' '}
        </label>
        <select
          style={{
            background: 'var(--bg-elev)',
            border: '1px solid var(--border)',
            borderRadius: 8,
            color: 'var(--text)',
            padding: '6px 10px',
            fontSize: 13,
          }}
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value)}
        >
          <option value="">Tất cả</option>
          <option value="hmm">hmm</option>
          <option value="random_forest">random_forest</option>
        </select>
        <span className={styles.muted}>
          {data ? `${data.models.length} phiên bản` : ''}
        </span>
      </div>

      <Card title="Danh sách phiên bản mô hình">
        {isLoading && <Loading />}
        {error && <ErrorState error={error} />}
        {!isLoading && !error && data && data.models.length === 0 && (
          <EmptyState title="Không có phiên bản mô hình" hint="Hãy huấn luyện mô hình trước" />
        )}
        {data && data.models.length > 0 && (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Version ID</th>
                  <th>Loại</th>
                  <th>Model ID</th>
                  <th>Version</th>
                  <th>Trạng thái</th>
                  <th>Chỉ số chính</th>
                  <th>Tạo lúc (UTC)</th>
                  <th>Artifact</th>
                  <th>Hành động</th>
                </tr>
              </thead>
              <tbody>
                {data.models.map((row) => (
                  <tr key={row.version_id}>
                    <td className="mono">{row.version_id}</td>
                    <td>
                      <Badge tone={row.model_type === 'hmm' ? 'teal' : 'purple'}>
                        {row.model_type}
                      </Badge>
                    </td>
                    <td className="mono">{row.model_id}</td>
                    <td className="mono">v{row.version}</td>
                    <td>
                      <StatusPill status={row.status} />
                    </td>
                    <td className="mono">{keyMetric(row)}</td>
                    <td className="mono">{fmtUtcSec(row.created_at)}</td>
                    <td>{row.has_artifact ? <Badge tone="success">có</Badge> : <Badge tone="neutral">không</Badge>}</td>
                    <td>
                      <div className={styles.btnRow}>
                        <button
                          type="button"
                          className={styles.expandBtn}
                          onClick={() => setSelectedId(selectedId === row.version_id ? null : row.version_id)}
                        >
                          {selectedId === row.version_id ? 'Thu gọn' : 'Chi tiết'}
                        </button>
                        <Button size="sm" disabled={!row.has_artifact} onClick={() => void onDownload(row)}>
                          Tải artifact
                        </Button>
                        {row.model_type === 'random_forest' && (
                          <Button size="sm" onClick={() => void onDownloadOnnx(row)}>
                            ONNX
                          </Button>
                        )}
                        {isAdmin && row.status !== 'approved' && (
                          <Button
                            size="sm"
                            variant="primary"
                            disabled={busy != null}
                            onClick={() => void changeStatus(row.version_id, 'approved')}
                          >
                            {busy?.versionId === row.version_id && busy.action === 'approved'
                              ? '…'
                              : 'Duyệt'}
                          </Button>
                        )}
                        {isAdmin && row.status !== 'rejected' && row.status !== 'archived' && (
                          <Button
                            size="sm"
                            variant="danger"
                            disabled={busy != null}
                            onClick={() => void changeStatus(row.version_id, 'rejected')}
                          >
                            Từ chối
                          </Button>
                        )}
                        {isAdmin && row.status !== 'archived' && row.status !== 'training' && (
                          <Button
                            size="sm"
                            variant="ghost"
                            disabled={busy != null}
                            onClick={() => void changeStatus(row.version_id, 'archived')}
                          >
                            Lưu trữ
                          </Button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {!isAdmin && (
          <div style={{ marginTop: 12 }}>
            <Notice tone="info">Cần quyền admin để duyệt / từ chối / lưu trữ mô hình.</Notice>
          </div>
        )}
      </Card>

      {selectedId != null && (
        <Card title={`Chi tiết phiên bản #${selectedId}`} subtitle={detail.data?.artifact_path}>
          {detail.isLoading && <Loading />}
          {detail.error && <ErrorState error={detail.error} />}
          {detail.data && <DetailPanel detail={detail.data} />}
        </Card>
      )}
    </div>
  );
}
