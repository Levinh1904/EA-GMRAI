"""trade_ens — long/short probability ensembles + walk-forward evaluation.

ONE model name only: trade_ens. Each side is the arithmetic mean of
LightGBM, RandomForest and LogisticRegression probabilities. There is no HMM,
regime model, ONNX export or secondary model in this module.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

try:
    import lightgbm as lgb
    LIGHTGBM_IMPORT_ERROR = None
except (ImportError, OSError) as exc:  # macOS: missing libomp must fail loudly at training time
    lgb = None
    LIGHTGBM_IMPORT_ERROR = f"{type(exc).__name__}: {exc}"

from app.ml.features_v2 import ALL_FEATURES, FEATURE_VERSION
from app.ml.profit_trader import (
    BarrierConfig,
    barrier_outcomes,
    choose_threshold,
    probs_to_signal,
    run_policy,
    summarize_trades,
)

N_FOLDS = 4
FOLD_BLOCK = 3500
MIN_TRAIN_BARS = 3000
EMBARGO = 30
HOLDOUT_BARS = 480
MIN_TRADES = 300
TARGET_WIN_RATE = 0.70
MIN_PROFIT_FACTOR = 1.0
MIN_MEAN_PNL = 0.0
QUANTILES = (0.02, 0.05, 0.10, 0.20, 0.30, 0.50)
SEL_MIN_TRADES = 50
SEL_MIN_WIN = 0.70
MIN_FEATURE_ROWS = 8000
MODEL_NAME = "trade_ens"
# Selected on the four walk-forward *selection* slices: LONG-only had negative
# selection PnL in 3/4 folds, SHORT-only was positive in 4/4. The holdout is not
# used to choose this. Both sides remain available by passing allowed_sides.
DEFAULT_ALLOWED_SIDES: tuple[str, ...] = ("SHORT",)


class TradeModelError(ValueError):
    pass


LGBM_PARAMS = {
    "n_estimators": 400,
    "learning_rate": 0.03,
    "num_leaves": 15,
    "max_depth": 5,
    "min_child_samples": 120,
    "subsample": 0.8,
    "subsample_freq": 1,
    "colsample_bytree": 0.7,
    "reg_lambda": 8.0,
    "reg_alpha": 1.0,
    "random_state": 42,
    "n_jobs": -1,
    "verbose": -1,
    "eval_metric": "binary_logloss",
}
RF_PARAMS = {
    "n_estimators": 200,
    "min_samples_leaf": 60,
    "max_depth": 8,
    "max_features": 0.5,
    "n_jobs": -1,
    "random_state": 42,
}
LR_PARAMS = {"C": 0.05, "max_iter": 500}


@dataclass
class TradeEnsemble:
    long_members: dict[str, Any]
    short_members: dict[str, Any]
    feature_columns: list[str]
    meta: dict

    def predict(self, X: pd.DataFrame) -> pd.DataFrame:
        return predict_ensemble(self, X)


def _positive_proba(model, X: np.ndarray) -> np.ndarray:
    proba = model.predict_proba(X)
    classes = list(getattr(model, "classes_", []))
    idx = classes.index(1) if 1 in classes else 0
    return np.asarray(proba[:, idx], dtype=float)


def _fit_side(
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_es: np.ndarray,
    y_es: np.ndarray,
) -> dict:
    if len(np.unique(y_train)) < 2:
        raise TradeModelError("training labels contain only one class")
    if lgb is None:
        raise TradeModelError(
            "LightGBM is unavailable. Install libomp (macOS: brew install libomp) "
            f"and retry. Import error: {LIGHTGBM_IMPORT_ERROR}"
        )

    lgbm = lgb.LGBMClassifier(**LGBM_PARAMS)
    if len(np.unique(y_es)) >= 2:
        lgbm.fit(
            X_train,
            y_train,
            eval_set=[(X_es, y_es)],
            callbacks=[lgb.early_stopping(40, verbose=False)],
        )
    else:
        lgbm.fit(X_train, y_train)

    rf = RandomForestClassifier(**RF_PARAMS).fit(X_train, y_train)

    scaler = StandardScaler().fit(X_train)
    lr = LogisticRegression(**LR_PARAMS).fit(
        np.clip(scaler.transform(X_train), -6.0, 6.0), y_train
    )
    return {"lgbm": lgbm, "rf": rf, "scaler": scaler, "lr": lr}


def fit_ensemble(
    X_train: pd.DataFrame,
    y_long_train: pd.Series,
    y_short_train: pd.Series,
    X_es: pd.DataFrame,
    y_long_es: pd.Series,
    y_short_es: pd.Series,
) -> TradeEnsemble:
    cols = list(X_train.columns)
    Xtr = X_train[cols].to_numpy(dtype=float)
    Xes = X_es[cols].to_numpy(dtype=float)
    long_members = _fit_side(Xtr, y_long_train.to_numpy(), Xes, y_long_es.to_numpy())
    short_members = _fit_side(Xtr, y_short_train.to_numpy(), Xes, y_short_es.to_numpy())
    return TradeEnsemble(
        long_members=long_members,
        short_members=short_members,
        feature_columns=cols,
        meta={},
    )


def _side_predict(members: dict, X: np.ndarray) -> np.ndarray:
    p_lgbm = _positive_proba(members["lgbm"], X)
    p_rf = _positive_proba(members["rf"], X)
    scaled = np.clip(members["scaler"].transform(X), -6.0, 6.0)
    p_lr = _positive_proba(members["lr"], scaled)
    return (p_lgbm + p_rf + p_lr) / 3.0


def predict_ensemble(model: TradeEnsemble, X: pd.DataFrame) -> pd.DataFrame:
    cols = model.feature_columns
    arr = X[cols].to_numpy(dtype=float)
    return pd.DataFrame(
        {
            "p_long": _side_predict(model.long_members, arr),
            "p_short": _side_predict(model.short_members, arr),
        },
        index=X.index,
    )


def build_dataset(features: pd.DataFrame, outcomes: pd.DataFrame) -> pd.DataFrame:
    """Join features and barrier outcomes; keep rows valid for both sides."""
    overlap = [
        "pnl_long", "pnl_short", "y_long", "y_short", "valid",
        "entry_idx", "entry_ts", "long_exit_idx", "short_exit_idx",
        "long_exit_ts", "short_exit_ts", "long_exit_reason", "short_exit_reason",
        "valid_long", "valid_short",
        "entry_price", "spread_usd",
    ]
    ds = features.join(outcomes[overlap], how="inner")
    ds = ds[ds["valid"].astype(bool) & ds["y_long"].notna() & ds["y_short"].notna()]
    return ds.sort_index()


def _probe_split(n_dev: int) -> dict[str, tuple[int, int]]:
    s = n_dev - EMBARGO
    train_end = int(0.65 * s)
    es_start = train_end + EMBARGO
    es_end = int(0.80 * s)
    sel_start = es_end + EMBARGO
    sel_end = s
    return {
        "train": (0, train_end),
        "es": (es_start, es_end),
        "sel": (sel_start, sel_end),
    }


def make_folds(n: int) -> tuple[list[dict], int]:
    """Four non-overlapping test blocks ending at n_dev; holdout is untouched."""
    holdout = min(HOLDOUT_BARS, n // 20)
    n_dev = n - holdout
    if n_dev < MIN_TRAIN_BARS:
        raise TradeModelError(f"not enough rows for walk-forward: n_dev={n_dev}")
    block = min(FOLD_BLOCK, (n_dev - MIN_TRAIN_BARS) // N_FOLDS)
    if block < 400:
        raise TradeModelError(f"fold block too small: {block} < 400")
    first = n_dev - N_FOLDS * block
    folds = []
    for k in range(N_FOLDS):
        lo = first + k * block
        hi = lo + block
        s = lo - EMBARGO
        train_end = int(0.65 * s)
        es_start = train_end + EMBARGO
        es_end = int(0.80 * s)
        sel_start = es_end + EMBARGO
        sel_end = s
        if not (0 < train_end < es_start < es_end < sel_start < sel_end < lo < hi):
            raise TradeModelError("invalid fold split")
        folds.append(
            {
                "fold": k,
                "train": (0, train_end),
                "es": (es_start, es_end),
                "sel": (sel_start, sel_end),
                "test": (lo, hi),
            }
        )
    return folds, n_dev


def _slice(df: pd.DataFrame, bounds: tuple[int, int]) -> pd.DataFrame:
    return df.iloc[bounds[0] : bounds[1]]


def _naive_win_rate(outcomes: pd.DataFrame, lo: int, hi: int) -> tuple[float, int]:
    sub = outcomes.iloc[lo:hi]
    sub = sub[sub["valid"].astype(bool)]
    n = len(sub)
    if n == 0:
        return 0.0, 0
    wins = float(sub["y_long"].sum() + sub["y_short"].sum())
    return wins / (2.0 * n), n


def run_walk_forward(
    ds: pd.DataFrame,
    cfg: BarrierConfig | None = None,
    allowed_sides: tuple[str, ...] = DEFAULT_ALLOWED_SIDES,
) -> dict:
    """Run four chronological folds and pool their out-of-sample trades.

    The side filter and thresholds are chosen only on each fold's selection
    slice. Test slices are never used to pick a side, threshold, or quantile.
    """
    cfg = cfg or BarrierConfig()
    folds, n_dev = make_folds(len(ds))
    X_all = ds[ALL_FEATURES]
    outcomes = ds[
        ["pnl_long", "pnl_short", "y_long", "y_short", "valid",
         "entry_idx", "entry_ts", "long_exit_idx", "short_exit_idx",
         "long_exit_ts", "short_exit_ts", "long_exit_reason", "short_exit_reason",
         "valid_long", "valid_short", "entry_price", "spread_usd"]
    ]

    fold_results: list[dict] = []
    all_trades: list[dict] = []
    naive_weighted = 0.0
    naive_n = 0
    for fold in folds:
        try:
            model = fit_ensemble(
                _slice(X_all, fold["train"]),
                _slice(ds["y_long"], fold["train"]),
                _slice(ds["y_short"], fold["train"]),
                _slice(X_all, fold["es"]),
                _slice(ds["y_long"], fold["es"]),
                _slice(ds["y_short"], fold["es"]),
            )
            probs = predict_ensemble(model, X_all.iloc[: fold["test"][1]])
            chosen = choose_threshold(
                probs["p_long"],
                probs["p_short"],
                outcomes,
                start=fold["sel"][0],
                end=fold["sel"][1],
                quantiles=QUANTILES,
                min_trades=SEL_MIN_TRADES,
                min_win_rate=SEL_MIN_WIN,
                allowed_sides=allowed_sides,
            )
        except Exception as exc:  # a broken fold must not kill the whole report
            fold_results.append(
                {"fold": fold["fold"], "status": "error", "error": f"{type(exc).__name__}: {exc}"}
            )
            continue
        if chosen is None:
            fold_results.append(
                {"fold": fold["fold"], "status": "abstain", "reason": "selection_gate"}
            )
            continue

        signals = probs_to_signal(
            probs["p_long"],
            probs["p_short"],
            chosen["threshold"],
            allowed_sides=allowed_sides,
        )
        signals.index = probs.index
        trades = run_policy(
            signals, outcomes, start=fold["test"][0], end=fold["test"][1]
        )
        metrics = summarize_trades(trades)
        naive, naive_rows = _naive_win_rate(
            outcomes, fold["test"][0], fold["test"][1]
        )
        if metrics["n"]:
            naive_weighted += naive * metrics["n"]
            naive_n += metrics["n"]
        all_trades.extend(trades)
        fold_results.append(
            {
                "fold": fold["fold"],
                "status": "done",
                "q": chosen["q"],
                "threshold": chosen["threshold"],
                "allowed_sides": list(allowed_sides),
                "selection_metrics": chosen["selection_metrics"],
                "test_metrics": metrics,
                "naive_win_rate": round(naive, 6),
            }
        )

    pooled = summarize_trades(all_trades)
    naive_rate = naive_weighted / naive_n if naive_n else 0.0
    breakeven = pooled.get("breakeven_win_rate")
    passed = bool(
        pooled["n"] >= MIN_TRADES
        and pooled.get("mean_pnl", 0) > MIN_MEAN_PNL
        and (pooled.get("profit_factor") or 0) > MIN_PROFIT_FACTOR
        and breakeven is not None
        and pooled.get("win_rate") is not None
        and pooled["win_rate"] > breakeven
        and pooled.get("wilson_low") is not None
        and pooled["wilson_low"] >= breakeven
    )
    return {
        "model_name": MODEL_NAME,
        "feature_version": FEATURE_VERSION,
        "barrier": cfg.to_dict(),
        "allowed_sides": list(allowed_sides),
        "n_rows": int(len(ds)),
        "n_dev": int(n_dev),
        "holdout_rows": int(len(ds) - n_dev),
        "folds": fold_results,
        "oos_metrics": pooled,
        "naive_win_rate": round(float(naive_rate), 6),
        "passed": passed,
        "gate": {
            "min_trades": MIN_TRADES,
            "min_mean_pnl": MIN_MEAN_PNL,
            "min_profit_factor": MIN_PROFIT_FACTOR,
            "target_win_rate": TARGET_WIN_RATE,
            "breakeven_win_rate": breakeven,
            "wilson_low": pooled["wilson_low"],
        },
    }


def train_final_model(
    ds: pd.DataFrame,
    cfg: BarrierConfig | None = None,
    allowed_sides: tuple[str, ...] = DEFAULT_ALLOWED_SIDES,
) -> dict:
    """Fit probe -> choose q -> refit final; evaluate holdout exactly once.

    Returns a dictionary with ``model``, ``threshold``, ``q``, ``meta`` and
    validation/holdout reports. The caller decides whether to persist/approve.
    """
    cfg = cfg or BarrierConfig()
    n = len(ds)
    holdout = min(HOLDOUT_BARS, n // 20)
    n_dev = n - holdout
    if n_dev < MIN_TRAIN_BARS:
        raise TradeModelError(f"not enough rows for final model: n_dev={n_dev}")
    X_all = ds[ALL_FEATURES]

    split = _probe_split(n_dev)
    if not (0 < split["train"][1] < split["es"][0] < split["es"][1] < split["sel"][0] < split["sel"][1] < n_dev):
        raise TradeModelError("invalid probe split")
    probe = fit_ensemble(
        _slice(X_all, split["train"]),
        _slice(ds["y_long"], split["train"]),
        _slice(ds["y_short"], split["train"]),
        _slice(X_all, split["es"]),
        _slice(ds["y_long"], split["es"]),
        _slice(ds["y_short"], split["es"]),
    )
    probe_probs = predict_ensemble(probe, X_all.iloc[:n_dev])
    chosen = choose_threshold(
        probe_probs["p_long"],
        probe_probs["p_short"],
        ds[
            ["pnl_long", "pnl_short", "y_long", "y_short", "valid",
             "entry_idx", "entry_ts", "long_exit_idx", "short_exit_idx",
             "long_exit_ts", "short_exit_ts", "long_exit_reason", "short_exit_reason",
             "valid_long", "valid_short", "entry_price", "spread_usd"]
        ],
        start=split["sel"][0],
        end=split["sel"][1],
        quantiles=QUANTILES,
        min_trades=SEL_MIN_TRADES,
        min_win_rate=SEL_MIN_WIN,
        allowed_sides=allowed_sides,
    )
    if chosen is None:
        return {"passed": False, "reason": "selection_abstained", "probe_split": split}

    cut = n_dev - EMBARGO
    final_train_end = int(0.85 * cut)
    final_es_start = final_train_end + EMBARGO
    final_es_end = cut
    if not (0 < final_train_end < final_es_start < final_es_end <= n_dev):
        raise TradeModelError("invalid final split")
    final_model = fit_ensemble(
        X_all.iloc[:final_train_end],
        ds["y_long"].iloc[:final_train_end],
        ds["y_short"].iloc[:final_train_end],
        X_all.iloc[final_es_start:final_es_end],
        ds["y_long"].iloc[final_es_start:final_es_end],
        ds["y_short"].iloc[final_es_start:final_es_end],
    )
    es_probs = predict_ensemble(final_model, X_all.iloc[final_es_start:final_es_end])
    if len(allowed_sides) == 1 and allowed_sides[0] == "LONG":
        sample = es_probs["p_long"].to_numpy()
    elif len(allowed_sides) == 1 and allowed_sides[0] == "SHORT":
        sample = es_probs["p_short"].to_numpy()
    else:
        sample = np.maximum(
            es_probs["p_long"].to_numpy(), es_probs["p_short"].to_numpy()
        )
    threshold = float(np.quantile(sample, 1.0 - chosen["q"]))
    thresholds = {side: threshold for side in allowed_sides}

    holdout_probs = predict_ensemble(final_model, X_all.iloc[n_dev:])
    holdout_signals = probs_to_signal(
        holdout_probs["p_long"],
        holdout_probs["p_short"],
        threshold,
        allowed_sides=allowed_sides,
        long_threshold=thresholds.get("LONG"),
        short_threshold=thresholds.get("SHORT"),
    )
    holdout_signals.index = holdout_probs.index
    outcomes = ds[
        ["pnl_long", "pnl_short", "y_long", "y_short", "valid",
         "entry_idx", "entry_ts", "long_exit_idx", "short_exit_idx",
         "long_exit_ts", "short_exit_ts", "long_exit_reason", "short_exit_reason",
         "valid_long", "valid_short", "entry_price", "spread_usd"]
    ]
    holdout_trades = run_policy(holdout_signals, outcomes, start=n_dev, end=n)
    holdout_metrics = summarize_trades(holdout_trades)

    meta = {
        "model_name": MODEL_NAME,
        "feature_version": FEATURE_VERSION,
        "barrier": cfg.to_dict(),
        "allowed_sides": list(allowed_sides),
        "threshold": round(threshold, 6),
        "thresholds": {k: round(v, 6) for k, v in thresholds.items()},
        "quantile": chosen["q"],
        "feature_columns": ALL_FEATURES,
        "trained_until": str(ds.index[-1]),
        "n_rows": int(n),
        "n_dev": int(n_dev),
        "holdout_rows": int(holdout),
        "probe_split": split,
        "selection": chosen,
        "holdout_metrics": holdout_metrics,
    }
    return {
        "passed": True,
        "model": final_model,
        "threshold": round(threshold, 6),
        "thresholds": {k: round(v, 6) for k, v in thresholds.items()},
        "allowed_sides": list(allowed_sides),
        "q": chosen["q"],
        "meta": meta,
        "holdout_metrics": holdout_metrics,
    }


__all__ = [
    "BarrierConfig",
    "DEFAULT_ALLOWED_SIDES",
    "FOLD_BLOCK",
    "HOLDOUT_BARS",
    "MIN_FEATURE_ROWS",
    "MIN_MEAN_PNL",
    "MIN_PROFIT_FACTOR",
    "MIN_TRADES",
    "MODEL_NAME",
    "N_FOLDS",
    "TARGET_WIN_RATE",
    "TradeEnsemble",
    "TradeModelError",
    "barrier_outcomes",
    "build_dataset",
    "fit_ensemble",
    "make_folds",
    "predict_ensemble",
    "run_walk_forward",
    "train_final_model",
]
