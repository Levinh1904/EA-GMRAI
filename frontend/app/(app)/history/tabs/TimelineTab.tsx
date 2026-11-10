'use client';

import { useEffect, useMemo, useState } from 'react';
import dynamic from 'next/dynamic';
import { Button, Card, ErrorState, Loading, Notice, Segmented } from '@/components/ui/ui';
import { fmtNum, fmtPct, fmtUtc } from '@/lib/format';
import {
  AGREEMENT_NEUTRAL_COLOR,
  DISAGREEMENT_COLOR,
  regimeColor,
  regimeLabel,
} from '@/lib/regime';
import { useApi } from '@/lib/swr';
import type { HistoryBar, HistoryRun, HistorySegment, VsReferenceStats } from '@/lib/types';
import type { DiffStripSegment, RefStripSegment, TimelineStripMode } from '@/components/charts/HistoryCharts';
import { useAllSegments, useRunBars } from '@/components/charts/TradingChart/useChartData';
import { useHmmStateMap } from '../shared';
import { segmentInRange, type HistoryFilters } from '../filters';
import { BarDetailPanel } from './BarDetailPanel';
import { SegmentDetailPanel } from './SegmentDetailPanel';
import styles from '../../pages.module.css';
import hstyles from '../history.module.css';

const TimelineChart = dynamic(
  () => import('@/components/charts/HistoryCharts').then((m) => m.TimelineChart),
  {
    ssr: false,
    loading: () => <Loading label="Đang khởi tạo biểu đồ timeline…" />,
  }
);

const DENSITY_OPTIONS = [
  { value: '1', label: 'Đầy đủ' },
  { value: '2', label: '1/2 nến' },
  { value: '4', label: '1/4 nến' },
  { value: '8', label: '1/8 nến' },
];

const STRIP_MODE_OPTIONS: Array<{ value: TimelineStripMode; label: string }> = [
  { value: 'ai', label: 'AI' },
  { value: 'reference', label: 'Reference' },
  { value: 'overlay', label: 'Overlay (AI + Reference)' },
  { value: 'disagreement', label: 'Bất đồng' },
];

const RANGE_PRESETS: { label: string; days: number | null }[] = [
  { label: '1 tháng', days: 30 },
  { label: '3 tháng', days: 90 },
  { label: '6 tháng', days: 180 },
  { label: '1 năm', days: 365 },
  { label: 'Toàn bộ', days: null },
];

/** Group consecutive bars with the same key into client-side strip segments. */
function groupStripSegments(
  bars: HistoryBar[],
  keyOf: (b: HistoryBar) => string
): Array<{ start_ts: string; end_ts: string; key: string }> {
  const out: Array<{ start_ts: string; end_ts: string; key: string }> = [];
  let cur: { key: string; start: string; end: string } | null = null;
  for (const b of bars) {
    const key = keyOf(b);
    if (!cur || cur.key !== key) {
      if (cur) out.push({ start_ts: cur.start, end_ts: cur.end, key: cur.key });
      cur = { key, start: b.ts, end: b.ts };
    } else {
      cur.end = b.ts;
    }
  }
  if (cur) out.push({ start_ts: cur.start, end_ts: cur.end, key: cur.key });
  return out;
}

export default function TimelineTab({
  run,
  runId,
  filters,
  onDateRangePreset,
}: {
  run: HistoryRun;
  runId: number;
  filters: HistoryFilters;
  onDateRangePreset: (range: { startDate: string; endDate: string } | null) => void;
}) {
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [selectedBarTs, setSelectedBarTs] = useState<string | null>(null);
  const [focusRange, setFocusRange] = useState<[string, string] | null>(null);
  const [activePreset, setActivePreset] = useState<string>('Toàn bộ');
  const [density, setDensity] = useState<string>('2');
  const [stripMode, setStripMode] = useState<TimelineStripMode>('ai');
  const hmmStateMap = useHmmStateMap(run.hmm_model_version_id);

  // Shared (SWR-cached) data: all bars + all segments of the run.
  const { bars, isLoading: barsLoading, error: barsError } = useRunBars(runId, true);
  const { segments, isLoading: segLoading, error: segError } = useAllSegments(runId);

  // Reference version + config come from the vs_reference report.
  const { data: vsRef } = useApi<VsReferenceStats>(`/history/runs/${runId}/stats/vs_reference`);

  // Global regime mode drives the strip mode (internal selector still works).
  useEffect(() => {
    setStripMode(filters.regimeMode === 'reference' ? 'reference' : 'ai');
  }, [filters.regimeMode]);

  // Global date range drives the chart focus + the segment list.
  useEffect(() => {
    if (filters.start && filters.end) {
      const start = filters.start;
      const end = filters.end;
      setActivePreset('');
      setFocusRange((prev) =>
        prev && prev[0] === start && prev[1] === end ? prev : [start, end]
      );
    } else {
      setFocusRange((prev) => (prev === null ? prev : null));
    }
  }, [filters.start, filters.end]);

  // Reference strip: group consecutive bars with identical reference_regime.
  const refSegments = useMemo<RefStripSegment[]>(
    () =>
      groupStripSegments(bars, (b) => b.reference_regime ?? 'UNKNOWN').map((s) => ({
        start_ts: s.start_ts,
        end_ts: s.end_ts,
        regime: s.key,
      })),
    [bars]
  );

  // Disagreement strip + agreement rate over the full dataset.
  const { diffSegments, agreementPct } = useMemo(() => {
    const diffs: DiffStripSegment[] = groupStripSegments(bars, (b) =>
      b.reference_regime != null && b.regime != null && b.reference_regime === b.regime
        ? 'agree'
        : 'disagree'
    ).map((s) => ({ start_ts: s.start_ts, end_ts: s.end_ts, agree: s.key === 'agree' }));
    let agree = 0;
    for (const b of bars) {
      if (b.reference_regime != null && b.regime != null && b.reference_regime === b.regime) agree++;
    }
    return {
      diffSegments: diffs,
      agreementPct: bars.length > 0 ? agree / bars.length : null,
    };
  }, [bars]);

  const selected = useMemo(
    () => segments.find((s) => s.id === selectedId) ?? null,
    [segments, selectedId]
  );

  const selectedBar = useMemo(() => {
    if (!selectedBarTs) return null;
    const ms = new Date(selectedBarTs).getTime();
    if (!Number.isNaN(ms)) {
      const exact = bars.find((b) => new Date(b.ts).getTime() === ms);
      if (exact) return exact;
    }
    return bars.find((b) => b.ts === selectedBarTs) ?? null;
  }, [selectedBarTs, bars]);

  function handleSelectBar(barTs: string) {
    setSelectedBarTs(barTs);
  }

  function selectSegment(seg: HistorySegment | null) {
    setSelectedId(seg ? seg.id : null);
    setActivePreset('');
    if (seg) {
      const end = new Date(seg.end_ts).getTime();
      const endIso = Number.isNaN(end) ? seg.end_ts : new Date(end + 15 * 60 * 1000).toISOString();
      setFocusRange([seg.start_ts, endIso]);
    } else {
      setFocusRange(null);
    }
  }

  // Segments filtered by the global date range.
  const filteredSegments = useMemo(() => {
    if (!filters.start && !filters.end) return segments;
    return segments.filter((s) => segmentInRange(s.start_ts, s.end_ts, filters));
  }, [segments, filters.start, filters.end]);

  const showList = useMemo(() => filteredSegments.slice(-400), [filteredSegments]);
  const densityNum = Math.max(1, parseInt(density, 10) || 1);

  function applyRangePreset(label: string, days: number | null) {
    if (days == null) {
      setActivePreset(label);
      onDateRangePreset(null);
      return;
    }
    const endMs = run.data_end ? new Date(run.data_end).getTime() : Date.now();
    if (Number.isNaN(endMs)) return;
    const startMs = endMs - days * 24 * 60 * 60 * 1000;
    setActivePreset(label);
    onDateRangePreset({
      startDate: new Date(startMs).toISOString().slice(0, 10),
      endDate: new Date(endMs).toISOString().slice(0, 10),
    });
  }

  const refSegCount = refSegments.length;
  const refAvailable = bars.some((b) => b.reference_regime != null);
  const hasDateRange = Boolean(filters.start && filters.end);

  return (
    <div className={styles.stack}>
      <Notice tone="info">
        🖱 <b>Lăn chuột</b>: phóng to/thu nhỏ · <b>Kéo chuột</b>: vẽ vùng phóng to · <b>Kéo ngang
        (kéo biểu đồ)</b>: di chuyển · <b>Nhấp đúp</b>: đặt lại toàn bộ. Bấm vào dải regime hoặc một
        dòng trong danh sách để chọn segment — biểu đồ tự zoom tới segment đó. <b>Bấm vào cây nến</b>{' '}
        để xem chi tiết thanh nến (OHLC, AI, Reference).
      </Notice>

      <div className={styles.toolbar} style={{ marginBottom: 10 }}>
        {RANGE_PRESETS.map((p) => (
          <Button
            key={p.label}
            size="sm"
            variant={activePreset === p.label ? 'primary' : 'ghost'}
            onClick={() => applyRangePreset(p.label, p.days)}
          >
            {p.label}
          </Button>
        ))}
        {hasDateRange && (
          <Button size="sm" onClick={() => onDateRangePreset(null)}>
            Bỏ lọc ngày
          </Button>
        )}
        <span className={styles.muted} style={{ fontSize: 12 }}>
          Bộ lọc ngày đồng bộ với thanh lọc chung của trang
        </span>
      </div>

      <Card
        title={`Timeline nến + regime — run #${runId}`}
        subtitle={
          barsLoading
            ? 'Đang tải toàn bộ nến (phân trang)…'
            : `${fmtNum(bars.length, 0)} nến · ${fmtNum(segments.length, 0)} segments${
                hasDateRange ? ` · lọc ngày: ${fmtUtc(filters.start)} → ${fmtUtc(filters.end)}` : ''
              } · nguồn: ${run.data_source ?? '—'}`
        }
        right={
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6, alignItems: 'flex-end' }}>
            <Segmented options={STRIP_MODE_OPTIONS} value={stripMode} onChange={setStripMode} />
            <Segmented options={DENSITY_OPTIONS} value={density} onChange={setDensity} />
            <span className={styles.muted} style={{ fontSize: 11 }}>
              Chế độ dải regime · giảm mẫu giúp zoom mượt
            </span>
          </div>
        }
      >
        {barsLoading && <Loading label="Đang tải toàn bộ nến (phân trang)…" />}
        {barsError != null && bars.length === 0 && <ErrorState error={barsError} />}
        {!barsLoading && !barsError && bars.length === 0 && (
          <ErrorState title="Không có dữ liệu nến" error="Run không có bars." />
        )}
        {(stripMode === 'reference' || stripMode === 'overlay' || stripMode === 'disagreement') &&
          !refAvailable &&
          !barsLoading &&
          bars.length > 0 && (
            <Notice tone="warn">
              Run #{runId} không có dữ liệu <code>reference_regime</code> theo từng nến — dải
              Reference/Bất đồng không thể hiển thị. Hãy chạy lại run với backend có hỗ trợ reference
              engine.
            </Notice>
          )}
        {!barsLoading && bars.length > 0 && (
          <>
            <div className={styles.chartBox}>
              <TimelineChart
                bars={bars}
                segments={segments}
                selectedSegmentId={selectedId}
                focusRange={focusRange}
                onSelectSegment={(id) => {
                  const seg = segments.find((s) => s.id === id) ?? null;
                  selectSegment(seg);
                }}
                onClearFocus={() => setFocusRange(null)}
                onSelectBar={handleSelectBar}
                stripMode={stripMode}
                refSegments={refSegments}
                diffSegments={diffSegments}
                density={densityNum}
                height={560}
              />
            </div>
            {densityNum > 1 && (
              <div className={styles.muted} style={{ fontSize: 12, marginTop: 6 }}>
                Chế độ giảm mẫu 1/{densityNum} chỉ áp dụng cho nến hiển thị (tăng tốc render) — dải
                regime và overlay segment vẫn chính xác tuyệt đối.
              </div>
            )}
            {stripMode === 'disagreement' && (
              <div className={styles.toolbar} style={{ marginTop: 10, marginBottom: 0, justifyContent: 'center' }}>
                <span className={styles.legendItem}>
                  <span className={styles.legendDot} style={{ background: AGREEMENT_NEUTRAL_COLOR }} />
                  Đồng thuận (AI = Reference)
                </span>
                <span className={styles.legendItem}>
                  <span className={styles.legendDot} style={{ background: DISAGREEMENT_COLOR }} />
                  Bất đồng (AI ≠ Reference)
                </span>
                <strong style={{ fontSize: 12 }}>
                  {agreementPct != null ? `${fmtPct(agreementPct, 1)} đồng thuận` : '—'} trên toàn bộ{' '}
                  {fmtNum(bars.length, 0)} nến
                </strong>
              </div>
            )}
            <div className={styles.legend}>
              {stripMode === 'overlay' && (
                <>
                  <span className={styles.legendItem}>
                    <span
                      className={styles.legendDot}
                      style={{ background: 'rgba(255,255,255,0.35)', border: '1px solid rgba(255,255,255,0.8)' }}
                    />
                    Dải AI (trên)
                  </span>
                  <span className={styles.legendItem}>
                    <span
                      className={styles.legendDot}
                      style={{ background: 'rgba(0,0,0,0.4)', border: '1px solid rgba(255,255,255,0.8)' }}
                    />
                    Dải Reference (dưới)
                  </span>
                </>
              )}
              {stripMode === 'reference' && (
                <span className={styles.legendItem}>
                  <span
                    className={styles.legendDot}
                    style={{ background: 'rgba(0,0,0,0.4)', border: '1px solid rgba(255,255,255,0.8)' }}
                  />
                  Dải Reference (quy tắc, ref_v1) — {fmtNum(refSegCount, 0)} đoạn
                </span>
              )}
              {stripMode === 'ai' && (
                <span className={styles.legendItem}>
                  <span
                    className={styles.legendDot}
                    style={{ background: 'rgba(255,255,255,0.35)', border: '1px solid rgba(255,255,255,0.8)' }}
                  />
                  Dải AI (theo segments)
                </span>
              )}
              {Object.entries({
                TREND_UP: 'Xu hướng tăng',
                TREND_DOWN: 'Xu hướng giảm',
                SIDEWAYS: 'Đi ngang',
                EARLY_TREND_UP: 'Tăng sớm',
                EARLY_TREND_DOWN: 'Giảm sớm',
                TRANSITION: 'Chuyển tiếp',
                HIGH_VOLATILITY: 'Biến động cao',
                UNKNOWN: 'Không xác định',
              }).map(([key, label]) => (
                <span key={key} className={styles.legendItem}>
                  <span className={styles.legendDot} style={{ background: regimeColor(key) }} />
                  {label}
                </span>
              ))}
              <span className={styles.legendItem}>
                <span
                  className={styles.legendDot}
                  style={{ background: 'transparent', border: '1px solid rgba(255,255,255,0.6)' }}
                />
                Segment đang chọn
              </span>
            </div>
            {focusRange && (
              <div className={styles.toolbar} style={{ marginTop: 10, marginBottom: 0 }}>
                <Button size="sm" onClick={() => setFocusRange(null)}>
                  Xem toàn bộ (bỏ zoom)
                </Button>
                <span className={styles.muted} style={{ fontSize: 12 }}>
                  Zoom tới: {fmtUtc(focusRange[0])} → {fmtUtc(focusRange[1])} (nhấp đúp vào biểu đồ
                  cũng đặt lại zoom)
                </span>
              </div>
            )}
          </>
        )}
      </Card>

      <div className={`${styles.grid} ${styles.cols2}`}>
        <BarDetailPanel
          bar={selectedBar}
          hmmStateMap={hmmStateMap}
          run={run}
          referenceVersion={vsRef?.reference_version ?? null}
          onClose={() => setSelectedBarTs(null)}
        />
        <SegmentDetailPanel segment={selected} hmmStateMap={hmmStateMap} />
      </div>

      <Card
        title={`Danh sách segments (${fmtNum(filteredSegments.length, 0)}${
          filteredSegments.length !== segments.length ? ` / ${fmtNum(segments.length, 0)}` : ''
        } — hiển thị ${fmtNum(showList.length, 0)} gần nhất)`}
        subtitle="Bấm để chọn & zoom · danh sách áp dụng bộ lọc ngày chung"
      >
        {segLoading && segments.length === 0 && <Loading label="Đang tải segments…" />}
        {segError != null && segments.length === 0 && <ErrorState error={segError} />}
        {showList.length > 0 && (
          <div className={hstyles.segList}>
            {showList.map((s) => (
              <button
                key={s.id}
                type="button"
                className={`${hstyles.segRow} ${s.id === selectedId ? hstyles.segRowActive : ''}`}
                onClick={() => selectSegment(s)}
              >
                <span className={hstyles.segDot} style={{ background: regimeColor(s.regime) }} />
                <span style={{ fontFamily: 'var(--mono)' }}>#{s.segment_index}</span>
                <span>{regimeLabel(s.regime)}</span>
                <span className={hstyles.segMeta}>
                  {s.duration_minutes} phút · {s.bar_count} nến · {fmtUtc(s.start_ts)}
                </span>
              </button>
            ))}
          </div>
        )}
        {!segLoading && !segError && showList.length === 0 && segments.length > 0 && (
          <div className={styles.muted} style={{ padding: 14 }}>
            Không có segment nào trong khoảng ngày đã chọn.
          </div>
        )}
      </Card>
    </div>
  );
}
