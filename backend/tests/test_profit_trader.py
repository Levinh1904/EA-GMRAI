"""Barrier semantics: independent LONG/SHORT paths and SL-before-TP."""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.ml.profit_trader import (
    BarrierConfig,
    barrier_outcomes,
    probs_to_signal,
    run_policy,
    summarize_trades,
)


def _flat(n: int = 80) -> pd.DataFrame:
    idx = pd.date_range("2026-01-01", periods=n, freq="15min", tz="UTC")
    return pd.DataFrame(
        {
            "open": 2000.0,
            "high": 2001.0,
            "low": 1999.0,
            "close": 2000.0,
            "spread": 0.0,
        },
        index=idx,
    )


def test_long_and_short_outcomes_are_simulated_independently():
    df = _flat()
    t = 30
    # Long TP=$2001 first, then short TP=$1999 on the next candle.
    df.iloc[t + 1, df.columns.get_loc("high")] = 2001.5
    df.iloc[t + 1, df.columns.get_loc("low")] = 1999.5
    df.iloc[t + 2, df.columns.get_loc("high")] = 2000.5
    df.iloc[t + 2, df.columns.get_loc("low")] = 1998.5
    out = barrier_outcomes(df, BarrierConfig(horizon=4))
    row = out.iloc[t]
    assert bool(row["valid"])
    assert row["long_exit_reason"] == "TP"
    assert row["short_exit_reason"] == "TP"
    assert row["pnl_long"] > 0
    assert row["pnl_short"] > 0
    assert row["long_exit_ts"] != row["short_exit_ts"]


def test_stop_loss_wins_when_both_levels_are_touched_in_same_candle():
    df = _flat()
    t = 30
    # ATR is 2; long TP=2001, long SL=1996, both touched on the same bar.
    df.iloc[t + 1, df.columns.get_loc("high")] = 2002.0
    df.iloc[t + 1, df.columns.get_loc("low")] = 1995.0
    out = barrier_outcomes(df, BarrierConfig(horizon=4))
    row = out.iloc[t]
    assert bool(row["valid_long"])
    assert row["long_exit_reason"] == "SL"
    assert row["pnl_long"] < 0


def test_short_only_ignores_high_long_probability():
    idx = pd.date_range("2026-01-01", periods=3, freq="15min", tz="UTC")
    p_long = pd.Series([0.99, 0.40, 0.80], index=idx)
    p_short = pd.Series([0.80, 0.90, 0.60], index=idx)

    both = probs_to_signal(p_long, p_short, 0.85)
    assert both.tolist() == ["LONG", "SHORT", "NO_TRADE"]

    short_only = probs_to_signal(
        p_long, p_short, 0.85, allowed_sides=("SHORT",)
    )
    assert short_only.tolist() == ["NO_TRADE", "SHORT", "NO_TRADE"]


def test_policy_uses_one_position_and_skips_until_exit():
    idx = pd.date_range("2026-01-01", periods=8, freq="15min", tz="UTC")
    signals = pd.Series(["LONG", "LONG", "NO_TRADE", "SHORT", "NO_TRADE", "NO_TRADE", "NO_TRADE", "NO_TRADE"], index=idx)
    outcomes = pd.DataFrame(
        {
            "valid": True,
            "valid_long": True,
            "valid_short": True,
            "entry_ts": idx + pd.Timedelta(minutes=15),
            "long_exit_ts": idx + pd.Timedelta(minutes=45),
            "short_exit_ts": idx + pd.Timedelta(minutes=45),
            "long_exit_reason": "TP",
            "short_exit_reason": "TP",
            "pnl_long": 1.0,
            "pnl_short": 2.0,
        },
        index=idx,
    )
    trades = run_policy(signals, outcomes, start=0, end=len(signals))
    assert [t["direction"] for t in trades] == ["LONG"]
    assert summarize_trades(trades)["n"] == 1
