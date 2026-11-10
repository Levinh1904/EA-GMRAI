'use client';

import { useEffect, useMemo, useState } from 'react';
import { useAuth } from '@/components/AuthProvider';
import { Button, EmptyState, ErrorState, Loading, Notice, PageHeader, StatusPill } from '@/components/ui/ui';
import { api } from '@/lib/api';
import { fmtNum, fmtUtc } from '@/lib/format';
import { useApi } from '@/lib/swr';
import type { HistoryRun, HistoryRunListResponse } from '@/lib/types';
import styles from '../pages.module.css';
import hstyles from './history.module.css';
import OverviewTab from './tabs/OverviewTab';
import TimelineTab from './tabs/TimelineTab';
import TrendsTab from './tabs/TrendsTab';
import SidewaysTab from './tabs/SidewaysTab';
import EarlyTrendTab from './tabs/EarlyTrendTab';
import SegmentsTab from './tabs/SegmentsTab';
import TransitionsTab from './tabs/TransitionsTab';
import MultiTfTab from './tabs/MultiTfTab';
import CompareTab from './tabs/CompareTab';
import ReferenceCompareTab from './tabs/ReferenceCompareTab';
import OutcomesTab from './tabs/OutcomesTab';
import ReportsTab from './tabs/ReportsTab';

export type HistoryTabKey =
  | 'overview'
  | 'timeline'
  | 'trends'
  | 'sideways'
  | 'early'
  | 'segments'
  | 'transitions'
  | 'multitf'
  | 'compare'
  | 'reference'
  | 'outcomes'
  | 'reports';

const TABS: Array<{ key: HistoryTabKey; label: string }> = [
  { key: 'overview', label: 'Tổng quan lịch sử' },
  { key: 'timeline', label: 'Timeline lịch sử' },
  { key: 'trends', label: 'Phân tích xu hướng' },
  { key: 'sideways', label: 'Phân tích Sideways' },
  { key: 'early', label: 'Early Trend' },
  { key: 'segments', label: 'Danh sách Segments' },
  { key: 'transitions', label: 'Ma trận chuyển trạng thái' },
  { key: 'multitf', label: 'Đa khung thời gian' },
  { key: 'compare', label: 'So sánh mô hình' },
  { key: 'reference', label: 'So sánh Reference' },
  { key: 'outcomes', label: 'Kết quả tương lai' },
  { key: 'reports', label: 'Báo cáo & Xuất' },
];

interface Toast {
  tone: 'success' | 'danger' | 'info';
  text: string;
}

export default function HistoryPage() {
  const { user } = useAuth();
  const [tab, setTab] = useState<HistoryTabKey>('overview');
  const [selectedRunId, setSelectedRunId] = useState<number | null>(null);
  const [toast, setToast] = useState<Toast | null>(null);
  const [scheduling, setScheduling] = useState(false);

  const runs = useApi<HistoryRunListResponse>('/history/runs?limit=20');
  const runList = runs.data?.runs ?? [];

  const anyActive = useMemo(
    () => runList.some((r) => r.status === 'running' || r.status === 'pending'),
    [runList]
  );

  // Poll every 4s while any run is being processed.
  const { mutate } = runs;
  useEffect(() => {
    if (!anyActive) return;
    const t = setInterval(() => {
      void mutate();
    }, 4000);
    return () => clearInterval(t);
  }, [anyActive, mutate]);

  // Auto-select: newest "done" run, else newest run.
  useEffect(() => {
    if (selectedRunId != null && runList.some((r) => r.id === selectedRunId)) return;
    if (runList.length === 0) return;
    const done = runList.find((r) => r.status === 'done');
    setSelectedRunId((done ?? runList[0]).id);
  }, [runList, selectedRunId]);

  // Auto-dismiss toast.
  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 5000);
    return () => clearTimeout(t);
  }, [toast]);

  const activeRun = useMemo(
    () => runList.find((r) => r.id === selectedRunId) ?? null,
    [runList, selectedRunId]
  );

  async function scheduleRun() {
    if (scheduling) return;
    setScheduling(true);
    try {
      const resp = await api.startHistoryRun();
      setToast({ tone: 'success', text: `Đã lên lịch chạy phân tích — run_id ${resp.run_id}` });
      setSelectedRunId(resp.run_id);
      await mutate();
    } catch (e) {
      setToast({
        tone: 'danger',
        text: e instanceof Error ? e.message : 'Không thể lên lịch chạy phân tích',
      });
    } finally {
      setScheduling(false);
    }
  }

  return (
    <div className={styles.stack}>
      <PageHeader
        title="Lịch sử Regime"
        subtitle="Historical Market Regime Analyzer — phân tích hồi cứu 1 năm dữ liệu XAUUSD M15"
        right={
          <div className={styles.toolbar} style={{ marginBottom: 0 }}>
            <label className={styles.small} style={{ color: 'var(--text-muted)' }}>
              Run:
            </label>
            <select
              className={hstyles.select}
              value={selectedRunId ?? ''}
              onChange={(e) => setSelectedRunId(e.target.value ? Number(e.target.value) : null)}
              disabled={runList.length === 0}
            >
              {runList.map((r) => (
                <option key={r.id} value={r.id}>
                  #{r.id} · {r.symbol} {r.timeframe} · {r.status} · {r.bar_count ?? '—'} bars
                </option>
              ))}
            </select>
            {user?.role === 'admin' && (
              <Button onClick={scheduleRun} disabled={scheduling}>
                {scheduling ? 'Đang lên lịch…' : 'Chạy phân tích mới'}
              </Button>
            )}
          </div>
        }
      />

      {toast && (
        <div
          className={`${hstyles.toast} ${
            toast.tone === 'danger'
              ? hstyles.toastDanger
              : toast.tone === 'success'
                ? hstyles.toastSuccess
                : ''
          }`}
          role="status"
        >
          {toast.text}
        </div>
      )}

      {runs.isLoading && <Loading label="Đang tải danh sách run…" />}

      {runs.error && (
        <ErrorState
          error={runs.error}
          title="Không thể tải danh sách run lịch sử"
          onRetry={() => void mutate()}
        />
      )}

      {!runs.isLoading && !runs.error && runList.length === 0 && (
        <EmptyState
          title="Chưa có run phân tích lịch sử nào"
          hint={
            user?.role === 'admin'
              ? 'Bấm “Chạy phân tích mới” ở góc phải để lên lịch run đầu tiên (POST /history/run).'
              : 'Hãy yêu cầu quản trị viên chạy POST /history/run để tạo run phân tích lịch sử.'
          }
        />
      )}

      {!runs.isLoading && !runs.error && activeRun && (
        <>
          <div className={hstyles.runInfoBar}>
            <StatusPill status={activeRun.status} />
            <span className={hstyles.mono}>
              #{activeRun.id} · {activeRun.symbol} {activeRun.timeframe} · nguồn{' '}
              {activeRun.data_source ?? '—'}
            </span>
            <span className={hstyles.mono}>
              {fmtNum(activeRun.bar_count, 0)} bars · {fmtNum(activeRun.segment_count, 0)} segments
            </span>
            <span className={hstyles.mono}>
              {fmtUtc(activeRun.data_start)} → {fmtUtc(activeRun.data_end)}
            </span>
            <span className={hstyles.mono}>
              HMM v{activeRun.hmm_model_version_id ?? '—'} · RF v{activeRun.rf_model_version_id ?? '—'}
            </span>
            {anyActive && (
              <span className={hstyles.pulse}>
                <span className={hstyles.pulseDot} />
                đang xử lý… tự động cập nhật 4 giây
              </span>
            )}
          </div>

          {activeRun.status === 'failed' && activeRun.error && (
            <Notice tone="danger">
              Run #{activeRun.id} thất bại: {activeRun.error}
            </Notice>
          )}

          {(activeRun.status === 'running' || activeRun.status === 'pending') && (
            <Notice tone="info">
              Run #{activeRun.id} đang được xử lý — các tab hiển thị dữ liệu hiện có và tự động làm
              mới khi run hoàn tất.
            </Notice>
          )}

          <div className={hstyles.tabs} role="tablist">
            {TABS.map((t) => (
              <button
                key={t.key}
                type="button"
                role="tab"
                aria-selected={tab === t.key}
                className={`${hstyles.tabBtn} ${tab === t.key ? hstyles.tabBtnActive : ''}`}
                onClick={() => setTab(t.key)}
              >
                {t.label}
              </button>
            ))}
          </div>

          <div className={hstyles.tabPanel}>
            {tab === 'overview' && <OverviewTab run={activeRun} runId={activeRun.id} />}
            {tab === 'timeline' && <TimelineTab run={activeRun} runId={activeRun.id} />}
            {tab === 'trends' && <TrendsTab runId={activeRun.id} />}
            {tab === 'sideways' && <SidewaysTab runId={activeRun.id} />}
            {tab === 'early' && <EarlyTrendTab runId={activeRun.id} />}
            {tab === 'segments' && <SegmentsTab run={activeRun} runId={activeRun.id} />}
            {tab === 'transitions' && <TransitionsTab runId={activeRun.id} />}
            {tab === 'multitf' && <MultiTfTab runId={activeRun.id} />}
            {tab === 'compare' && <CompareTab runId={activeRun.id} runs={runList} />}
            {tab === 'reference' && <ReferenceCompareTab runId={activeRun.id} />}
            {tab === 'outcomes' && <OutcomesTab runId={activeRun.id} />}
            {tab === 'reports' && <ReportsTab run={activeRun} runId={activeRun.id} />}
          </div>

          {activeRun.data_end && (
            <div className={styles.muted} style={{ fontSize: 12 }}>
              Dữ liệu của run kết thúc tại {fmtUtc(activeRun.data_end)} — số liệu là ảnh chụp lịch
              sử, không tự cập nhật theo thời gian thực. Múi giờ hiển thị: UTC.
            </div>
          )}
        </>
      )}

      {!runs.isLoading && !runs.error && runList.length > 0 && !activeRun && (
        <ErrorState title="Không chọn được run" error="Không tìm thấy run đã chọn trong danh sách." />
      )}
    </div>
  );
}
