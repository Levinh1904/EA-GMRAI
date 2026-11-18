'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useAuth } from '@/components/AuthProvider';
import { Button, EmptyState, ErrorState, Loading, Notice, PageHeader, StatusPill } from '@/components/ui/ui';
import { api } from '@/lib/api';
import { fmtNum, fmtUtc } from '@/lib/format';
import { useApi } from '@/lib/swr';
import type { HistoryRun, HistoryRunListResponse } from '@/lib/types';
import { HistoryFiltersBar } from './HistoryFiltersBar';
import { DEFAULT_FILTERS, dayRangeToUtc, type HistoryFilters } from './filters';
import styles from '../pages.module.css';
import hstyles from './history.module.css';
import OverviewTab from './tabs/OverviewTab';
import TimelineTab from './tabs/TimelineTab';
import TrendsTab from './tabs/TrendsTab';
import DirectionAccuracyTab from './tabs/DirectionAccuracyTab';
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
  | 'direction'
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
  { key: 'direction', label: 'Độ chính xác hướng' },
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

const TAB_KEYS = new Set<string>(TABS.map((t) => t.key));

const ENTRY_HOURS = Array.from({ length: 24 }, (_, i) => i);
const GOOD_ENTRY_HOURS = [6, 8, 14, 17];

function formatEntryHours(hours?: number[] | null): string {
  if (hours == null) return 'Theo model';
  if (hours.length === 0 || hours.length === 24) return 'Tất cả';
  return hours.map((h) => String(h).padStart(2, '0')).join(', ');
}

interface Toast {
  tone: 'success' | 'danger' | 'info';
  text: string;
}

export default function HistoryPage() {
  const { user } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const tabParam = searchParams?.get('tab') ?? null;

  const [tab, setTab] = useState<HistoryTabKey>('overview');
  const [selectedRunId, setSelectedRunId] = useState<number | null>(null);
  const [toast, setToast] = useState<Toast | null>(null);
  const [scheduling, setScheduling] = useState(false);

  // Global filters (date range / regime mode) + model version picker.
  const [filters, setFilters] = useState<HistoryFilters>(DEFAULT_FILTERS);
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [modelVersionId, setModelVersionId] = useState('');
  // UTC entry hours for the NEXT history run. The engine only opens new trends
  // in these hours; existing trends may run past the window.
  const [selectedHours, setSelectedHours] = useState<number[]>(GOOD_ENTRY_HOURS);

  const toggleHour = useCallback((h: number) => {
    setSelectedHours((prev) =>
      prev.includes(h) ? prev.filter((x) => x !== h) : [...prev, h].sort((a, b) => a - b)
    );
  }, []);

  const runs = useApi<HistoryRunListResponse>('/history/runs?limit=20');
  const runList = runs.data?.runs ?? [];

  // Deep-link support: /history?tab=reference (sidebar "So sánh Reference").
  useEffect(() => {
    if (tabParam && TAB_KEYS.has(tabParam)) setTab(tabParam as HistoryTabKey);
  }, [tabParam]);

  const selectTab = useCallback(
    (next: HistoryTabKey) => {
      setTab(next);
      router.replace(`/history?tab=${next}`, { scroll: false });
    },
    [router]
  );

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

  // Date inputs → normalized UTC day range in the filters state.
  useEffect(() => {
    setFilters((prev) => {
      const range = dayRangeToUtc(startDate || null, endDate || null);
      return {
        ...prev,
        start: range?.start ?? null,
        end: range?.end ?? null,
      };
    });
  }, [startDate, endDate]);

  function handleModelVersion(value: string) {
    setModelVersionId(value);
    const id = value ? Number(value) : null;
    if (id == null) return;
    const match = runList.find(
      (r) => r.hmm_model_version_id === id && r.status === 'done'
    ) ?? runList.find((r) => r.hmm_model_version_id === id);
    if (match) {
      setSelectedRunId(match.id);
      setToast({
        tone: 'info',
        text: `Đã chuyển sang run #${match.id} (HMM v${id})`,
      });
    } else {
      setToast({
        tone: 'danger',
        text: `Không có run lịch sử nào dùng mô hình HMM v${id}.`,
      });
    }
  }

  async function scheduleRun() {
    if (scheduling) return;
    setScheduling(true);
    try {
      const resp = await api.startHistoryRun({ hours: selectedHours });
      setToast({
        tone: 'success',
        text: `Đã lên lịch chạy phân tích với giờ entry ${formatEntryHours(selectedHours)} (UTC) — run_id ${resp.run_id}`,
      });
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
              <Button onClick={scheduleRun} disabled={scheduling} title="Tạo run mới với các giờ entry đã chọn">
                {scheduling ? 'Đang lên lịch…' : 'Chạy lại với giờ đã chọn'}
              </Button>
            )}
          </div>
        }
      />

      {user?.role === 'admin' ? (
        <div className={hstyles.sessionFilter}>
          <div className={hstyles.sessionHead}>
            <span className={hstyles.filterLabel}>Giờ entry cho lần chạy mới (UTC)</span>
            <span className={hstyles.sessionValue}>{formatEntryHours(selectedHours)}</span>
            {activeRun && (
              <span className={hstyles.filterNote}>
                Run hiện tại #{activeRun.id}: {formatEntryHours(activeRun.allowed_entry_hours_utc)}
              </span>
            )}
          </div>
          <div className={hstyles.hourGrid}>
            {ENTRY_HOURS.map((h) => {
              const active = selectedHours.includes(h);
              return (
                <button
                  key={h}
                  type="button"
                  className={`${hstyles.hourBtn} ${active ? hstyles.hourBtnActive : ''}`}
                  onClick={() => toggleHour(h)}
                  aria-pressed={active}
                  title={`${String(h).padStart(2, '0')}:00 UTC = ${String((h + 7) % 24).padStart(2, '0')}:00 giờ VN`}
                >
                  {String(h).padStart(2, '0')}
                </button>
              );
            })}
          </div>
          <div className={hstyles.sessionActions}>
            <Button size="sm" variant="ghost" onClick={() => setSelectedHours(GOOD_ENTRY_HOURS)}>
              Preset 6,8,14,17
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setSelectedHours(ENTRY_HOURS)}>
              Tất cả 24h
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setSelectedHours([])}>
              Bỏ lọc
            </Button>
            <span className={hstyles.filterNote}>
              Chỉ lọc entry; trend đã mở vẫn giữ qua giờ khác. Giờ VN = UTC+7.
            </span>
          </div>
        </div>
      ) : (
        activeRun && (
          <div className={hstyles.sessionFilter}>
            <div className={hstyles.sessionHead}>
              <span className={hstyles.filterLabel}>Giờ entry của run #{activeRun.id} (UTC)</span>
              <span className={hstyles.sessionValue}>
                {formatEntryHours(activeRun.allowed_entry_hours_utc)}
              </span>
            </div>
          </div>
        )
      )}

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
          <HistoryFiltersBar
            filters={filters}
            startDate={startDate}
            endDate={endDate}
            onStartDate={setStartDate}
            onEndDate={setEndDate}
            onClearDates={() => {
              setStartDate('');
              setEndDate('');
            }}
            modelVersionId={modelVersionId}
            onModelVersion={handleModelVersion}
            onRegimeMode={(m) => setFilters((prev) => ({ ...prev, regimeMode: m }))}
          />

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
                onClick={() => selectTab(t.key)}
              >
                {t.label}
              </button>
            ))}
          </div>

          <div className={hstyles.tabPanel}>
            {tab === 'overview' && <OverviewTab run={activeRun} runId={activeRun.id} />}
            {tab === 'timeline' && (
              <TimelineTab
                run={activeRun}
                runId={activeRun.id}
                filters={filters}
                onDateRangePreset={(range) => {
                  if (!range) {
                    setStartDate('');
                    setEndDate('');
                  } else {
                    setStartDate(range.startDate);
                    setEndDate(range.endDate);
                  }
                }}
              />
            )}
            {tab === 'trends' && <TrendsTab runId={activeRun.id} />}
            {tab === 'direction' && <DirectionAccuracyTab run={activeRun} />}
            {tab === 'sideways' && <SidewaysTab runId={activeRun.id} />}
            {tab === 'early' && <EarlyTrendTab runId={activeRun.id} />}
            {tab === 'segments' && (
              <SegmentsTab run={activeRun} runId={activeRun.id} filters={filters} />
            )}
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
