"""Evaluation metrics + trading simulation (research tool only)."""
import numpy as np
import pandas as pd

from app.ml.evaluation import (
    classification_metrics,
    detection_metrics,
    false_trend_rate,
    regime_stability,
    trading_metrics,
    trading_simulation,
)


def test_classification_metrics_perfect():
    y = pd.Series(["TREND_UP"] * 10 + ["TREND_DOWN"] * 10 + ["SIDEWAYS"] * 10)
    pred = y.copy()
    m = classification_metrics(y, pred)
    assert m["accuracy"] == 1.0
    assert m["macro_f1"] == 1.0
    for c in m["per_class"].values():
        assert c["precision"] == 1.0


def test_detection_metrics():
    labels = pd.Series(["SIDEWAYS"] * 5 + ["TREND_UP"] * 10 + ["SIDEWAYS"] * 5 + ["TREND_DOWN"] * 10)
    regimes = pd.Series(["SIDEWAYS"] * 7 + ["TREND_UP"] * 8 + ["SIDEWAYS"] * 7 + ["TREND_DOWN"] * 10)
    d = detection_metrics(labels, regimes)
    assert d["trend_up"]["windows"] == 1
    assert d["trend_up"]["missed"] == 0
    assert d["trend_up"]["mean_delay_bars"] == 2.0
    assert d["trend_down"]["missed"] == 0


def test_false_trend_rate():
    labels = pd.Series(["TREND_UP", "SIDEWAYS", "SIDEWAYS", "SIDEWAYS"])
    regimes = pd.Series(["TREND_UP", "TREND_UP", "TREND_DOWN", "SIDEWAYS"])
    # 3 trend-signal bars, 2 of them false (labels not that trend) -> 2/3
    assert false_trend_rate(labels, regimes) == round(2 / 3, 4)


def test_regime_stability():
    regimes = pd.Series(["TREND_UP"] * 3 + ["SIDEWAYS"] * 2 + ["TREND_UP"] * 1)
    s = regime_stability(regimes)
    assert s["TREND_UP"] == 2.0
    assert s["SIDEWAYS"] == 2.0


def test_trading_simulation_mechanics():
    n = 100
    close = pd.Series(np.linspace(2400, 2420, n))
    atr = pd.Series(np.full(n, 2.0))
    permission = pd.Series(["NO_TRADE"] * 10 + ["BUY_ONLY"] * 30 + ["NO_TRADE"] * 60)
    res = trading_simulation(close, atr, permission, cost_usd=30.0, max_hold=24)
    trades = res["trades"]
    assert len(trades) == 2  # max_hold exit at bar 34, then re-entry, exit at bar 40
    m = res["metrics"]
    assert m["n_trades"] == 2
    assert m["total_pnl_usd"] > 0
    assert m["win_rate"] == 1.0
    assert m["profit_factor"] is None  # no losing trades -> undefined
    assert m["max_drawdown_usd"] == 0.0


def test_trading_simulation_short():
    n = 60
    close = pd.Series(np.linspace(2400, 2380, n))
    atr = pd.Series(np.full(n, 2.0))
    permission = pd.Series(["SELL_ONLY"] * 30 + ["NO_TRADE"] * 30)
    res = trading_simulation(close, atr, permission, cost_usd=30.0, max_hold=50)
    assert res["metrics"]["n_trades"] == 1
    assert res["metrics"]["total_pnl_usd"] > 0


def test_trading_metrics_empty():
    m = trading_metrics([], [])
    assert m["n_trades"] == 0
    assert m["profit_factor"] is None


def test_missed_trends():
    n = 80
    close = pd.Series(np.linspace(2400, 2408, n))
    atr = pd.Series(np.full(n, 1.0))
    labels = pd.Series(["TREND_UP"] * 40 + ["SIDEWAYS"] * 40)
    permission = pd.Series(["NO_TRADE"] * n)  # never trades
    res = trading_simulation(close, atr, permission, labels=labels, cost_usd=30.0)
    assert res["metrics"]["missed_trends"] == 1
