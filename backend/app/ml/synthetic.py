"""Synthetic XAUUSD candle generation for development/testing.

ALWAYS labeled source='synthetic_demo'. Never used in production and never
displayed as live data (dashboard shows a clear DEMO DATA banner).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# regime params: (drift per bar, vol per bar)
REGIME_PARAMS = {
    0: (0.0, 0.0004),  # sideways
    1: (0.00035, 0.0008),  # trend up
    2: (-0.00035, 0.0008),  # trend down
    3: (0.0, 0.0025),  # high volatility
    4: (0.0, 0.0012),  # transition
}


def generate_synthetic_candles(
    n_m15: int = 12_000,
    seed: int = 42,
    start: str = "2025-06-01T00:00:00Z",
    price0: float = 2400.0,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, list[int]]:
    """Returns (df_m5, df_m15, df_h1, true_regimes).

    M5 bars are Brownian-bridged between consecutive M15 closes so all three
    timeframes are internally consistent.
    """
    rng = np.random.default_rng(seed)

    # piecewise regime process with mean duration ~200 bars
    true_regimes: list[int] = []
    state = 0
    for _ in range(n_m15):
        if rng.random() < 1 / 200:
            state = int(rng.integers(0, 5))
        true_regimes.append(state)

    closes = [price0]
    price = price0
    for r in true_regimes:
        mu, sigma = REGIME_PARAMS[r]
        price = price * np.exp(mu + sigma * rng.standard_normal())
        closes.append(price)
    closes = np.array(closes)

    times = pd.date_range(start, periods=n_m15, freq="15min", tz="UTC")
    m15_rows = []
    for i, t in enumerate(times):
        o = closes[i]
        c = closes[i + 1]
        mu, sigma = REGIME_PARAMS[true_regimes[i]]
        wick = abs(rng.standard_normal()) * sigma  # fractional wick size
        h = max(o, c) * (1 + wick)
        l = min(o, c) * (1 - wick)
        m15_rows.append(
            {
                "ts": t,
                "open": round(o, 3),
                "high": round(h, 3),
                "low": round(l, 3),
                "close": round(c, 3),
                "tick_volume": int(rng.integers(200, 2000)),
                "spread": int(rng.integers(15, 40)),
                "source": "synthetic_demo",
            }
        )
    df_m15 = pd.DataFrame(m15_rows).set_index("ts")

    # M5 via Brownian bridge within each M15 bar
    m5_rows = []
    for i, t in enumerate(times):
        o = closes[i]
        c = closes[i + 1]
        mu, sigma = REGIME_PARAMS[true_regimes[i]]
        span = (t,)
        subs = 3
        step_t = pd.Timedelta(minutes=5)
        prev = o
        for j in range(subs):
            frac = (j + 1) / subs
            mean = o + (c - o) * frac
            noise = sigma * prev * np.sqrt(1 / subs)
            cc = mean + rng.standard_normal() * noise
            hh = max(prev, cc) * (1 + abs(rng.standard_normal()) * sigma * 0.5)
            ll = min(prev, cc) * (1 - abs(rng.standard_normal()) * sigma * 0.5)
            m5_rows.append(
                {
                    "ts": t + j * step_t,
                    "open": round(prev, 3),
                    "high": round(hh, 3),
                    "low": round(ll, 3),
                    "close": round(cc, 3),
                    "tick_volume": int(rng.integers(50, 700)),
                    "spread": int(rng.integers(15, 40)),
                    "source": "synthetic_demo",
                }
            )
            prev = cc
    df_m5 = pd.DataFrame(m5_rows).set_index("ts")

    # H1 aggregated from M15
    h1_rows = []
    for i in range(0, n_m15, 4):
        chunk = df_m15.iloc[i : i + 4]
        if len(chunk) == 0:
            continue
        h1_rows.append(
            {
                "ts": chunk.index[0],
                "open": chunk["open"].iloc[0],
                "high": chunk["high"].max(),
                "low": chunk["low"].min(),
                "close": chunk["close"].iloc[-1],
                "tick_volume": int(chunk["tick_volume"].sum()),
                "spread": int(chunk["spread"].mean()),
                "source": "synthetic_demo",
            }
        )
    df_h1 = pd.DataFrame(h1_rows).set_index("ts")

    return df_m5, df_m15, df_h1, true_regimes
