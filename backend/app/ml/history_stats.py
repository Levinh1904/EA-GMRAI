"""Statistics over regime segments/bars — pure functions, JSON-friendly output.

All thresholds are explicit, documented and configurable; strength classes
use quantiles of the segment population itself (never hand-picked cutoffs).
"""
from __future__ import annotations

import math
from collections import Counter, defaultdict
from datetime import datetime

import numpy as np
import pandas as pd

from app.ml.evaluation import classification_metrics, detection_metrics, false_trend_rate
from app.ml.regime_engine import OPERATIONAL_REGIMES

STATS_REGIMES = ["TREND_UP", "TREND_DOWN", "SIDEWAYS", "EARLY_TREND", "TRANSITION", "HIGH_VOLATILITY", "UNKNOWN"]

DEFAULT_SIDEWAYS_BUCKETS = [  # minutes, upper bound inclusive
    ("<30m", 0, 30),
    ("30m-1h", 30, 60),
    ("1h-2h", 60, 120),
    ("2h-4h", 120, 240),
    ("4h-8h", 240, 480),
    (">8h", 480, None),
]


def _group_regime(regime: str) -> str:
    if regime in ("EARLY_TREND_UP", "EARLY_TREND_DOWN"):
        return "EARLY_TREND"
    if regime == "INSUFFICIENT_DATA":
        return "UNKNOWN"
    return regime


def _seg_df(segments: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(segments)
    if len(df) == 0:
        return df
    df["regime_group"] = df["regime"].map(_group_regime)
    return df


# ---------------------------------------------------------------- durations

def duration_statistics(segments: list[dict]) -> dict:
    df = _seg_df(segments)
    out: dict[str, dict] = {}
    total_minutes = int(df["duration_minutes"].sum()) if len(df) else 0
    if len(df):
        span_days = max(
            (
                pd.to_datetime(df["end_ts"], utc=True).max()
                - pd.to_datetime(df["start_ts"], utc=True).min()
            ).days,
            1,
        )
    else:
        span_days = 1
    for regime in STATS_REGIMES:
        sub = df[df["regime_group"] == regime] if len(df) else df
        if len(sub) == 0:
            out[regime] = {"occurrences": 0, "total_minutes": 0, "occupancy_pct": 0.0,
                           "mean_minutes": None, "median_minutes": None, "longest_minutes": None,
                           "shortest_minutes": None, "p25": None, "p75": None, "p90": None,
                           "avg_per_day": 0.0}
            continue
        d = sub["duration_minutes"]
        out[regime] = {
            "occurrences": int(len(sub)),
            "total_minutes": int(d.sum()),
            "occupancy_pct": round(100.0 * d.sum() / total_minutes, 2) if total_minutes else 0.0,
            "mean_minutes": round(float(d.mean()), 1),
            "median_minutes": round(float(d.median()), 1),
            "longest_minutes": int(d.max()),
            "shortest_minutes": int(d.min()),
            "p25": round(float(d.quantile(0.25)), 1),
            "p75": round(float(d.quantile(0.75)), 1),
            "p90": round(float(d.quantile(0.90)), 1),
            "avg_per_day": round(float(len(sub) / span_days), 2),
        }
    return out


def transition_count(segments: list[dict]) -> int:
    df = _seg_df(segments)
    return max(int((df["regime_group"] != df["regime_group"].shift()).sum()) - 1, 0) if len(df) > 1 else 0


# ---------------------------------------------------------------- trends

def trend_analysis(segments: list[dict], strength_method: str = "quantile") -> dict:
    df = _seg_df(segments)
    trend = df[df["regime_group"].isin(["TREND_UP", "TREND_DOWN"])] if len(df) else df
    out = {"method": strength_method,
           "strength_note": ("Quantile-based on efficiency_ratio + ADX of the trend segment "
                             "population: strong >= p75, weak <= p25, else medium. "
                             "Configurable via ?strength_method / thresholds.")}
    for regime in ("TREND_UP", "TREND_DOWN"):
        sub = trend[trend["regime_group"] == regime] if len(trend) else trend
        if len(sub) == 0:
            out[regime] = {"count": 0}
            continue
        d = sub["duration_minutes"]
        speed = sub["net_change"].abs() / d.replace(0, np.nan)  # USD per minute
        out[regime] = {
            "count": int(len(sub)),
            "total_minutes": int(d.sum()),
            "mean_minutes": round(float(d.mean()), 1),
            "median_minutes": round(float(d.median()), 1),
            "longest_minutes": int(d.max()),
            "shortest_minutes": int(d.min()),
            "mean_speed_usd_per_min": round(float(speed.mean()), 3),
            "mean_net_change": round(float(sub["net_change"].mean()), 3),
            "mean_mfe": round(float(sub["mfe"].mean()), 3),
            "mean_mae": round(float(sub["mae"].mean()), 3),
            "mean_atr_ratio": round(float(sub["atr_mean"].mean()), 4),
            "mean_adx_norm": round(float(sub["adx_mean"].mean()), 4),
            "mean_efficiency": round(float(sub["efficiency_mean"].mean()), 4),
            "mean_bar_count": round(float(sub["bar_count"].mean()), 1),
        }
    # strength classification (documented quantile method)
    if len(trend):
        strength_score = 0.5 * trend["efficiency_mean"] + 0.5 * trend["adx_mean"]
        q25, q75 = strength_score.quantile(0.25), strength_score.quantile(0.75)
        trend = trend.assign(
            strength=np.where(
                strength_score >= q75, "strong",
                np.where(strength_score <= q25, "weak", "medium"),
            )
        )
        out["strength"] = {
            "score_formula": "0.5 * efficiency_mean + 0.5 * adx_norm",
            "q25": round(float(q25), 4),
            "q75": round(float(q75), 4),
            "distribution": {
                f"{regime}|{strength}": int(v)
                for (regime, strength), v in trend.groupby(["regime_group", "strength"]).size().to_dict().items()
            },
        }
    return out


# ---------------------------------------------------------------- sideways

def sideways_analysis(
    segments: list[dict],
    buckets: list[tuple[str, float, float | None]] | None = None,
) -> dict:
    buckets = buckets or DEFAULT_SIDEWAYS_BUCKETS
    df = _seg_df(segments)
    out: dict = {"bucket_note": "Duration buckets in minutes, configurable via ?buckets.",
                 "buckets": {}}
    if len(df) == 0:
        for name, _, _ in buckets:
            out["buckets"][name] = 0
        out.update({"count": 0, "total_minutes": 0})
        return out
    side = df[df["regime_group"] == "SIDEWAYS"]

    d = side["duration_minutes"]
    for name, lo, hi in buckets:
        mask = d >= lo
        if hi is not None:
            mask &= d <= hi
        out["buckets"][name] = int(mask.sum())
    width = side["high_price"] - side["low_price"]
    # breakout analysis from the full ordered segment sequence
    full = df.sort_values("segment_index").reset_index(drop=True)
    next_regimes: list[str] = []
    breakouts = 0
    false_breakouts = 0
    min_trend_bars = 4  # documented heuristic: breakout trend < 4 bars then sideways again
    for i, s in enumerate(full.to_dict("records")):
        if s["regime_group"] != "SIDEWAYS":
            continue
        if i + 1 >= len(full):
            break
        nxt = full.iloc[i + 1]
        nr = nxt["regime_group"]
        next_regimes.append(nr)
        if nr in ("TREND_UP", "TREND_DOWN"):
            breakouts += 1
            if nxt["bar_count"] < min_trend_bars and i + 2 < len(full) and full.iloc[i + 2]["regime_group"] == "SIDEWAYS":
                false_breakouts += 1
    out.update({
        "count": int(len(side)),
        "total_minutes": int(d.sum()),
        "mean_minutes": round(float(d.mean()), 1),
        "median_minutes": round(float(d.median()), 1),
        "longest_minutes": int(d.max()),
        "shortest_minutes": int(d.min()),
        "mean_range_width": round(float(width.mean()), 3),
        "mean_range_high": round(float(side["high_price"].mean()), 3),
        "mean_range_low": round(float(side["low_price"].mean()), 3),
        "mean_atr_ratio": round(float(side["atr_mean"].mean()), 4),
        "mean_adx_norm": round(float(side["adx_mean"].mean()), 4),
        "mean_efficiency": round(float(side["efficiency_mean"].mean()), 4),
        "mean_touches_high": round(float(side["range_touches_high"].mean()), 1),
        "mean_touches_low": round(float(side["range_touches_low"].mean()), 1),
        "breakouts": breakouts,
        "false_breakouts": false_breakouts,
        "false_breakout_rule": "breakout trend segment < 4 bars followed by SIDEWAYS",
        "next_regime_distribution": dict(Counter(next_regimes)),
    })
    return out


# ---------------------------------------------------------------- early trend

def early_trend_analysis(
    bars: pd.DataFrame,
    labels: pd.Series,
    window: int = 12,
) -> dict:
    """Evaluate Early Trend signals against REALIZED reference labels.

    Future data (labels from forward returns) is used ONLY for evaluation,
    never to generate the signals themselves. The signals come from the
    causal per-bar regime stored in `bars`.
    """
    out: dict = {}
    regime = np.asarray(bars["regime"])
    lab = labels.reindex(bars.index).values
    for direction, target, wrong in (
        ("EARLY_TREND_UP", "TREND_UP", "TREND_DOWN"),
        ("EARLY_TREND_DOWN", "TREND_DOWN", "TREND_UP"),
    ):
        signals = np.where(regime == direction)[0]
        outcomes = []
        delays = []
        for t in signals:
            win = lab[t + 1 : t + 1 + window]
            win = win[~pd.isna(win)]
            if len(win) == 0:
                outcomes.append("no_data")
                continue
            if target in win:
                outcomes.append("confirmed")
                delays.append(int(np.where(win == target)[0][0]) + 1)
            elif wrong in win:
                outcomes.append("wrong_direction")
            else:
                outcomes.append("no_trend")
        counts = Counter(outcomes)
        confirmed = counts.get("confirmed", 0)
        total = len(signals)
        out[direction] = {
            "signals": total,
            "confirmed": confirmed,
            "wrong_direction": counts.get("wrong_direction", 0),
            "no_trend": counts.get("no_trend", 0),
            "no_data": counts.get("no_data", 0),
            "success_rate_pct": round(100.0 * confirmed / total, 1) if total else None,
            "false_rate_pct": round(100.0 * (total - confirmed) / total, 1) if total else None,
            "mean_detection_delay_bars": round(float(np.mean(delays)), 1) if delays else None,
            "window_bars": window,
        }
    out["note"] = (
        "Reference labels are REALIZED forward returns (12 bars vs 0.75 ATR) computed "
        "after the fact — used for evaluation only; signals themselves are causal."
    )
    return out


# ---------------------------------------------------------------- transitions

def transition_matrix(segments: list[dict]) -> dict:
    df = _seg_df(segments)
    regs = [r for r in STATS_REGIMES if (df["regime_group"] == r).any()] if len(df) else []
    pairs: Counter = Counter()
    dur_by_src: dict[str, list[float]] = defaultdict(list)
    for i in range(len(df) - 1):
        a = df["regime_group"].iloc[i]
        b = df["regime_group"].iloc[i + 1]
        if a != b:
            pairs[(a, b)] += 1
            dur_by_src[a].append(float(df["duration_minutes"].iloc[i]))
    matrix = {a: {b: int(pairs.get((a, b), 0)) for b in regs} for a in regs}
    rates = {}
    for a in regs:
        total = sum(matrix[a].values())
        rates[a] = {b: round(v / total, 3) if total else 0.0 for b, v in matrix[a].items()}
    mean_before = {
        a: round(float(np.mean(dur_by_src[a])), 1) if dur_by_src[a] else None for a in regs
    }
    return {
        "regimes": regs,
        "counts": matrix,
        "rates": rates,
        "mean_source_duration_minutes": mean_before,
        "total_transitions": int(sum(pairs.values())),
        "note": "Frequencies of OPERATIONAL regime changes (from segments). Distinct from the "
                "HMM's intrinsic transition probabilities (see /models/{hmm_id} transition matrix).",
    }


# ---------------------------------------------------------------- daily/weekly

def period_aggregation(bars: pd.DataFrame, segments: list[dict], period: str = "day") -> dict:
    freq = {"day": "D", "week": "W-MON", "month": "ME", "quarter": "QE", "year": "YE"}[period]
    b = bars.copy()
    b["bucket"] = b.index.to_period(freq).to_timestamp()
    b["regime_group"] = b["regime"].map(_group_regime)
    seg = _seg_df(segments)
    if len(seg):
        seg["bucket"] = pd.to_datetime(seg["start_ts"], utc=True).dt.to_period(freq).dt.to_timestamp()

    rows = []
    for bucket, grp in b.groupby("bucket"):
        minutes = {r: int((grp["regime_group"] == r).sum() * 15) for r in STATS_REGIMES}
        dominant = max(minutes, key=minutes.get) if any(minutes.values()) else "UNKNOWN"
        seg_count = int((seg["bucket"] == bucket).sum()) if len(seg) else 0
        rows.append(
            {
                "period_start": bucket.isoformat(),
                **{f"{r.lower().replace('_', '_')}_minutes": minutes[r] for r in STATS_REGIMES},
                "segments": seg_count,
                "dominant_regime": dominant,
                "range_usd": round(float(grp["high"].max() - grp["low"].min()), 3),
            }
        )
    return {"period": period, "rows": sorted(rows, key=lambda r: r["period_start"])}


# ---------------------------------------------------------------- multi-TF

def multi_tf_context(
    bars: pd.DataFrame,
    h1_threshold: float = 0.15,
    m5_threshold: float = 0.5,
) -> dict:
    """Compare M15 operational regime with H1 context and M5 timing signals
    (real features computed causally — NOT standalone AI regimes)."""
    def cls(v, th):
        if v is None or pd.isna(v):
            return "NODATA"
        return "UP" if v > th else ("DOWN" if v < -th else "SIDEWAYS")

    h1 = [cls(v, h1_threshold) for v in bars["h1_trend_context"]]
    m5 = [cls(v, m5_threshold) for v in bars["m5_momentum"]]
    m15 = []
    consensus = []
    for r, a, b in zip(bars["regime"], h1, m5):
        if r in ("TREND_UP", "EARLY_TREND_UP"):
            m15.append("UP")
        elif r in ("TREND_DOWN", "EARLY_TREND_DOWN"):
            m15.append("DOWN")
        else:
            m15.append("NEUTRAL")
        if m15[-1] in ("UP", "DOWN") and a == m15[-1] and b == m15[-1]:
            consensus.append(f"CONSENSUS_{m15[-1]}")
        elif m15[-1] in ("UP", "DOWN") and a != m15[-1] and b != m15[-1]:
            consensus.append("CONFLICT_BOTH")
        elif m15[-1] in ("UP", "DOWN") and a != m15[-1]:
            consensus.append("CONFLICT_H1")
        elif m15[-1] in ("UP", "DOWN") and b != m15[-1]:
            consensus.append("CONFLICT_M5")
        else:
            consensus.append("NEUTRAL")

    counts = Counter(consensus)
    total = len(consensus) or 1

    def runs(seq):
        lens, cur, n = [], seq[0], 0
        for v in seq:
            if v == cur:
                n += 1
            else:
                lens.append((cur, n))
                cur, n = v, 1
        lens.append((cur, n))
        return lens

    run_lens = defaultdict(list)
    for v, n in runs(consensus):
        run_lens[v].append(n * 15)

    sample = pd.DataFrame(
        {"ts": [t.isoformat() for t in bars.index],
         "m15_regime": list(bars["regime"]),
         "m5_timing": m5,
         "h1_context": h1,
         "agreement": consensus}
    ).tail(200)

    return {
        "thresholds": {"h1_trend_context": h1_threshold, "m5_momentum": m5_threshold},
        "note": "M5/H1 columns are real FEATURE-based timing/context signals, not AI regimes.",
        "counts": {k: int(v) for k, v in counts.items()},
        "occupancy_pct": {k: round(100.0 * v / total, 2) for k, v in counts.items()},
        "mean_duration_minutes": {k: round(float(np.mean(run_lens[k])), 1) for k in run_lens},
        "sample": sample.to_dict("records"),
    }


# ---------------------------------------------------------------- comparison

def compare_runs(bars_a: pd.DataFrame, bars_b: pd.DataFrame, name_a: str, name_b: str) -> dict:
    merged = bars_a[["regime"]].join(bars_b[["regime"]], lsuffix="_a", rsuffix="_b", how="inner")
    merged = merged.dropna()
    if len(merged) == 0:
        return {"error": "no overlapping bars"}
    regs = sorted(set(merged["regime_a"]) | set(merged["regime_b"]))
    counts = {}
    for a in regs:
        row = {}
        for b in regs:
            row[b] = int(((merged["regime_a"] == a) & (merged["regime_b"] == b)).sum())
        counts[a] = row
    agree = int((merged["regime_a"] == merged["regime_b"]).sum())
    return {
        "names": [name_a, name_b],
        "overlap_bars": len(merged),
        "agreement_rate": round(agree / len(merged), 4),
        "confusion_counts": counts,
        "duration_minutes": {
            name_a: {r: int((merged["regime_a"] == r).sum() * 15) for r in regs},
            name_b: {r: int((merged["regime_b"] == r).sum() * 15) for r in regs},
        },
        "segment_counts": {
            name_a: int(_segments_in(merged["regime_a"])),
            name_b: int(_segments_in(merged["regime_b"])),
        },
    }


def _segments_in(series: pd.Series) -> int:
    return int((series != series.shift()).sum() - (1 if len(series) else 0)) if len(series) else 0


def compare_vs_reference(bars: pd.DataFrame, labels: pd.Series) -> dict:
    """Compare the operational regime against realized reference labels."""
    scored = bars["regime"].replace(
        {
            "TRANSITION": "SIDEWAYS",
            "HIGH_VOLATILITY": "SIDEWAYS",
            "UNKNOWN": "SIDEWAYS",
            "EARLY_TREND_UP": "SIDEWAYS",
            "EARLY_TREND_DOWN": "SIDEWAYS",
            "INSUFFICIENT_DATA": "SIDEWAYS",
        }
    )
    lab = labels.reindex(bars.index).dropna()
    idx = lab.index
    cls = classification_metrics(lab, scored.reindex(idx))
    return {
        "reference_note": "Reference labels = realized forward returns (12 bars vs 0.75 ATR). "
                          "Evaluation only — not ground truth.",
        "classification": cls,
        "false_trend_rate": false_trend_rate(lab, scored.reindex(idx)),
        "detection": detection_metrics(lab, scored.reindex(idx)),
    }
