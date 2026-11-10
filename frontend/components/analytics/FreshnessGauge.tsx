'use client';

// Semicircular freshness gauge: candle age vs the stale threshold for one
// timeframe. Data from /stats/dashboard `data_freshness`.

import { fmtAge, fmtNum } from '@/lib/format';
import type { FreshnessInfo } from '@/lib/types';
import styles from './analytics.module.css';

function arcPath(cx: number, cy: number, r: number, startAngle: number, endAngle: number): string {
  const s = (startAngle * Math.PI) / 180;
  const e = (endAngle * Math.PI) / 180;
  const x1 = cx + r * Math.cos(s);
  const y1 = cy + r * Math.sin(s);
  const x2 = cx + r * Math.cos(e);
  const y2 = cy + r * Math.sin(e);
  const large = e - s > Math.PI ? 1 : 0;
  return `M ${x1.toFixed(2)} ${y1.toFixed(2)} A ${r} ${r} 0 ${large} 1 ${x2.toFixed(2)} ${y2.toFixed(2)}`;
}

export function FreshnessGauge({
  tf,
  info,
  width = 168,
}: {
  tf: string;
  info: FreshnessInfo | null | undefined;
  width?: number;
}) {
  const height = Math.round(width * 0.62);
  const cx = width / 2;
  const cy = height - 6;
  const r = width / 2 - 14;

  const age = info?.age_minutes ?? null;
  const threshold = info?.threshold_minutes ?? null;
  const stale = info?.stale ?? false;

  const ratio =
    age != null && threshold != null && threshold > 0
      ? Math.min(1, age / threshold)
      : age != null
        ? 1
        : 0;

  const color = age == null
    ? 'var(--text-disabled)'
    : stale
      ? 'var(--status-danger)'
      : ratio > 0.66
        ? 'var(--status-warn)'
        : 'var(--status-ok)';

  return (
    <div className={styles.gauge}>
      <svg viewBox={`0 0 ${width} ${height}`} width={width} height={height} role="img" aria-label={`Độ tươi dữ liệu ${tf}`}>
        <path
          d={arcPath(cx, cy, r, 180, 360)}
          fill="none"
          stroke="var(--surface-3)"
          strokeWidth={10}
          strokeLinecap="round"
        />
        {age != null && (
          <path
            d={arcPath(cx, cy, r, 180, 180 + 180 * ratio)}
            fill="none"
            stroke={color}
            strokeWidth={10}
            strokeLinecap="round"
          />
        )}
        <text x={cx} y={cy - 18} textAnchor="middle" className={styles.gaugeValue}>
          {age != null ? `${fmtNum(age, 0)}` : '—'}
        </text>
        <text x={cx} y={cy - 4} textAnchor="middle" className={styles.gaugeUnit}>
          phút
        </text>
      </svg>
      <div className={styles.gaugeMeta}>
        <span className={styles.gaugeTf}>{tf}</span>
        <span className={styles.gaugeLabel} style={{ color }}>
          {age == null ? 'không rõ' : stale ? 'Cũ' : ratio > 0.66 ? 'Gần hạn' : 'Mới'}
        </span>
        <span className={styles.gaugeSub}>
          ngưỡng {threshold != null ? `${fmtNum(threshold, 0)} phút` : '—'} · {fmtAge(age)}
        </span>
      </div>
    </div>
  );
}
