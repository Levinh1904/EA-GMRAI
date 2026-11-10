'use client';

import { useMemo, useState } from 'react';
import { Badge, Button, Card, EmptyState, ErrorState, Loading, Notice, RegimeBadge } from '@/components/ui/ui';
import { api } from '@/lib/api';
import { fmtNum, fmtPrice, fmtUtc } from '@/lib/format';
import { regimeColor } from '@/lib/regime';
import { useApi } from '@/lib/swr';
import type {
  HistoryBar,
  HistoryRun,
  HistorySegment,
  HistorySegmentsResponse,
  Regime,
} from '@/lib/types';
import { useAllSegments, useRunBars } from '@/components/charts/TradingChart/useChartData';
import { useHmmStateMap, isEarlyRegime } from '../shared';
import { segmentInRange, type HistoryFilters } from '../filters';
import { SegmentDetailPanel } from './SegmentDetailPanel';
import styles from '../../pages.module.css';
import hstyles from '../history.module.css';

const PAGE = 100;

type SortKey = 'segment_index' | 'start_ts' | 'duration_minutes' | 'bar_count' | 'net_change' | 'range_touches_high' | 'range_touches_low';

const REGIME_FILTERS = [
  { value: '', label: 'Tất cả regimes' },
  { value: 'TREND_UP', label: 'TREND_UP' },
  { value: 'TREND_DOWN', label: 'TREND_DOWN' },
  { value: 'SIDEWAYS', label: 'SIDEWAYS' },
  { value: 'EARLY_TREND_UP', label: 'EARLY_TREND_UP' },
  { value: 'EARLY_TREND_DOWN', label: 'EARLY_TREND_DOWN' },
  { value: 'TRANSITION', label: 'TRANSITION' },
  { value: 'HIGH_VOLATILITY', label: 'HIGH_VOLATILITY' },
  { value: 'UNKNOWN', label: 'UNKNOWN' },
];

/** Group consecutive bars with the same reference_regime into segment-like rows. */
function buildReferenceSegments(bars: HistoryBar[]): HistorySegment[] {
  const out: HistorySegment[] = [];
  interface Acc {
    regime: string;
    start_ts: string;
    end_ts: string;
    open: number;
    close: number;
    high: number;
    low: number;
    count: number;
    atrSum: number;
    adxSum: number;
    effSum: number;
  }
  let cur: Acc | null = null;
  let index = 0;
  const push = (a: Acc) => {
    index++;
    out.push({
      id: -index,
      segment_index: index,
      regime: a.regime as Regime,
      start_ts: a.start_ts,
      end_ts: a.end_ts,
      bar_count: a.count,
      duration_minutes: a.count * 15,
      start_price: a.open,
      end_price: a.close,
      high_price: a.high,
      low_price: a.low,
      net_change: a.close - a.open,
      mfe: a.high - a.open,
      mae: a.open - a.low,
      atr_mean: a.atrSum / a.count,
      adx_mean: a.adxSum / a.count,
      efficiency_mean: a.effSum / a.count,
      hmm_probs: null,
      confidence_mean: Number.NaN,
      model_version_id: null,
      split_reason: null,
      range_touches_high: 0,
      range_touches_low: 0,
    });
  };
  for (const b of bars) {
    const r = b.reference_regime ?? 'UNKNOWN';
    if (!cur || cur.regime !== r) {
      if (cur) push(cur);
      cur = {
        regime: r,
        start_ts: b.ts,
        end_ts: b.ts,
        open: b.open,
        close: b.close,
        high: b.high,
        low: b.low,
        count: 1,
        atrSum: b.atr_ratio ?? 0,
        adxSum: b.adx_norm ?? 0,
        effSum: b.efficiency_ratio ?? 0,
      };
    } else {
      cur.end_ts = b.ts;
      cur.close = b.close;
      if (b.high > cur.high) cur.high = b.high;
      if (b.low < cur.low) cur.low = b.low;
      cur.count++;
      cur.atrSum += b.atr_ratio ?? 0;
      cur.adxSum += b.adx_norm ?? 0;
      cur.effSum += b.efficiency_ratio ?? 0;
    }
  }
  if (cur) push(cur);
  return out;
}

export default function SegmentsTab({
  run,
  runId,
  filters,
}: {
  run: HistoryRun;
  runId: number;
  filters: HistoryFilters;
}) {
  const [regime, setRegime] = useState('');
  const [minDur, setMinDur] = useState('');
  const [maxDur, setMaxDur] = useState('');
  const [applied, setApplied] = useState({ regime: '', minDur: '', maxDur: '' });
  const [extra, setExtra] = useState<HistorySegment[]>([]);
  const [extraLoading, setExtraLoading] = useState(false);
  const [extraError, setExtraError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [sort, setSort] = useState<{ key: SortKey; dir: 1 | -1 }>({ key: 'segment_index', dir: 1 });
  const hmmStateMap = useHmmStateMap(run.hmm_model_version_id);

  const referenceMode = filters.regimeMode === 'reference';
  const dateFiltered = Boolean(filters.start || filters.end);

  // Reference mode: bar-level reference_regime → pseudo segments.
  const { bars, isLoading: barsLoading, error: barsError } = useRunBars(runId, referenceMode);
  const pseudoSegments = useMemo(
    () => (referenceMode ? buildReferenceSegments(bars) : []),
    [referenceMode, bars]
  );

  // Full segment list (for top-longest + date-filtered client mode).
  const { segments: allSegs, isLoading: allSegsLoading, error: allSegsError } = useAllSegments(runId);

  // Server-paginated query (default AI mode without a date range).
  const query = useMemo(() => {
    const q = new URLSearchParams();
    q.set('limit', String(PAGE));
    q.set('offset', '0');
    if (applied.regime) q.set('regime', applied.regime);
    if (applied.minDur) q.set('min_duration', applied.minDur);
    if (applied.maxDur) q.set('max_duration', applied.maxDur);
    return q.toString();
  }, [applied]);

  const { data, error, isLoading } = useApi<HistorySegmentsResponse>(
    !referenceMode && !dateFiltered ? `/history/runs/${runId}/segments?${query}` : null
  );

  const useClientFilter = referenceMode || dateFiltered;

  // Base rows depending on mode.
  const baseRows = useMemo<HistorySegment[]>(() => {
    if (referenceMode) return pseudoSegments;
    if (dateFiltered) {
      return allSegs.filter((s) => segmentInRange(s.start_ts, s.end_ts, filters));
    }
    return [...extra, ...(data?.segments ?? [])];
  }, [referenceMode, dateFiltered, pseudoSegments, allSegs, filters, extra, data]);

  const rows = useMemo(() => {
    if (!useClientFilter) return baseRows;
    const min = minDur ? Number(minDur) : null;
    const max = maxDur ? Number(maxDur) : null;
    return baseRows.filter((s) => {
      if (regime && s.regime !== regime) return false;
      if (min != null && s.duration_minutes < min) return false;
      if (max != null && s.duration_minutes > max) return false;
      return true;
    });
  }, [useClientFilter, baseRows, regime, minDur, maxDur]);

  const total = useClientFilter ? rows.length : (data?.total ?? 0);
  const hasMore = !useClientFilter && rows.length < total;

  const sortedRows = useMemo(() => {
    const { key, dir } = sort;
    return [...rows].sort((a, b) => {
      const va = a[key];
      const vb = b[key];
      const cmp =
        typeof va === 'string' && typeof vb === 'string'
          ? va.localeCompare(vb)
          : Number(va) - Number(vb);
      return cmp * dir;
    });
  }, [rows, sort]);

  function toggleSort(key: SortKey) {
    setSort((prev) => (prev.key === key ? { key, dir: prev.dir === 1 ? -1 : 1 } : { key, dir: 1 }));
  }

  function SortTh({ label, k }: { label: string; k: SortKey }) {
    const active = sort.key === k;
    return (
      <th
        onClick={() => toggleSort(k)}
        style={{ cursor: 'pointer', userSelect: 'none' }}
        title={`Sắp xếp theo ${label}`}
      >
        {label}
        {active ? (sort.dir === 1 ? ' ▲' : ' ▼') : ''}
      </th>
    );
  }

  async function loadMore() {
    if (extraLoading) return;
    setExtraLoading(true);
    setExtraError(null);
    try {
      const resp = await api.historySegments(runId, {
        limit: PAGE,
        offset: rows.length,
        regime: applied.regime || undefined,
        min_duration: applied.minDur ? Number(applied.minDur) : undefined,
        max_duration: applied.maxDur ? Number(applied.maxDur) : undefined,
      });
      setExtra((prev) => [...prev, ...resp.segments]);
    } catch (e) {
      setExtraError(e instanceof Error ? e.message : 'Tải thêm thất bại');
    } finally {
      setExtraLoading(false);
    }
  }

  const selected = useMemo(
    () => rows.find((s) => s.id === selectedId) ?? allSegs.find((s) => s.id === selectedId) ?? null,
    [rows, allSegs, selectedId]
  );

  const topLongest = useMemo(() => {
    const top: HistorySegment[] = [];
    const seen = new Set<string>();
    const byRegime = new Map<string, HistorySegment[]>();
    for (const s of allSegs) {
      const key = isEarlyRegime(s.regime) ? 'EARLY_TREND' : (s.regime ?? 'UNKNOWN');
      const arr = byRegime.get(key) ?? [];
      arr.push(s);
      byRegime.set(key, arr);
    }
    for (const [key, arr] of byRegime) {
      if (seen.has(key)) continue;
      seen.add(key);
      arr.sort((a, b) => b.duration_minutes - a.duration_minutes);
      top.push(...arr.slice(0, 5));
    }
    top.sort((a, b) => b.duration_minutes - a.duration_minutes);
    return top;
  }, [allSegs]);

  const topByRegime = useMemo(() => {
    const map = new Map<string, HistorySegment[]>();
    for (const s of topLongest) {
      const key = isEarlyRegime(s.regime) ? 'EARLY_TREND' : (s.regime ?? 'UNKNOWN');
      const arr = map.get(key) ?? [];
      arr.push(s);
      map.set(key, arr);
    }
    return map;
  }, [topLongest]);

  function applyFilters() {
    if (useClientFilter) return; // client-side, applied live
    setApplied({ regime, minDur, maxDur });
  }

  function clearFilters() {
    setRegime('');
    setMinDur('');
    setMaxDur('');
    setApplied({ regime: '', minDur: '', maxDur: '' });
  }

  const clientLoading = referenceMode ? barsLoading : dateFiltered ? allSegsLoading : false;
  const clientError = referenceMode ? barsError : dateFiltered ? allSegsError : null;

  return (
    <div className={styles.stack}>
      {referenceMode && (
        <Notice tone="info">
          <strong>Chế độ Reference:</strong> danh sách bên dưới được nhóm từ{' '}
          <code>reference_regime</code> của từng nến (động cơ quy tắc) — không phải segments AI gốc.
          Các trường như posterior HMM / model version không áp dụng cho chế độ này.
        </Notice>
      )}
      {dateFiltered && !referenceMode && (
        <Notice tone="info">
          Đang lọc theo khoảng ngày: {fmtUtc(filters.start)} → {fmtUtc(filters.end)} (lọc phía máy
          khách trên toàn bộ segments).
        </Notice>
      )}

      <div className={styles.toolbar}>
        <select className={hstyles.select} value={regime} onChange={(e) => setRegime(e.target.value)}>
          {REGIME_FILTERS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
        <label className={styles.small} style={{ color: 'var(--text-muted)' }}>
          Tối thiểu (phút)
        </label>
        <input
          className={hstyles.input}
          type="number"
          min={0}
          value={minDur}
          onChange={(e) => setMinDur(e.target.value)}
          placeholder="0"
          style={{ width: 110 }}
        />
        <label className={styles.small} style={{ color: 'var(--text-muted)' }}>
          Tối đa (phút)
        </label>
        <input
          className={hstyles.input}
          type="number"
          min={0}
          value={maxDur}
          onChange={(e) => setMaxDur(e.target.value)}
          placeholder="∞"
          style={{ width: 110 }}
        />
        {!useClientFilter && <Button onClick={applyFilters}>Áp dụng bộ lọc</Button>}
        {useClientFilter && (
          <span className={styles.muted} style={{ fontSize: 12 }}>
            Bộ lọc áp dụng trực tiếp (chế độ Reference / lọc ngày)
          </span>
        )}
        {regime || minDur || maxDur ? (
          <Button variant="ghost" onClick={clearFilters}>
            Xóa bộ lọc
          </Button>
        ) : null}
        <span className={styles.muted}>{fmtNum(total, 0)} segments khớp</span>
      </div>

      <Card
        title="Danh sách segments"
        subtitle="Bấm tiêu đề cột để sắp xếp (trên dữ liệu đã tải) · bấm một dòng để xem chi tiết"
      >
        {clientLoading && rows.length === 0 && <Loading label="Đang tải segments…" />}
        {clientError != null && rows.length === 0 && <ErrorState error={clientError} />}
        {isLoading && rows.length === 0 && <Loading label="Đang tải segments…" />}
        {error && rows.length === 0 && <ErrorState error={error} />}
        {!isLoading && !error && !clientLoading && !clientError && rows.length === 0 && (
          <EmptyState
            title="Không có segment khớp bộ lọc"
            hint="Thử nới rộng khoảng thời lượng hoặc chọn regime khác."
          />
        )}
        {rows.length > 0 && (
          <>
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <SortTh label="#" k="segment_index" />
                    <th>Regime</th>
                    <SortTh label="Bắt đầu (UTC)" k="start_ts" />
                    <th>Kết thúc (UTC)</th>
                    <SortTh label="Phút" k="duration_minutes" />
                    <SortTh label="Nến" k="bar_count" />
                    <th className="num">Giá mở</th>
                    <th className="num">Giá đóng</th>
                    <SortTh label="Net change" k="net_change" />
                    <SortTh label="Chạm cao" k="range_touches_high" />
                    <SortTh label="Chạm thấp" k="range_touches_low" />
                  </tr>
                </thead>
                <tbody>
                  {sortedRows.map((s) => (
                    <tr
                      key={s.id}
                      onClick={() => setSelectedId(s.id === selectedId ? null : s.id)}
                      style={{
                        cursor: 'pointer',
                        background: s.id === selectedId ? 'rgba(76,141,255,0.10)' : undefined,
                      }}
                    >
                      <td className="mono">
                        {s.id < 0 ? `${s.segment_index}*` : s.segment_index}
                      </td>
                      <td>
                        <RegimeBadge regime={s.regime} />
                      </td>
                      <td className="mono">{fmtUtc(s.start_ts)}</td>
                      <td className="mono">{fmtUtc(s.end_ts)}</td>
                      <td className="num">{fmtNum(s.duration_minutes, 0)}</td>
                      <td className="num">{fmtNum(s.bar_count, 0)}</td>
                      <td className="num">{fmtPrice(s.start_price)}</td>
                      <td className="num">{fmtPrice(s.end_price)}</td>
                      <td
                        className="num"
                        style={{ color: s.net_change >= 0 ? 'var(--green)' : 'var(--red)' }}
                      >
                        {s.net_change >= 0 ? '+' : ''}
                        {fmtPrice(s.net_change)}
                      </td>
                      <td className="num">{s.range_touches_high}</td>
                      <td className="num">{s.range_touches_low}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {!useClientFilter && (
              <div className={styles.toolbar} style={{ marginTop: 12, marginBottom: 0 }}>
                <Button onClick={loadMore} disabled={extraLoading || !hasMore}>
                  {extraLoading ? 'Đang tải…' : `Tải thêm ${PAGE} segments`}
                </Button>
                <span className={styles.muted}>
                  Đã hiển thị {fmtNum(rows.length, 0)} / {fmtNum(total, 0)}
                </span>
              </div>
            )}
            {extraError && <Notice tone="danger">{extraError}</Notice>}
          </>
        )}
      </Card>

      {selected && <SegmentDetailPanel segment={selected} hmmStateMap={hmmStateMap} />}

      <Card title="Top 5 segments dài nhất theo regime" subtitle="Tính trên toàn bộ segments AI của run">
        {allSegsLoading && topLongest.length === 0 && <Loading label="Đang quét toàn bộ segments…" />}
        {allSegsError != null && topLongest.length === 0 && <ErrorState error={allSegsError} />}
        {!allSegsLoading && !allSegsError && topByRegime.size === 0 && (
          <EmptyState title="Chưa có dữ liệu top segments" />
        )}
        {[...topByRegime.entries()].map(([key, segs]) => (
          <div key={key} style={{ marginBottom: 14 }}>
            <div className={styles.toolbar} style={{ marginBottom: 6 }}>
              <Badge
                tone="neutral"
                title={key}
                style={{
                  color: regimeColor(key),
                  background: `${regimeColor(key)}1a`,
                  borderColor: `${regimeColor(key)}55`,
                }}
              >
                {key}
              </Badge>
            </div>
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Bắt đầu (UTC)</th>
                    <th>Kết thúc (UTC)</th>
                    <th className="num">Phút</th>
                    <th className="num">Nến</th>
                    <th className="num">Net change</th>
                  </tr>
                </thead>
                <tbody>
                  {segs.map((s) => (
                    <tr
                      key={s.id}
                      onClick={() => setSelectedId(s.id === selectedId ? null : s.id)}
                      style={{
                        cursor: 'pointer',
                        background: s.id === selectedId ? 'rgba(76,141,255,0.10)' : undefined,
                      }}
                    >
                      <td className="mono">{s.segment_index}</td>
                      <td className="mono">{fmtUtc(s.start_ts)}</td>
                      <td className="mono">{fmtUtc(s.end_ts)}</td>
                      <td className="num">{fmtNum(s.duration_minutes, 0)}</td>
                      <td className="num">{fmtNum(s.bar_count, 0)}</td>
                      <td className="num" style={{ color: s.net_change >= 0 ? 'var(--green)' : 'var(--red)' }}>
                        {s.net_change >= 0 ? '+' : ''}
                        {fmtPrice(s.net_change)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ))}
      </Card>
    </div>
  );
}
