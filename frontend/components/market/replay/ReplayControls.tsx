'use client';

// Top-bar controls for the Historical Market Replay: UTC datetime picker,
// timeframe selector, transport (jump-to-start / step-back / play-pause /
// step-forward), playback speed, and the "now" cursor indicator.

import { Segmented } from '@/components/ui/ui';
import type { Timeframe } from '@/lib/types';
import styles from './replay.module.css';

const TF_OPTIONS: Timeframe[] = ['M5', 'M15', 'H1'];

const SPEED_OPTIONS: Array<{ value: string; label: string }> = [
  { value: '0.5', label: '0.5x' },
  { value: '1', label: '1x' },
  { value: '2', label: '2x' },
  { value: '4', label: '4x' },
  { value: '8', label: '8x' },
];

interface ReplayControlsProps {
  timeframe: Timeframe;
  onTimeframeChange: (tf: Timeframe) => void;
  anchorInput: string;
  onAnchorInput: (value: string) => void;
  playing: boolean;
  onTogglePlay: () => void;
  onJumpToStart: () => void;
  onStepBack: () => void;
  onStepForward: () => void;
  speed: number;
  onSpeedChange: (s: number) => void;
  canBack: boolean;
  canForward: boolean;
  nowText: string;
  disabled: boolean;
}

export function ReplayControls({
  timeframe,
  onTimeframeChange,
  anchorInput,
  onAnchorInput,
  playing,
  onTogglePlay,
  onJumpToStart,
  onStepBack,
  onStepForward,
  speed,
  onSpeedChange,
  canBack,
  canForward,
  nowText,
  disabled,
}: ReplayControlsProps) {
  return (
    <div className={styles.controlsBar}>
      <label className={styles.dtField}>
        <span className={styles.dtLabel}>Thời điểm bắt đầu (UTC)</span>
        <input
          type="datetime-local"
          className={styles.dtInput}
          value={anchorInput}
          onChange={(e) => onAnchorInput(e.target.value)}
          disabled={disabled}
        />
      </label>

      <div className={styles.controlsGroup} role="group" aria-label="Khung thời gian">
        <span className={styles.groupLabel}>TF</span>
        {TF_OPTIONS.map((tf) => (
          <button
            key={tf}
            type="button"
            className={`${styles.toolBtn} ${timeframe === tf ? styles.toolBtnActive : ''}`}
            onClick={() => onTimeframeChange(tf)}
            title={`Khung thời gian ${tf}`}
            aria-pressed={timeframe === tf}
          >
            {tf}
          </button>
        ))}
      </div>

      <div className={styles.controlsDivider} />

      <div className={styles.controlsGroup} role="group" aria-label="Điều khiển phát">
        <button
          type="button"
          className={styles.transportBtn}
          onClick={onJumpToStart}
          disabled={disabled || !canBack}
          title="Nhảy về nến đầu tiên"
          aria-label="Nhảy về đầu"
        >
          ⏮
        </button>
        <button
          type="button"
          className={styles.transportBtn}
          onClick={onStepBack}
          disabled={disabled || !canBack}
          title="Nến trước"
          aria-label="Nến trước"
        >
          ◀
        </button>
        <button
          type="button"
          className={`${styles.transportBtn} ${styles.playBtn}`}
          onClick={onTogglePlay}
          disabled={disabled}
          title={playing ? 'Tạm dừng' : 'Phát'}
          aria-label={playing ? 'Tạm dừng' : 'Phát'}
        >
          {playing ? '⏸' : '▶'}
        </button>
        <button
          type="button"
          className={styles.transportBtn}
          onClick={onStepForward}
          disabled={disabled || !canForward}
          title="Nến tiếp theo"
          aria-label="Nến tiếp theo"
        >
          ▶
        </button>
      </div>

      <div className={styles.controlsGroup} role="group" aria-label="Tốc độ phát">
        <span className={styles.groupLabel}>Tốc độ</span>
        <Segmented
          options={SPEED_OPTIONS}
          value={String(speed)}
          onChange={(v) => onSpeedChange(parseFloat(v))}
        />
      </div>

      <div className={styles.controlsSpacer} />

      <div className={styles.nowIndicator}>
        <span className={styles.nowDot} />
        <span className={styles.nowLabel} title="Vị trí con trỏ phát lại">
          {nowText}
        </span>
      </div>
    </div>
  );
}
