"""Serving + in-sample history for the approved trade_ens model."""
from __future__ import annotations

import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from app.config import settings
from app.ml.features_v2 import ALL_FEATURES, build_features_v2
from app.ml.indicators import atr
from app.ml.profit_trader import (
    BarrierConfig,
    barrier_outcomes,
    probs_to_signal,
    run_policy,
    summarize_trades,
)
from app.ml.trade_model import MODEL_NAME, predict_ensemble
from app.models import MarketCandle, MarketTick, ModelVersion
from app.services.source import active_source
from app.services.training import load_candles
from app.services.trade_training import get_approved_trade_model
from app.timeutil import ensure_utc, timeframe_seconds, utcnow

M15 = timeframe_seconds("M15")
_MODEL_CACHE: dict = {"path": None, "mtime": None, "payload": None}
_SIGNAL_CACHE: dict = {"key": None, "t": 0.0, "payload": None}
_HISTORY_CACHE: dict = {"key": None, "t": 0.0, "payload": None}
_SIGNAL_TTL = 15.0
_HISTORY_TTL = 60.0


class TradeSignalError(RuntimeError):
    def __init__(self, message: str, code: str):
        super().__init__(message)
        self.code = code


def _load_artifact(version: ModelVersion) -> dict:
    path = Path(version.artifact_path or "")
    if not path.exists():
        raise TradeSignalError("Approved trade_ens artifact is missing", "MISSING_ARTIFACT")
    mtime = path.stat().st_mtime
    if _MODEL_CACHE["path"] == str(path) and _MODEL_CACHE["mtime"] == mtime:
        return _MODEL_CACHE["payload"]
    payload = joblib.load(path)
    _MODEL_CACHE.update({"path": str(path), "mtime": mtime, "payload": payload})
    return payload


def _load_market(db: Session):
    source = active_source(db, "XAUUSD", "M15")
    if source != "ftmo_mt5":
        code = "DEMO_DATA_NOT_SUPPORTED" if source == "synthetic_demo" else "NO_DATA"
        raise TradeSignalError(
            "No real ftmo_mt5 source available; demo candles are display-only",
            code,
        )
    df_m5, df_m15, df_h1 = load_candles(
        db, "XAUUSD", m5_limit=200_000, m15_limit=80_000, h1_limit=20_000, source="ftmo_mt5"
    )
    if len(df_m15) < 100:
        raise TradeSignalError("Insufficient M15 candles", "INSUFFICIENT_DATA")
    features = build_features_v2(df_m5, df_m15, df_h1)
    if len(features) == 0:
        raise TradeSignalError("Insufficient features", "INSUFFICIENT_FEATURES")
    return source, df_m15, features


def _latest_tick(db: Session):
    tick = db.query(MarketTick).filter(MarketTick.symbol == "XAUUSD").first()
    if tick is None:
        return None
    age = (utcnow() - ensure_utc(tick.ts)).total_seconds()
    return tick, age


def _policy(artifact: dict) -> tuple[float, dict[str, float], tuple[str, ...]]:
    meta = artifact.get("meta", {}) or {}
    threshold = float(artifact.get("threshold", meta.get("threshold", 0.5)))
    allowed = tuple(meta.get("allowed_sides") or ("LONG", "SHORT"))
    thresholds = {
        side: float((artifact.get("thresholds") or meta.get("thresholds") or {}).get(side, threshold))
        for side in allowed
    }
    return threshold, thresholds, allowed


def _signal_from_probs(
    p_long: float,
    p_short: float,
    thresholds: dict[str, float],
    allowed_sides: tuple[str, ...],
) -> str:
    if (
        "LONG" in allowed_sides
        and p_long >= thresholds.get("LONG", 0.5)
        and p_long >= p_short
    ):
        return "LONG"
    if (
        "SHORT" in allowed_sides
        and p_short >= thresholds.get("SHORT", 0.5)
        and p_short > p_long
    ):
        return "SHORT"
    return "NO_TRADE"


def compute_latest_signal(db: Session) -> dict:
    version = get_approved_trade_model(db)
    if version is None:
        raise TradeSignalError(
            "No approved trade_ens model. Train and approve a model first.",
            "NO_APPROVED_MODEL",
        )
    artifact = _load_artifact(version)
    model = artifact["model"]
    threshold, thresholds, allowed_sides = _policy(artifact)
    meta = artifact.get("meta", {})

    source = active_source(db, "XAUUSD", "M15")
    if source != "ftmo_mt5":
        code = "DEMO_DATA_NOT_SUPPORTED" if source == "synthetic_demo" else "NO_DATA"
        raise TradeSignalError(
            "No real ftmo_mt5 source available; demo candles are display-only",
            code,
        )
    latest_raw = (
        db.query(MarketCandle.ts)
        .filter(
            MarketCandle.symbol == "XAUUSD",
            MarketCandle.timeframe == "M15",
            MarketCandle.source == source,
        )
        .order_by(MarketCandle.ts.desc())
        .first()
    )
    if latest_raw is None:
        raise TradeSignalError("Insufficient M15 candles", "INSUFFICIENT_DATA")
    latest_ts = ensure_utc(latest_raw[0])
    cache_key = (
        version.id,
        latest_ts.isoformat(),
        tuple(sorted(thresholds.items())),
        allowed_sides,
    )
    now_mono = time.monotonic()
    if (
        _SIGNAL_CACHE["key"] == cache_key
        and now_mono - _SIGNAL_CACHE["t"] < _SIGNAL_TTL
        and _SIGNAL_CACHE["payload"] is not None
    ):
        return {**_SIGNAL_CACHE["payload"], "cached": True}

    source, df_m15, features = _load_market(db)
    latest_ts = ensure_utc(features.index[-1])
    tick_info = _latest_tick(db)

    probs = predict_ensemble(model, features.iloc[[-1]][ALL_FEATURES])
    p_long = float(probs.iloc[0]["p_long"])
    p_short = float(probs.iloc[0]["p_short"])
    signal = _signal_from_probs(p_long, p_short, thresholds, allowed_sides)

    row = df_m15.loc[latest_ts]
    close = float(row["close"])
    atr_series = atr(df_m15, 14)
    atr_value = float(atr_series.loc[latest_ts])
    spread_points = row.get("spread")
    spread_points = float(spread_points) if pd.notna(spread_points) else 0.0
    spread_usd = max(spread_points, 0.0) * 0.01
    tick = tick_info[0] if tick_info else None
    tick_age = tick_info[1] if tick_info else None
    entry_price = close
    if tick is not None and tick_age is not None and tick_age <= 120 and signal != "NO_TRADE":
        entry_price = float(tick.ask if signal == "LONG" else tick.bid)
    if signal == "LONG":
        tp_price = entry_price + 0.5 * atr_value
        sl_price = entry_price - 2.0 * atr_value
    elif signal == "SHORT":
        tp_price = entry_price - 0.5 * atr_value
        sl_price = entry_price + 2.0 * atr_value
    else:
        tp_price = sl_price = None
    bar_close = latest_ts + pd.Timedelta(seconds=M15)
    age_seconds = (utcnow() - bar_close).total_seconds()
    stale = age_seconds > 2 * M15
    payload = {
        "symbol": "XAUUSD",
        "timeframe": "M15",
        "signal": signal,
        "tradeable": bool(signal != "NO_TRADE" and not stale),
        "research_only": True,
        "p_long": round(p_long, 6),
        "p_short": round(p_short, 6),
        "threshold": round(threshold, 6),
        "thresholds": {k: round(v, 6) for k, v in thresholds.items()},
        "allowed_sides": list(allowed_sides),
        "price": round(close, 3),
        "entry_price": round(entry_price, 3),
        "tp_price": round(tp_price, 3) if tp_price is not None else None,
        "sl_price": round(sl_price, 3) if sl_price is not None else None,
        "atr": round(atr_value, 6),
        "spread_usd": round(spread_usd, 6),
        "bar_ts": latest_ts.isoformat(),
        "bar_close_ts": bar_close.isoformat(),
        "expires_at": (bar_close + pd.Timedelta(seconds=2 * M15)).isoformat(),
        "data_age_seconds": round(age_seconds, 1),
        "stale": bool(stale),
        "source": source,
        "model_version_id": version.id,
        "model_name": MODEL_NAME,
        "feature_version": meta.get("feature_version", "v2"),
        "barrier": meta.get("barrier"),
        "tick_age_seconds": round(tick_age, 1) if tick_age is not None else None,
        "warnings": [
            "Research signal only — no order is sent by GMRAI.",
            "High win rate does not imply profit: TP=0.5 ATR, SL=2.0 ATR.",
            "p_long/p_short are model probabilities, not a guarantee.",
            f"Allowed sides for this model version: {', '.join(allowed_sides)}.",
        ],
        "cached": False,
    }
    _SIGNAL_CACHE.update({"key": cache_key, "t": now_mono, "payload": payload})
    return payload


def compute_signal_history(db: Session, limit: int = 1000) -> dict:
    version = get_approved_trade_model(db)
    if version is None:
        raise TradeSignalError(
            "No approved trade_ens model. Train and approve a model first.",
            "NO_APPROVED_MODEL",
        )
    artifact = _load_artifact(version)
    model = artifact["model"]
    threshold, thresholds, allowed_sides = _policy(artifact)
    meta = artifact.get("meta", {})
    source, df_m15, features = _load_market(db)
    latest_ts = ensure_utc(features.index[-1])
    cache_key = (
        version.id,
        latest_ts.isoformat(),
        tuple(sorted(thresholds.items())),
        allowed_sides,
        int(limit),
    )
    now_mono = time.monotonic()
    if (
        _HISTORY_CACHE["key"] == cache_key
        and now_mono - _HISTORY_CACHE["t"] < _HISTORY_TTL
        and _HISTORY_CACHE["payload"] is not None
    ):
        return {**_HISTORY_CACHE["payload"], "cached": True}

    outcomes = barrier_outcomes(df_m15).reindex(features.index)
    probs = predict_ensemble(model, features[ALL_FEATURES])
    signals = probs_to_signal(
        probs["p_long"],
        probs["p_short"],
        threshold,
        allowed_sides=allowed_sides,
        long_threshold=thresholds.get("LONG"),
        short_threshold=thresholds.get("SHORT"),
    )
    signals.index = probs.index
    trades = run_policy(signals, outcomes, start=0, end=len(signals))
    metrics = summarize_trades(trades)

    frame = pd.DataFrame(
        {
            "ts": features.index,
            "open": df_m15["open"].reindex(features.index).values,
            "high": df_m15["high"].reindex(features.index).values,
            "low": df_m15["low"].reindex(features.index).values,
            "close": df_m15["close"].reindex(features.index).values,
            "p_long": probs["p_long"].values,
            "p_short": probs["p_short"].values,
            "signal": signals.values,
            "atr": atr(df_m15, 14).reindex(features.index).values,
        }
    )
    frame = frame.tail(max(1, min(int(limit), 5000))).copy()
    frame["ts"] = frame["ts"].map(lambda x: ensure_utc(x).isoformat())

    by_direction = {}
    trade_frame = pd.DataFrame(trades)
    if len(trade_frame):
        for direction, group in trade_frame.groupby("direction"):
            pnls = group["pnl"].to_numpy()
            by_direction[str(direction)] = {
                "n": int(len(group)),
                "win_rate": round(float((pnls > 0).mean()), 6),
                "mean_pnl": round(float(pnls.mean()), 6),
                "total_pnl": round(float(pnls.sum()), 6),
            }

    payload = {
        "model_version_id": version.id,
        "model_name": MODEL_NAME,
        "feature_version": meta.get("feature_version", "v2"),
        "threshold": round(threshold, 6),
        "thresholds": {k: round(v, 6) for k, v in thresholds.items()},
        "allowed_sides": list(allowed_sides),
        "barrier": meta.get("barrier"),
        "in_sample": True,
        "source": source,
        "bars": frame.to_dict(orient="records"),
        "trades": [
            {
                **t,
                "entry_ts": ensure_utc(t["entry_ts"]).isoformat(),
                "exit_ts": ensure_utc(t["exit_ts"]).isoformat(),
            }
            for t in trades
        ],
        "metrics": metrics,
        "equity_curve": metrics.get("equity_curve", []),
        "by_direction": by_direction,
        "warnings": [
            "This is in-sample replay of the approved model, not a live track record.",
            "Win rate is not profit; TP=0.5 ATR and SL=2.0 ATR.",
            "trade_ens is the only model; no reference/regime context is used.",
        ],
        "cached": False,
    }
    _HISTORY_CACHE.update({"key": cache_key, "t": now_mono, "payload": payload})
    return payload
