'use client';

import type { CSSProperties, ReactNode } from 'react';
import { regimeColor, regimeLabel, statusLabel, statusTone, type Tone } from '@/lib/regime';
import styles from './ui.module.css';

// ---------- Card ----------

export function Card({
  title,
  subtitle,
  right,
  children,
  tone,
  className,
}: {
  title?: ReactNode;
  subtitle?: ReactNode;
  right?: ReactNode;
  children: ReactNode;
  tone?: 'default' | 'warn' | 'danger';
  className?: string;
}) {
  const toneClass =
    tone === 'warn' ? styles.cardToneWarn : tone === 'danger' ? styles.cardToneDanger : '';
  return (
    <section className={`${styles.card} ${toneClass} ${className ?? ''}`}>
      {(title || subtitle || right) && (
        <div className={styles.cardHead}>
          <div>
            {title && <h2 className={styles.cardTitle}>{title}</h2>}
            {subtitle && <div className={styles.cardSub}>{subtitle}</div>}
          </div>
          {right && <div className={styles.cardRight}>{right}</div>}
        </div>
      )}
      {children}
    </section>
  );
}

// ---------- Page header ----------

export function PageHeader({
  title,
  subtitle,
  right,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  right?: ReactNode;
}) {
  return (
    <div className={styles.pageHeader}>
      <div>
        <h1 className={styles.pageTitle}>{title}</h1>
        {subtitle && <div className={styles.pageSub}>{subtitle}</div>}
      </div>
      {right && <div>{right}</div>}
    </div>
  );
}

// ---------- Stat ----------

export function Stat({
  label,
  value,
  sub,
  tone,
}: {
  label: ReactNode;
  value: ReactNode;
  sub?: ReactNode;
  tone?: 'up' | 'down' | 'warn' | 'neutral';
}) {
  const toneClass =
    tone === 'up'
      ? styles.statUp
      : tone === 'down'
        ? styles.statDown
        : tone === 'warn'
          ? styles.statWarn
          : '';
  return (
    <div className={styles.stat}>
      <div className={styles.statLabel}>{label}</div>
      <div className={`${styles.statValue} ${toneClass}`}>{value}</div>
      {sub && <div className={styles.statSub}>{sub}</div>}
    </div>
  );
}

// ---------- Badges ----------

export function Badge({
  tone = 'neutral',
  children,
  title,
}: {
  tone?: Tone | 'purple' | 'teal' | 'yellow';
  children: ReactNode;
  title?: string;
}) {
  return (
    <span className={`${styles.badge} ${styles[`tone${cap(tone)}`] ?? ''}`} title={title}>
      {children}
    </span>
  );
}

function cap(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

export function RegimeBadge({ regime, large }: { regime: string | null | undefined; large?: boolean }) {
  const color = regimeColor(regime);
  return (
    <span
      className={`${styles.badge} ${large ? styles.regimeBadgeLarge : ''}`}
      style={{
        color,
        background: `${color}1a`,
        borderColor: `${color}55`,
      }}
    >
      <span
        className={styles.dot}
        style={{ background: color, boxShadow: `0 0 6px ${color}` }}
      />
      {regimeLabel(regime)}
    </span>
  );
}

export function StatusPill({ status }: { status: string | null | undefined }) {
  return <Badge tone={statusTone(status)}>{statusLabel(status)}</Badge>;
}

export function FreshnessPill({
  ageMinutes,
  stale,
  thresholdMinutes,
}: {
  ageMinutes: number | null | undefined;
  stale: boolean | null | undefined;
  thresholdMinutes?: number | null;
}) {
  if (ageMinutes == null) return <Badge tone="neutral">Không rõ</Badge>;
  if (stale) {
    return (
      <Badge tone="danger" title={`Ngưỡng cảnh báo: ${thresholdMinutes ?? '—'} phút`}>
        Cũ · {ageMinutes.toFixed(0)} phút
      </Badge>
    );
  }
  if (thresholdMinutes != null && ageMinutes > thresholdMinutes * 0.66) {
    return (
      <Badge tone="warning" title={`Ngưỡng cảnh báo: ${thresholdMinutes} phút`}>
        Gần hạn · {ageMinutes.toFixed(0)} phút
      </Badge>
    );
  }
  return <Badge tone="success">Mới · {ageMinutes.toFixed(0)} phút</Badge>;
}

// ---------- States ----------

export function Loading({ label = 'Đang tải dữ liệu…' }: { label?: string }) {
  return (
    <div className={styles.loading}>
      <div className={styles.spinner} />
      <div>{label}</div>
    </div>
  );
}

export function EmptyState({
  title = 'Không có dữ liệu',
  hint,
}: {
  title?: string;
  hint?: string;
}) {
  return (
    <div className={styles.empty}>
      <div className={styles.emptyTitle}>{title}</div>
      {hint && <div className={styles.emptyHint}>{hint}</div>}
    </div>
  );
}

export function ErrorState({
  title = 'Không thể tải dữ liệu',
  error,
  onRetry,
}: {
  title?: string;
  error?: unknown;
  onRetry?: () => void;
}) {
  const message = error instanceof Error ? error.message : error ? String(error) : null;
  return (
    <div className={styles.error}>
      <div className={styles.errorTitle}>{title}</div>
      {message && <div className={styles.errorMsg}>{message}</div>}
      {onRetry && (
        <button type="button" className={styles.btn} onClick={onRetry}>
          Thử lại
        </button>
      )}
    </div>
  );
}

// ---------- Probability bar ----------

export function ProbRow({
  label,
  value,
  color,
  digits = 1,
}: {
  label: string;
  value: number;
  color: string;
  digits?: number;
}) {
  const pct = Math.max(0, Math.min(1, value));
  return (
    <div className={styles.probRow}>
      <div className={styles.probLabel} title={label}>
        {label}
      </div>
      <div className={styles.probTrack}>
        <div className={styles.probFill} style={{ width: `${pct * 100}%`, background: color }} />
      </div>
      <div className={styles.probVal}>{(pct * 100).toFixed(digits)}%</div>
    </div>
  );
}

// ---------- Key-value list ----------

export function KV({
  items,
  columns = 2,
}: {
  items: Array<{ label: ReactNode; value: ReactNode }>;
  columns?: 1 | 2;
}) {
  return (
    <div className={columns === 1 ? styles.kv1 : styles.kv}>
      {items.map((it, i) => (
        <div className={styles.kvItem} key={i}>
          <span className={styles.kvLabel}>{it.label}</span>
          <span className={styles.kvValue}>{it.value}</span>
        </div>
      ))}
    </div>
  );
}

// ---------- Notices ----------

export function Notice({
  tone = 'info',
  children,
}: {
  tone?: 'info' | 'warn' | 'danger';
  children: ReactNode;
}) {
  const cls =
    tone === 'warn' ? styles.noticeWarn : tone === 'danger' ? styles.noticeDanger : styles.noticeInfo;
  return (
    <div className={`${styles.notice} ${cls}`}>
      <span className={styles.noticeIcon}>{tone === 'warn' ? '⚠' : tone === 'danger' ? '✕' : 'ℹ'}</span>
      <div>{children}</div>
    </div>
  );
}

// ---------- Buttons ----------

export function Button({
  children,
  onClick,
  variant = 'default',
  size = 'md',
  disabled,
  type = 'button',
  title,
}: {
  children: ReactNode;
  onClick?: () => void;
  variant?: 'default' | 'primary' | 'danger' | 'ghost';
  size?: 'sm' | 'md';
  disabled?: boolean;
  type?: 'button' | 'submit';
  title?: string;
}) {
  const cls = [
    styles.btn,
    variant === 'primary' ? styles.btnPrimary : '',
    variant === 'danger' ? styles.btnDanger : '',
    variant === 'ghost' ? styles.btnGhost : '',
    size === 'sm' ? styles.btnSm : '',
  ]
    .filter(Boolean)
    .join(' ');
  return (
    <button type={type} className={cls} onClick={onClick} disabled={disabled} title={title}>
      {children}
    </button>
  );
}

// ---------- Form controls ----------

export function Field({
  label,
  children,
  hint,
}: {
  label: ReactNode;
  children: ReactNode;
  hint?: ReactNode;
}) {
  return (
    <label className={styles.field}>
      <span className={styles.fieldLabel}>{label}</span>
      {children}
      {hint && <span className={styles.hint}>{hint}</span>}
    </label>
  );
}

export function NumberField({
  label,
  value,
  onChange,
  step,
  min,
  max,
  hint,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
  step?: number;
  min?: number;
  max?: number;
  hint?: string;
}) {
  return (
    <Field label={label} hint={hint}>
      <input
        type="number"
        className={styles.input}
        value={value}
        step={step}
        min={min}
        max={max}
        onChange={(e) => {
          const v = parseFloat(e.target.value);
          if (!Number.isNaN(v)) onChange(v);
        }}
      />
    </Field>
  );
}

// ---------- Segmented control ----------

export function Segmented<T extends string>({
  options,
  value,
  onChange,
}: {
  options: Array<{ value: T; label: string }>;
  value: T;
  onChange: (v: T) => void;
}) {
  return (
    <div className={styles.seg}>
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          className={`${styles.segBtn} ${o.value === value ? styles.segBtnActive : ''}`}
          onClick={() => onChange(o.value)}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

// ---------- JSON block ----------

export function JsonBlock({ data, maxHeight }: { data: unknown; maxHeight?: number }) {
  const style: CSSProperties | undefined = maxHeight ? { maxHeight } : undefined;
  return (
    <pre className={styles.json} style={style}>
      {JSON.stringify(data, null, 2)}
    </pre>
  );
}

// ---------- Section ----------

export function Section({ title, children }: { title: ReactNode; children: ReactNode }) {
  return (
    <div className={styles.section}>
      <h3 className={styles.sectionTitle}>{title}</h3>
      {children}
    </div>
  );
}
