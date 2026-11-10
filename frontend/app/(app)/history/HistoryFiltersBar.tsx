'use client';

// Global filters bar for the Historical Analyzer: date range (UTC days),
// timeframe (M15 only — the model is trained on M15), model version
// (re-selects the matching run) and AI/Reference regime mode.

import { Button, Segmented } from '@/components/ui/ui';
import type { ModelListResponse, Timeframe } from '@/lib/types';
import { useApi } from '@/lib/swr';
import { isoToDateInput, type HistoryFilters } from './filters';
import hstyles from './history.module.css';

const TF_OPTIONS: Array<{ value: Timeframe; label: string }> = [
  { value: 'M15', label: 'M15' },
  { value: 'M5', label: 'M5' },
  { value: 'H1', label: 'H1' },
];

export function HistoryFiltersBar({
  filters,
  startDate,
  endDate,
  onStartDate,
  onEndDate,
  onClearDates,
  modelVersionId,
  onModelVersion,
  onRegimeMode,
  disabled,
}: {
  filters: HistoryFilters;
  startDate: string;
  endDate: string;
  onStartDate: (v: string) => void;
  onEndDate: (v: string) => void;
  onClearDates: () => void;
  modelVersionId: string;
  onModelVersion: (v: string) => void;
  onRegimeMode: (m: 'ai' | 'reference') => void;
  disabled?: boolean;
}) {
  const models = useApi<ModelListResponse>('/models?model_type=hmm&limit=100', {
    revalidateOnFocus: false,
  });
  const hmmVersions = (models.data?.models ?? []).filter((m) => m.model_type === 'hmm');
  const dateActive = Boolean(startDate || endDate);

  return (
    <div className={hstyles.filtersBar}>
      <div className={hstyles.filterGroup} title="Khoảng ngày (UTC) — áp dụng cho Timeline và danh sách segments">
        <span className={hstyles.filterLabel}>Khoảng ngày (UTC)</span>
        <input
          type="date"
          className={hstyles.input}
          value={startDate}
          max={endDate || undefined}
          onChange={(e) => onStartDate(e.target.value)}
          disabled={disabled}
        />
        <span className={hstyles.filterDash}>→</span>
        <input
          type="date"
          className={hstyles.input}
          value={endDate}
          min={startDate || undefined}
          onChange={(e) => onEndDate(e.target.value)}
          disabled={disabled}
        />
        {dateActive && (
          <Button size="sm" variant="ghost" onClick={onClearDates} disabled={disabled}>
            Xóa
          </Button>
        )}
      </div>

      <div
        className={hstyles.filterGroup}
        title="Model chỉ huấn luyện trên M15 — các khung thời gian khác chưa được hỗ trợ"
      >
        <span className={hstyles.filterLabel}>Khung thời gian</span>
        <select className={hstyles.select} value="M15" disabled style={{ maxWidth: 90 }}>
          {TF_OPTIONS.map((o) => (
            <option key={o.value} value={o.value} disabled={o.value !== 'M15'}>
              {o.label}
            </option>
          ))}
        </select>
        <span className={hstyles.filterNote}>model chỉ huấn luyện trên M15</span>
      </div>

      <div className={hstyles.filterGroup} title="Chọn phiên bản mô hình HMM — sẽ chuyển sang run dùng phiên bản đó (nếu có)">
        <span className={hstyles.filterLabel}>Phiên bản mô hình</span>
        <select
          className={hstyles.select}
          value={modelVersionId}
          onChange={(e) => onModelVersion(e.target.value)}
          disabled={disabled}
        >
          <option value="">Tự động (run mới nhất)</option>
          {hmmVersions.map((m) => (
            <option key={m.version_id} value={String(m.version_id)}>
              v{m.version} · #{m.version_id} · {m.status}
            </option>
          ))}
        </select>
      </div>

      <div className={hstyles.filterGroup} title="Chế độ regime: AI (mô hình) hoặc Reference (động cơ quy tắc)">
        <span className={hstyles.filterLabel}>Chế độ regime</span>
        <Segmented
          options={[
            { value: 'ai', label: 'AI' },
            { value: 'reference', label: 'Reference' },
          ]}
          value={filters.regimeMode}
          onChange={onRegimeMode}
        />
      </div>
    </div>
  );
}

export { isoToDateInput };
