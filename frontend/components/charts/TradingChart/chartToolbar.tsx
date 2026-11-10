'use client';

// Functional chart toolbar: symbol badge, timeframe switcher, range presets,
// zoom controls, view toggles (grid/crosshair/volume/auto-scale) and fullscreen.
// Signals toggle is intentionally disabled: the backend has no trade signals.

import { Icon } from '@/components/icons';
import type { Timeframe } from '@/lib/types';
import styles from './tradingchart.module.css';

export interface RangePreset {
  label: string;
  days: number | null;
}

export const RANGE_PRESETS: RangePreset[] = [
  { label: '1D', days: 1 },
  { label: '5D', days: 5 },
  { label: '1M', days: 30 },
  { label: '3M', days: 90 },
  { label: '6M', days: 180 },
  { label: '1Y', days: 365 },
  { label: 'TẤT CẢ', days: null },
];

const TF_OPTIONS: Timeframe[] = ['M5', 'M15', 'H1'];

interface ToolbarProps {
  timeframe: Timeframe;
  onTimeframeChange: (tf: Timeframe) => void;
  activeRange: string | null;
  onRange: (days: number | null, label: string) => void;
  onZoomIn: () => void;
  onZoomOut: () => void;
  onReset: () => void;
  onFitContent: () => void;
  autoScale: boolean;
  onAutoScaleToggle: () => void;
  showGrid: boolean;
  onGridToggle: () => void;
  showCrosshair: boolean;
  onCrosshairToggle: () => void;
  showVolume: boolean;
  onVolumeToggle: () => void;
  showEma: boolean;
  onEmaToggle: () => void;
  showAiBands: boolean;
  onAiBandsToggle: () => void;
  showRefBands: boolean;
  onRefBandsToggle: () => void;
  onFullscreen: () => void;
}

function ToolButton({
  label,
  title,
  active,
  onClick,
  disabled,
  icon,
}: {
  label?: string;
  title: string;
  active?: boolean;
  onClick: () => void;
  disabled?: boolean;
  icon?: string;
}) {
  return (
    <button
      type="button"
      className={`${styles.toolBtn} ${active ? styles.toolBtnActive : ''}`}
      onClick={onClick}
      disabled={disabled}
      title={title}
      aria-pressed={active}
    >
      {icon && <Icon name={icon} size={14} />}
      {label && <span>{label}</span>}
    </button>
  );
}

export function ChartToolbar(props: ToolbarProps) {
  return (
    <div className={styles.toolbar}>
      <div className={styles.toolbarGroup}>
        <span className={styles.symbolBadge}>
          XAUUSD
          <span className={styles.symbolSub}>Vàng / USD</span>
        </span>
      </div>

      <div className={styles.toolbarGroup} role="group" aria-label="Khung thời gian">
        {TF_OPTIONS.map((tf) => (
          <ToolButton
            key={tf}
            label={tf}
            title={`Khung thời gian ${tf}`}
            active={props.timeframe === tf}
            onClick={() => props.onTimeframeChange(tf)}
          />
        ))}
      </div>

      <div className={styles.toolbarDivider} />

      <div className={styles.toolbarGroup} role="group" aria-label="Phạm vi thời gian">
        {RANGE_PRESETS.map((p) => (
          <ToolButton
            key={p.label}
            label={p.label}
            title={p.days == null ? 'Toàn bộ dữ liệu đã tải' : `Hiển thị ${p.days} ngày gần nhất`}
            active={props.activeRange === p.label}
            onClick={() => props.onRange(p.days, p.label)}
          />
        ))}
      </div>

      <div className={styles.toolbarDivider} />

      <div className={styles.toolbarGroup} role="group" aria-label="Thu phóng">
        <ToolButton icon="zoomIn" title="Phóng to" onClick={props.onZoomIn} />
        <ToolButton icon="zoomOut" title="Thu nhỏ" onClick={props.onZoomOut} />
        <ToolButton icon="reset" title="Đặt lại về mặc định" onClick={props.onReset} />
        <ToolButton icon="fit" title="Khớp toàn bộ dữ liệu (Fit Content)" onClick={props.onFitContent} />
      </div>

      <div className={styles.toolbarDivider} />

      <div className={styles.toolbarGroup} role="group" aria-label="Hiển thị">
        <ToolButton
          icon="layers"
          title="Tự động co giãn trục giá"
          active={props.autoScale}
          onClick={props.onAutoScaleToggle}
        />
        <ToolButton
          icon="grid"
          title="Hiện/ẩn lưới"
          active={props.showGrid}
          onClick={props.onGridToggle}
        />
        <ToolButton
          icon="crosshair"
          title="Hiện/ẩn crosshair"
          active={props.showCrosshair}
          onClick={props.onCrosshairToggle}
        />
        <ToolButton
          icon="volume"
          title="Hiện/ẩn khối lượng"
          active={props.showVolume}
          onClick={props.onVolumeToggle}
        />
        <ToolButton
          label="EMA20"
          title="Hiện/ẩn đường trung bình EMA20"
          active={props.showEma}
          onClick={props.onEmaToggle}
        />
        <ToolButton
          label="AI Regime"
          title="Hiện/ẩn vùng chế độ AI (từ run lịch sử mới nhất)"
          active={props.showAiBands}
          onClick={props.onAiBandsToggle}
        />
        <ToolButton
          label="Reference"
          title="Hiện/ẩn vùng chế độ Reference (động cơ quy tắc)"
          active={props.showRefBands}
          onClick={props.onRefBandsToggle}
        />
      </div>

      <div className={styles.toolbarSpacer} />

      <div className={styles.toolbarGroup} role="group" aria-label="Tín hiệu giao dịch">
        <button
          type="button"
          className={styles.toolBtn}
          disabled
          title="Chưa có dữ liệu tín hiệu — backend không cung cấp điểm BUY/SELL"
        >
          <Icon name="backtest" size={14} />
          <span>Tín hiệu</span>
        </button>
      </div>

      <div className={styles.toolbarGroup}>
        <ToolButton
          icon="maximize"
          title="Toàn màn hình"
          onClick={props.onFullscreen}
        />
      </div>
    </div>
  );
}
