"""Evaluation metrics — classification, detection quality, trading simulation.

The trading simulation is a RESEARCH tool only; GMRAI never sends orders.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_recall_fscore_support,
)

from app.ml.labels import LABEL_CLASSES


def classification_metrics(y_true: pd.Series, y_pred: pd.Series) -> dict:
    y_true = np.asarray(y_true)
    y_pred = np.asarray(y_pred)
    classes = [c for c in LABEL_CLASSES if (y_true == c).any() or (y_pred == c).any()]
    p, r, f1, _ = precision_recall_fscore_support(
        y_true, y_pred, labels=classes, zero_division=0
    )
    cm = confusion_matrix(y_true, y_pred, labels=LABEL_CLASSES)
    return {
        "accuracy": round(float(accuracy_score(y_true, y_pred)), 4),
        "macro_f1": round(float(f1_score(y_true, y_pred, labels=LABEL_CLASSES, average="macro", zero_division=0)), 4),
        "per_class": {
            c: {"precision": round(float(p[i]), 4), "recall": round(float(r[i]), 4), "f1": round(float(f1[i]), 4)}
            for i, c in enumerate(classes)
        },
        "confusion_matrix": cm.tolist(),
        "classes": LABEL_CLASSES,
    }


def _label_windows(labels: pd.Series, target: str) -> list[tuple[int, int]]:
    """Consecutive runs of `target` in labels -> [(start, end)] index positions."""
    windows = []
    start = None
    for i, v in enumerate(labels.values):
        if v == target and start is None:
            start = i
        elif v != target and start is not None:
            windows.append((start, i))
            start = None
    if start is not None:
        windows.append((start, len(labels)))
    return windows


def detection_metrics(labels: pd.Series, regimes: pd.Series) -> dict:
    """Detection delay and missed trends per trend direction."""
    out = {}
    for target in ("TREND_UP", "TREND_DOWN"):
        windows = _label_windows(labels, target)
        delays, missed = [], 0
        for (s, e) in windows:
            found = None
            for i in range(s, e):
                if regimes.iloc[i] == target:
                    found = i
                    break
            if found is None:
                missed += 1
            else:
                delays.append(found - s)
        out[target.lower()] = {
            "windows": len(windows),
            "missed": missed,
            "mean_delay_bars": round(float(np.mean(delays)), 2) if delays else None,
            "max_delay_bars": int(np.max(delays)) if delays else None,
        }
    return out


def false_trend_rate(labels: pd.Series, regimes: pd.Series) -> float:
    """Fraction of trend-signal bars where the realized label was not that trend."""
    r = np.asarray(regimes)
    lab = np.asarray(labels)
    trend_mask = np.isin(r, ["TREND_UP", "TREND_DOWN"])
    if trend_mask.sum() == 0:
        return 0.0
    wrong = (r[trend_mask] != lab[trend_mask]).sum()
    return round(float(wrong / trend_mask.sum()), 4)


def regime_stability(regimes: pd.Series) -> dict:
    """Mean run length per operational regime."""
    runs: dict[str, list[int]] = {}
    current, count = None, 0
    for v in regimes.values:
        if v == current:
            count += 1
        else:
            if current is not None:
                runs.setdefault(current, []).append(count)
            current, count = v, 1
    if current is not None:
        runs.setdefault(current, []).append(count)
    return {k: round(float(np.mean(v)), 2) for k, v in sorted(runs.items())}


def trading_simulation(
    close: pd.Series,
    atr: pd.Series,
    permission: pd.Series,
    labels: pd.Series | None = None,
    cost_usd: float = 30.0,
    lot: float = 1.0,
    max_hold: int = 24,
) -> dict:
    """Simple regime-based simulation: enter on BUY_ONLY/SELL_ONLY, exit on
    permission change or max hold. Returns trades + equity metrics."""
    usd_per_dollar = 100.0 * lot
    trades = []
    pos = 0  # +1 long, -1 short, 0 flat
    entry_idx, entry_px, entry_risk = None, None, None
    equity = 0.0
    curve = []

    n = len(close)
    for i in range(n):
        perm = permission.iloc[i]
        if pos == 0:
            if perm == "BUY_ONLY":
                pos, entry_idx, entry_px = 1, i, close.iloc[i]
                entry_risk = atr.iloc[i] * usd_per_dollar
            elif perm == "SELL_ONLY":
                pos, entry_idx, entry_px = -1, i, close.iloc[i]
                entry_risk = atr.iloc[i] * usd_per_dollar
        else:
            exit_signal = (pos == 1 and perm != "BUY_ONLY") or (pos == -1 and perm != "SELL_ONLY")
            if exit_signal or i - entry_idx >= max_hold or i == n - 1:
                pnl = (close.iloc[i] - entry_px) * usd_per_dollar * pos - cost_usd
                trades.append(
                    {
                        "entry_idx": int(entry_idx),
                        "exit_idx": int(i),
                        "direction": "LONG" if pos == 1 else "SHORT",
                        "entry": round(float(entry_px), 3),
                        "exit": round(float(close.iloc[i]), 3),
                        "pnl_usd": round(float(pnl), 2),
                        "r_multiple": round(float(pnl / max(entry_risk, 1e-9)), 3),
                        "bars": int(i - entry_idx),
                    }
                )
                equity += pnl
                curve.append(equity)
                pos, entry_idx, entry_px, entry_risk = 0, None, None, None

    metrics = trading_metrics(trades, curve)

    if labels is not None:
        traded = {(t["entry_idx"], t["exit_idx"]) for t in trades}
        missed = 0
        for target in ("TREND_UP", "TREND_DOWN"):
            direction = "LONG" if target == "TREND_UP" else "SHORT"
            for (s, e) in _label_windows(labels, target):
                hit = any(
                    t["direction"] == direction and s <= t["entry_idx"] < e
                    for t in trades
                )
                if not hit:
                    missed += 1
        metrics["missed_trends"] = missed
    return {"trades": trades, "metrics": metrics}


def trading_metrics(trades: list[dict], equity_curve: list[float]) -> dict:
    if not trades:
        return {
            "n_trades": 0,
            "profit_factor": None,
            "max_drawdown_usd": 0.0,
            "expectancy_usd": 0.0,
            "win_rate": None,
            "avg_r": None,
            "total_pnl_usd": 0.0,
        }
    pnls = np.array([t["pnl_usd"] for t in trades])
    gross_win = float(pnls[pnls > 0].sum())
    gross_loss = float(-pnls[pnls < 0].sum())
    peak = -np.inf
    max_dd = 0.0
    for eq in equity_curve:
        peak = max(peak, eq)
        max_dd = min(max_dd, eq - peak)
    rs = np.array([t["r_multiple"] for t in trades])
    return {
        "n_trades": int(len(trades)),
        "profit_factor": round(gross_win / gross_loss, 3) if gross_loss > 0 else None,
        "max_drawdown_usd": round(float(max_dd), 2),
        "expectancy_usd": round(float(pnls.mean()), 2),
        "win_rate": round(float((pnls > 0).mean()), 4),
        "avg_r": round(float(rs.mean()), 3),
        "total_pnl_usd": round(float(pnls.sum()), 2),
    }
