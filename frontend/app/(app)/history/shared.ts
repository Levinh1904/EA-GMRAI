// Shared helpers for the Historical Market Regime Analyzer page.
'use client';

import { useEffect, useState } from 'react';
import { fetchModelArtifactJson } from '@/lib/api';
import { fmtNum, fmtPrice, fmtUtc } from '@/lib/format';
import { regimeColor } from '@/lib/regime';
import type { HmmArtifact } from '@/lib/types';

/** Canonical order used to render regime tables/charts consistently. */
export const REGIME_ORDER: Array<{ key: string; label: string; color: string }> = [
  { key: 'TREND_UP', label: 'Tăng', color: regimeColor('TREND_UP') },
  { key: 'TREND_DOWN', label: 'Giảm', color: regimeColor('TREND_DOWN') },
  { key: 'SIDEWAYS', label: 'Đi ngang', color: regimeColor('SIDEWAYS') },
  { key: 'EARLY_TREND', label: 'Tín hiệu sớm', color: regimeColor('EARLY_TREND') },
  { key: 'TRANSITION', label: 'Chuyển tiếp', color: regimeColor('TRANSITION') },
  { key: 'HIGH_VOLATILITY', label: 'Biến động cao', color: regimeColor('HIGH_VOLATILITY') },
  { key: 'UNKNOWN', label: 'Không xác định', color: regimeColor('UNKNOWN') },
];

/** Palette for the 5 HMM latent states. */
export const HMM_STATE_COLORS = ['#4c8dff', '#14b8a6', '#f59e0b', '#a855f7', '#22c55e'];

/** "191.3 phút" */
export function fmtMin(v: number | null | undefined): string {
  return v == null || Number.isNaN(v) ? '—' : `${fmtNum(v, 1)} phút`;
}

/** "720 phút (12.0 giờ)" */
export function fmtMinHours(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return '—';
  return `${fmtNum(v, 1)} phút (${fmtNum(v / 60, 1)} giờ)`;
}

/** "+12.34 USD" with sign. */
export function signedUsd(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return '—';
  return `${v >= 0 ? '+' : ''}${fmtPrice(v)} USD`;
}

/** "0.41 lần/ngày" */
export function fmtPerDay(v: number | null | undefined): string {
  return v == null || Number.isNaN(v) ? '—' : `${fmtNum(v, 2)} lần/ngày`;
}

export function fmtTs(iso: string | null | undefined): string {
  return fmtUtc(iso);
}

export interface HmmStateLabel {
  regime: string;
  reason: string | null;
}

/**
 * Loads the HMM artifact of the run's model version and extracts the
 * state_mapping (state index -> semantic regime). Falls back to {} on any error.
 */
export function useHmmStateMap(versionId: number | null | undefined): Record<string, HmmStateLabel> {
  const [map, setMap] = useState<Record<string, HmmStateLabel>>({});

  useEffect(() => {
    let cancelled = false;
    if (!versionId) {
      setMap({});
      return;
    }
    fetchModelArtifactJson<HmmArtifact>(versionId)
      .then((artifact) => {
        if (cancelled) return;
        const sm = artifact?.state_mapping;
        if (!sm || typeof sm !== 'object') {
          setMap({});
          return;
        }
        const next: Record<string, HmmStateLabel> = {};
        for (const [k, v] of Object.entries(sm)) {
          if (v && typeof v === 'object') {
            next[k] = {
              regime: typeof v.regime === 'string' ? v.regime : 'UNKNOWN',
              reason: typeof v.reason === 'string' ? v.reason : null,
            };
          }
        }
        setMap(next);
      })
      .catch(() => {
        if (!cancelled) setMap({});
      });
    return () => {
      cancelled = true;
    };
  }, [versionId]);

  return map;
}

/** Volume-agnostic regime set used for chart stacking. */
export const PERIOD_REGIME_FIELDS: Array<{ key: string; label: string; color: string }> = [
  { key: 'trend_up_minutes', label: 'Tăng', color: regimeColor('TREND_UP') },
  { key: 'trend_down_minutes', label: 'Giảm', color: regimeColor('TREND_DOWN') },
  { key: 'sideways_minutes', label: 'Đi ngang', color: regimeColor('SIDEWAYS') },
  { key: 'early_trend_minutes', label: 'Tín hiệu sớm', color: regimeColor('EARLY_TREND') },
  { key: 'transition_minutes', label: 'Chuyển tiếp', color: regimeColor('TRANSITION') },
  { key: 'high_volatility_minutes', label: 'Biến động cao', color: regimeColor('HIGH_VOLATILITY') },
  { key: 'unknown_minutes', label: 'Không xác định', color: regimeColor('UNKNOWN') },
];

export function isEarlyRegime(r: string | null | undefined): boolean {
  return r === 'EARLY_TREND_UP' || r === 'EARLY_TREND_DOWN' || r === 'EARLY_TREND';
}
