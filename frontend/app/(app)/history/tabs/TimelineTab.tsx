'use client';

import { useEffect, useMemo, useState } from 'react';
import dynamic from 'next/dynamic';
import { Button, Card, ErrorState, Loading, Notice, Segmented } from '@/components/ui/ui';
import { api } from '@/lib/api';
import { fmtNum, fmtUtc } from '@/lib/format';
import { regimeColor, regimeLabel } from '@/lib/regime';
import type { HistoryBar, HistoryRun, HistorySegment } from '@/lib/types';
import { useHmmStateMap } from '../shared';
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

const RANGE_PRESETS: { label: string; days: number | null }[] = [
  { label: '1 tháng', days: 30 },
  { label: '3 tháng', days: 90 },
  { label: '6 tháng', days: 180 },
  { label: '1 năm', days: 365 },
  { label: 'Toàn bộ', days: null },
];

interface LoadState<T> {
  loading: boolean;
  error: string | null;
  items: T[];
  total: number;
}

export default function TimelineTab({ run, runId }: { run: HistoryRun; runId: number }) {
  const [bars, setBars] = useState<LoadState<HistoryBar>>({ loading: true, error: null, items: [], total: 0 });
  const [segments, setSegments] = useState<LoadState<HistorySegment>>({
    loading: true,
    error: null,
    items: [],
    total: 0,
  });
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [focusRange, setFocusRange] = useState<[string, string] | null>(null);
  const [activePreset, setActivePreset] = useState<string>('Toàn bộ');
  const [density, setDensity] = useState<string>('2');
  const hmmStateMap = useHmmStateMap(run.hmm_model_version_id);

  useEffect(() => {
    let cancelled = false;
    setBars({ loading: true, error: null, items: [], total: 0 });
    (async () => {
      const collected: HistoryBar[] = [];
      let offset = 0;
      try {
        for (;;) {
          const resp = await api.historyBars(runId, 5000, offset);
          if (cancelled) return;
          collected.push(...resp.bars);
          setBars({ loading: true, error: null, items: collected, total: resp.total });
          if (resp.bars.length === 0 || collected.length >= resp.total) break;
          offset += resp.limit;
        }
        if (!cancelled) setBars({ loading: false, error: null, items: collected, total: collected.length });
      } catch (e) {
        if (!cancelled)
          setBars({
            loading: false,
            error: e instanceof Error ? e.message : 'Tải bars thất bại',
            items: collected,
            total: collected.length,
          });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [runId]);

  useEffect(() => {
    let cancelled = false;
    setSegments({ loading: true, error: null, items: [], total: 0 });
    (async () => {
      const collected: HistorySegment[] = [];
      let offset = 0;
      try {
        for (;;) {
          const resp = await api.historySegments(runId, { limit: 1000, offset });
          if (cancelled) return;
          collected.push(...resp.segments);
          setSegments({ loading: true, error: null, items: collected, total: resp.total });
          if (resp.segments.length === 0 || collected.length >= resp.total) break;
          offset += resp.limit;
        }
        if (!cancelled)
          setSegments({ loading: false, error: null, items: collected, total: collected.length });
      } catch (e) {
        if (!cancelled)
          setSegments({
            loading: false,
            error: e instanceof Error ? e.message : 'Tải segments thất bại',
            items: collected,
            total: collected.length,
          });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [runId]);

  const selected = useMemo(
    () => segments.items.find((s) => s.id === selectedId) ?? null,
    [segments.items, selectedId]
  );

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

  const showList = useMemo(() => segments.items.slice(-400), [segments.items]);
  const densityNum = Math.max(1, parseInt(density, 10) || 1);

  function applyRangePreset(label: string, days: number | null) {
    setActivePreset(label);
    if (days == null) {
      setFocusRange(null);
      return;
    }
    const endMs = run.data_end ? new Date(run.data_end).getTime() : Date.now();
    if (Number.isNaN(endMs)) return;
    const startMs = endMs - days * 24 * 60 * 60 * 1000;
    setFocusRange([new Date(startMs).toISOString(), new Date(endMs).toISOString()]);
  }

  return (
    <div className={styles.stack}>
      <Notice tone="info">
        🖱 <b>Lăn chuột</b>: phóng to/thu nhỏ · <b>Kéo chuột</b>: vẽ vùng phóng to · <b>Kéo ngang
        (kéo biểu đồ)</b>: di chuyển · <b>Nhấp đúp</b>: đặt lại toàn bộ. Dải màu bên dưới là regime
        của từng segment (chính xác tuyệt đối, không giảm mẫu). Bấm vào dải regime hoặc một dòng
        trong danh sách để chọn segment — biểu đồ tự zoom tới segment đó.
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
      </div>

      <Card
        title={`Timeline nến + regime — run #${runId}`}
        subtitle={
          bars.loading
            ? `Đang tải bars: ${fmtNum(bars.items.length, 0)} / ${bars.total ? fmtNum(bars.total, 0) : '…'}`
            : `${fmtNum(bars.items.length, 0)} nến · ${fmtNum(segments.items.length, 0)} segments · nguồn: ${run.data_source ?? '—'}`
        }
        right={
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6, alignItems: 'flex-end' }}>
            <Segmented options={DENSITY_OPTIONS} value={density} onChange={setDensity} />
            <span className={styles.muted} style={{ fontSize: 11 }}>
              Giảm mẫu giúp zoom mượt — dải regime vẫn chính xác từng nến
            </span>
          </div>
        }
      >
        {bars.loading && (
          <Loading
            label={
              bars.items.length > 0
                ? `Đang tải toàn bộ nến: ${fmtNum(bars.items.length, 0)} / ${bars.total ? fmtNum(bars.total, 0) : '…'}…`
                : 'Đang tải toàn bộ nến (phân trang)…'
            }
          />
        )}
        {bars.error && bars.items.length === 0 && <ErrorState error={bars.error} />}
        {!bars.loading && !bars.error && bars.items.length === 0 && (
          <ErrorState title="Không có dữ liệu nến" error="Run không có bars." />
        )}
        {!bars.loading && bars.items.length > 0 && (
          <>
            <div className={styles.chartBox}>
              <TimelineChart
                bars={bars.items}
                segments={segments.items}
                selectedSegmentId={selectedId}
                focusRange={focusRange}
                onSelectSegment={(id) => {
                  const seg = segments.items.find((s) => s.id === id) ?? null;
                  selectSegment(seg);
                }}
                onClearFocus={() => setFocusRange(null)}
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
            <div className={styles.legend}>
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
        <SegmentDetailPanel segment={selected} hmmStateMap={hmmStateMap} />
        <Card
          title={`Danh sách segments (${fmtNum(segments.total, 0)} — hiển thị ${fmtNum(showList.length, 0)} gần nhất)`}
          subtitle="Bấm để chọn & zoom"
        >
          {segments.loading && segments.items.length === 0 && <Loading label="Đang tải segments…" />}
          {segments.error && segments.items.length === 0 && <ErrorState error={segments.error} />}
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
        </Card>
      </div>
    </div>
  );
}
