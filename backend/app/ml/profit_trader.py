"""Barrier labels, one-position policy and honest trade metrics.

The barrier is deliberately conservative: stop-loss is checked before
take-profit when both are touched inside the same candle. Every PnL subtracts
the spread stored on the signal candle. Nothing here sends orders.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable

import numpy as np
import pandas as pd

from app.ml.indicators import atr

PERIOD_SECONDS = 900


@dataclass(frozen=True)
class BarrierConfig:
    tp_atr: float = 0.5
    sl_atr: float = 2.0
    horizon: int = 16
    point_usd: float = 0.01  # XAUUSD: 1 point = $0.01/oz
    gap_multiple: float = 1.5

    def to_dict(self) -> dict:
        return asdict(self)


def barrier_outcomes(
    df_m15: pd.DataFrame, cfg: BarrierConfig | None = None
) -> pd.DataFrame:
    """Compute long/short barrier outcomes for every M15 bar.

    Returns one row per input bar. ``valid=False`` and y/pnl = NaN when the
    horizon cannot be completed or the path crosses a data gap.
    """
    cfg = cfg or BarrierConfig()
    df = df_m15.sort_index()
    n = len(df)
    atr14 = atr(df, 14).to_numpy(dtype=float)
    opens = df["open"].to_numpy(dtype=float)
    highs = df["high"].to_numpy(dtype=float)
    lows = df["low"].to_numpy(dtype=float)
    closes = df["close"].to_numpy(dtype=float)
    spreads = (
        df["spread"].to_numpy(dtype=float)
        if "spread" in df.columns
        else np.zeros(n, dtype=float)
    )
    index = df.index

    rows: list[dict] = []
    for t in range(n):
        base = {
            "entry_idx": np.nan,
            "entry_ts": None,
            "entry_price": np.nan,
            "spread_usd": np.nan,
            "long_exit_idx": np.nan,
            "short_exit_idx": np.nan,
            "long_exit_ts": None,
            "short_exit_ts": None,
            "long_exit_reason": None,
            "short_exit_reason": None,
            "valid_long": False,
            "valid_short": False,
            "valid": False,
            "pnl_long": np.nan,
            "pnl_short": np.nan,
            "y_long": np.nan,
            "y_short": np.nan,
        }
        if t + cfg.horizon > n - 1 or not np.isfinite(atr14[t]) or atr14[t] <= 0:
            rows.append(base)
            continue

        entry = opens[t + 1]
        a = atr14[t]
        if not np.isfinite(entry) or entry <= 0:
            rows.append(base)
            continue
        spread_points = spreads[t]
        spread_usd = (
            max(float(spread_points), 0.0) * cfg.point_usd
            if np.isfinite(spread_points)
            else 0.0
        )

        def simulate_side(side: int) -> dict:
            """Simulate one side independently; SL is checked before TP."""
            if side == 1:
                tp = entry + cfg.tp_atr * a
                sl = entry - cfg.sl_atr * a
            else:
                tp = entry - cfg.tp_atr * a
                sl = entry + cfg.sl_atr * a
            for j in range(t + 1, t + cfg.horizon + 1):
                gap = (index[j] - index[j - 1]).total_seconds() > (
                    PERIOD_SECONDS * cfg.gap_multiple
                )
                if gap:
                    return {
                        "exit_idx": j - 1,
                        "exit_ts": index[j - 1],
                        "exit_price": float(closes[j - 1]),
                        "reason": "GAP",
                        "valid": False,
                    }
                hi, lo = float(highs[j]), float(lows[j])
                if side == 1:
                    if lo <= sl:
                        return {"exit_idx": j, "exit_ts": index[j], "exit_price": float(sl), "reason": "SL", "valid": True}
                    if hi >= tp:
                        return {"exit_idx": j, "exit_ts": index[j], "exit_price": float(tp), "reason": "TP", "valid": True}
                else:
                    if hi >= sl:
                        return {"exit_idx": j, "exit_ts": index[j], "exit_price": float(sl), "reason": "SL", "valid": True}
                    if lo <= tp:
                        return {"exit_idx": j, "exit_ts": index[j], "exit_price": float(tp), "reason": "TP", "valid": True}
                if j == t + cfg.horizon:
                    return {
                        "exit_idx": j,
                        "exit_ts": index[j],
                        "exit_price": float(closes[j]),
                        "reason": "TIME",
                        "valid": True,
                    }
            return {"exit_idx": None, "exit_ts": None, "exit_price": None, "reason": None, "valid": False}

        long_side = simulate_side(1)
        short_side = simulate_side(-1)
        if long_side["exit_price"] is None or short_side["exit_price"] is None:
            rows.append(base)
            continue
        pnl_long = float(long_side["exit_price"] - entry - spread_usd)
        pnl_short = float(entry - short_side["exit_price"] - spread_usd)
        valid_long = bool(long_side["valid"])
        valid_short = bool(short_side["valid"])
        row = {
            "entry_idx": int(t + 1),
            "entry_ts": index[t + 1],
            "entry_price": float(entry),
            "spread_usd": float(spread_usd),
            "long_exit_idx": int(long_side["exit_idx"]),
            "short_exit_idx": int(short_side["exit_idx"]),
            "long_exit_ts": long_side["exit_ts"],
            "short_exit_ts": short_side["exit_ts"],
            "long_exit_reason": long_side["reason"],
            "short_exit_reason": short_side["reason"],
            "valid_long": valid_long,
            "valid_short": valid_short,
            "valid": bool(valid_long and valid_short),
            "pnl_long": pnl_long,
            "pnl_short": pnl_short,
            "y_long": float(pnl_long > 0) if valid_long and valid_short else np.nan,
            "y_short": float(pnl_short > 0) if valid_long and valid_short else np.nan,
        }
        rows.append(row)

    return pd.DataFrame(rows, index=df.index)


def probs_to_signal(
    p_long: Iterable[float],
    p_short: Iterable[float],
    threshold: float,
    allowed_sides: tuple[str, ...] = ("LONG", "SHORT"),
    long_threshold: float | None = None,
    short_threshold: float | None = None,
) -> pd.Series:
    pl = np.asarray(list(p_long), dtype=float)
    ps = np.asarray(list(p_short), dtype=float)
    out = np.full(len(pl), "NO_TRADE", dtype=object)
    lt = threshold if long_threshold is None else long_threshold
    st = threshold if short_threshold is None else short_threshold
    if "LONG" in allowed_sides:
        long_mask = (pl >= lt) & (pl >= ps)
        out[long_mask] = "LONG"
    if "SHORT" in allowed_sides:
        short_mask = (ps >= st) & (ps > pl)
        out[short_mask] = "SHORT"
    return pd.Series(out, index=getattr(p_long, "index", None))


def run_policy(
    signals: pd.Series,
    outcomes: pd.DataFrame,
    start: int = 0,
    end: int | None = None,
) -> list[dict]:
    """One-position policy using precomputed barrier outcomes.

    A signal at bar i enters at i+1 and exits according to the barrier outcome
    computed for bar i. No new position is opened until that trade exits.
    """
    end = len(signals) if end is None else min(end, len(signals))
    trades: list[dict] = []
    i = max(0, start)
    while i < end:
        sig = str(signals.iloc[i])
        if sig not in ("LONG", "SHORT"):
            i += 1
            continue
        row = outcomes.iloc[i]
        side = "long" if sig == "LONG" else "short"
        if not bool(row.get(f"valid_{side}", False)):
            i += 1
            continue
        entry_ts = row.get("entry_ts")
        exit_ts = row.get(f"{side}_exit_ts")
        if entry_ts is None or exit_ts is None:
            i += 1
            continue
        # The outcome indices live in the full M15 frame, while `signals` is the
        # feature-indexed frame (warmup rows were dropped). Use timestamps to
        # find the matching exit position, never the raw M15 integer index.
        exit_pos = int(signals.index.searchsorted(exit_ts, side="right")) - 1
        if i + 1 >= len(signals) or exit_pos <= i:
            i += 1
            continue
        pnl = float(row["pnl_long"] if side == "long" else row["pnl_short"])
        trades.append(
            {
                "direction": sig,
                "pnl": pnl,
                "entry_price": float(row["entry_price"])
                if row.get("entry_price") is not None and pd.notna(row.get("entry_price"))
                else None,
                "entry_idx": i + 1,
                "exit_idx": exit_pos,
                "entry_ts": signals.index[i + 1],
                "exit_ts": signals.index[exit_pos],
                "bars": exit_pos - (i + 1),
                "exit_reason": row.get(f"{side}_exit_reason"),
            }
        )
        i = max(exit_pos + 1, i + 1)
    return trades


def wilson_interval(wins: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n <= 0:
        return (0.0, 0.0)
    p = wins / n
    denom = 1.0 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def max_drawdown(pnls: Iterable[float]) -> float:
    equity = np.cumsum(np.asarray(list(pnls), dtype=float))
    if len(equity) == 0:
        return 0.0
    peak = np.maximum.accumulate(equity)
    return float((equity - peak).min())


def summarize_trades(trades: list[dict]) -> dict:
    if not trades:
        return {
            "n": 0, "wins": 0, "win_rate": None, "wilson_low": None, "wilson_high": None,
            "mean_pnl": 0.0, "total_pnl": 0.0, "profit_factor": None,
            "max_drawdown": 0.0, "t_stat": None, "avg_win": None, "avg_loss": None,
            "breakeven_win_rate": None, "equity_curve": [],
            "avg_entry_price": None, "mean_return_pct": None, "total_return_pct": None,
        }
    pnls = np.asarray([t["pnl"] for t in trades], dtype=float)
    wins = int((pnls > 0).sum())
    n = len(pnls)
    win_rate = wins / n
    lo, hi = wilson_interval(wins, n)
    gains = pnls[pnls > 0]
    losses = pnls[pnls < 0]
    avg_win = float(gains.mean()) if len(gains) else 0.0
    avg_loss = float(-losses.mean()) if len(losses) else 0.0
    gross_win = float(gains.sum())
    gross_loss = float(-losses.sum())
    std = float(pnls.std(ddof=1)) if n > 1 else 0.0
    entry_prices = [
        float(t["entry_price"])
        for t in trades
        if t.get("entry_price") is not None and np.isfinite(float(t["entry_price"]))
    ]
    returns_pct = [
        float(t["pnl"]) / float(t["entry_price"]) * 100.0
        for t in trades
        if t.get("entry_price") not in (None, 0)
    ]
    return {
        "n": n,
        "wins": wins,
        "win_rate": round(float(win_rate), 6),
        "wilson_low": round(float(lo), 6),
        "wilson_high": round(float(hi), 6),
        "mean_pnl": round(float(pnls.mean()), 6),
        "total_pnl": round(float(pnls.sum()), 6),
        "profit_factor": round(gross_win / gross_loss, 6) if gross_loss > 0 else None,
        "max_drawdown": round(max_drawdown(pnls), 6),
        "t_stat": round(float(pnls.mean() / (std / np.sqrt(n))), 6) if std > 0 else None,
        "avg_win": round(avg_win, 6),
        "avg_loss": round(avg_loss, 6),
        "breakeven_win_rate": round(avg_loss / (avg_win + avg_loss), 6)
        if (avg_win + avg_loss) > 0 else None,
        "equity_curve": [round(float(x), 6) for x in np.cumsum(pnls).tolist()],
        "avg_entry_price": round(float(np.mean(entry_prices)), 6) if entry_prices else None,
        "mean_return_pct": round(float(np.mean(returns_pct)), 6) if returns_pct else None,
        "total_return_pct": round(float(np.sum(returns_pct)), 6) if returns_pct else None,
    }


def choose_threshold(
    p_long: pd.Series,
    p_short: pd.Series,
    outcomes: pd.DataFrame,
    start: int,
    end: int,
    quantiles: tuple[float, ...] = (0.05, 0.10, 0.20, 0.30, 0.50),
    min_trades: int = 40,
    min_win_rate: float = 0.70,
    allowed_sides: tuple[str, ...] = ("LONG", "SHORT"),
    require_positive: bool = False,
) -> dict | None:
    """Choose a quantile threshold on a selection slice only.

    For a one-sided policy the quantile is computed from that side's own
    probability, not from max(p_long, p_short). This matters for SHORT-only:
    the long probability must not raise the short threshold.
    """
    if not allowed_sides:
        return None
    pl = p_long.iloc[start:end]
    ps = p_short.iloc[start:end]
    if len(pl) == 0:
        return None
    if len(allowed_sides) == 1 and allowed_sides[0] == "LONG":
        sample = pl.to_numpy()
    elif len(allowed_sides) == 1 and allowed_sides[0] == "SHORT":
        sample = ps.to_numpy()
    else:
        sample = np.maximum(pl.to_numpy(), ps.to_numpy())
    best = None
    for q in quantiles:
        threshold = float(np.quantile(sample, 1.0 - q))
        # Build signals on the FULL indexed series so an exit beyond the
        # selection slice can still be located by timestamp; entries remain
        # restricted to [start, end).
        signals = probs_to_signal(
            p_long, p_short, threshold, allowed_sides=allowed_sides
        )
        signals.index = p_long.index
        trades = run_policy(signals, outcomes, start=start, end=end)
        metrics = summarize_trades(trades)
        if metrics["n"] < min_trades or metrics["win_rate"] is None:
            continue
        if metrics["win_rate"] < min_win_rate:
            continue
        if require_positive and metrics["mean_pnl"] <= 0:
            continue
        candidate = {
            "q": q,
            "threshold": round(threshold, 6),
            "allowed_sides": list(allowed_sides),
            "selection_metrics": metrics,
        }
        if best is None or metrics["mean_pnl"] > best["selection_metrics"]["mean_pnl"]:
            best = candidate
    return best


__all__ = [
    "BarrierConfig",
    "barrier_outcomes",
    "choose_threshold",
    "max_drawdown",
    "probs_to_signal",
    "run_policy",
    "summarize_trades",
    "wilson_interval",
]
