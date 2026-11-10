'use client';

// SVG donut for regime distribution (occupancy % from /stats/duration).
// Flat, low-saturation, matches the chart palette.

import { fmtPct } from '@/lib/format';
import styles from './regime.module.css';

export interface DonutSlice {
  key: string;
  label: string;
  value: number; // fraction 0..1 or percentage-like occupancy
  color: string;
}

export function RegimeDonut({
  slices,
  centerValue,
  centerLabel,
  size = 148,
}: {
  slices: DonutSlice[];
  centerValue?: string;
  centerLabel?: string;
  size?: number;
}) {
  const r = 44;
  const cx = 60;
  const cy = 60;
  const circumference = 2 * Math.PI * r;
  const total = slices.reduce((s, d) => s + d.value, 0);

  let acc = 0;
  const segs = slices.map((s) => {
    const frac = total > 0 ? s.value / total : 0;
    const start = acc;
    acc += frac;
    return { ...s, start, end: acc };
  });

  return (
    <div className={styles.donutWrap}>
      <svg
        viewBox="0 0 120 120"
        width={size}
        height={size}
        role="img"
        aria-label="Phân bố thời lượng theo regime"
      >
        <circle
          cx={cx}
          cy={cy}
          r={r}
          fill="none"
          stroke="var(--surface-3)"
          strokeWidth={13}
        />
        {segs.map((s) => {
          if (s.end - s.start <= 0.0005) return null;
          const dash = `${(s.end - s.start) * circumference} ${circumference}`;
          const offset = -s.start * circumference;
          return (
            <circle
              key={s.key}
              cx={cx}
              cy={cy}
              r={r}
              fill="none"
              stroke={s.color}
              strokeWidth={13}
              strokeDasharray={dash}
              strokeDashoffset={offset}
              transform={`rotate(-90 ${cx} ${cy})`}
              opacity={0.88}
            >
              <title>
                {s.label}: {fmtPct(s.value / 100)}
              </title>
            </circle>
          );
        })}
        {centerValue && (
          <text x={cx} y={cy - 2} textAnchor="middle" className={styles.donutCenterValue}>
            {centerValue}
          </text>
        )}
        {centerLabel && (
          <text x={cx} y={cy + 14} textAnchor="middle" className={styles.donutCenterLabel}>
            {centerLabel}
          </text>
        )}
      </svg>
      <div className={styles.donutLegend}>
        {slices
          .filter((s) => s.value > 0)
          .map((s) => (
            <div key={s.key} className={styles.donutLegendRow}>
              <span className={styles.donutLegendDot} style={{ background: s.color }} />
              <span className={styles.donutLegendLabel}>{s.label}</span>
              <span className={`num ${styles.donutLegendValue}`}>{fmtPct(s.value / 100, 1)}</span>
            </div>
          ))}
      </div>
    </div>
  );
}
