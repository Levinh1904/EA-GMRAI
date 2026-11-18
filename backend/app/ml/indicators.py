"""Technical indicators — pure pandas/numpy, causal (only past data)."""
import numpy as np
import pandas as pd


def true_range(df: pd.DataFrame) -> pd.Series:
    prev_close = df["close"].shift(1)
    ranges = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    )
    return ranges.max(axis=1)


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    """Wilder ATR (EMA smoothing, alpha=1/n)."""
    return true_range(df).ewm(alpha=1.0 / n, adjust=False).mean()


def ema(series: pd.Series, n: int) -> pd.Series:
    return series.ewm(span=n, adjust=False).mean()


def sma(series: pd.Series, n: int) -> pd.Series:
    return series.rolling(n).mean()


def adx(df: pd.DataFrame, n: int = 14) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Wilder ADX / +DI / -DI (raw 0-100 scale)."""
    up = df["high"].diff()
    down = -df["low"].diff()
    plus_dm = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=df.index)
    minus_dm = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=df.index)
    atr_n = true_range(df).ewm(alpha=1.0 / n, adjust=False).mean()
    plus_di = 100.0 * plus_dm.ewm(alpha=1.0 / n, adjust=False).mean() / atr_n.replace(0, np.nan)
    minus_di = 100.0 * minus_dm.ewm(alpha=1.0 / n, adjust=False).mean() / atr_n.replace(0, np.nan)
    dx = 100.0 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx_series = dx.ewm(alpha=1.0 / n, adjust=False).mean()
    return adx_series, plus_di, minus_di


def efficiency_ratio(close: pd.Series, n: int = 10) -> pd.Series:
    net_move = (close - close.shift(n)).abs()
    path = close.diff().abs().rolling(n).sum()
    return net_move / path.replace(0, np.nan)


def log_return(close: pd.Series, bars: int = 1) -> pd.Series:
    return np.log(close / close.shift(bars))


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    """Wilder RSI (raw 0-100 scale)."""
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = gain.ewm(alpha=1.0 / n, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / n, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    out = 100.0 - 100.0 / (1.0 + rs)
    return out.where(avg_loss != 0, 100.0)
