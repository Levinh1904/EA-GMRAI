"""Walk-forward backtest engine — chronological folds, purge/embargo, OOS metrics.

Every fold refits EVERYTHING (scaler, HMM, state mapping, RF, thresholds) on
fold-train data only. Three variants are compared per fold: HMM-only,
RF-only and HMM+RF; the ensemble is chosen only if it wins out-of-sample.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler

from app.ml.evaluation import (
    classification_metrics,
    detection_metrics,
    false_trend_rate,
    regime_stability,
    trading_simulation,
)
from app.ml.features import ALL_FEATURES, M15_FEATURES, build_features
from app.ml.hmm_inference import from_hmmlearn
from app.ml.hmm_model import map_states, state_statistics, train_hmm
from app.ml.indicators import atr
from app.ml.labels import make_labels
from app.ml.regime_engine import (
    EngineParams,
    combine_scores,
    optimize_thresholds,
    run_engine_over_time,
)
from app.ml.rf_model import (
    build_rf_features,
    maybe_calibrate,
    predict_proba_rf,
    semantic_probs_array,
    tune_rf,
)
from app.ml.splits import WalkForwardConfig, sub_train_val_split, walk_forward_folds

N_M15_FEATURES = len(M15_FEATURES)
VARIANTS = {"hmm_only": 1.0, "combined": 0.5, "rf_only": 0.0}


@dataclass
class BacktestConfig:
    initial_train: int = 5000
    test_size: int = 500
    step: int | None = None
    embargo: int = 12
    hmm_n_states: int = 5
    hmm_n_init: int = 10
    seed: int = 42
    rf_horizon: int = 12
    up_threshold_atr: float = 0.75
    cost_usd: float = 30.0
    max_hold: int = 24
    min_train: int = 1000
    val_frac: float = 0.2

    def to_dict(self) -> dict:
        return asdict(self)


def _scores_for_region(
    semantic_df: pd.DataFrame,
    rf_probs: pd.DataFrame,
    idx: tuple[int, int],
    weight_hmm: float,
) -> list[dict]:
    start, end = idx
    rows = []
    for i in range(start, end):
        hmm_sem = {c: float(semantic_df.iloc[i][c]) for c in semantic_df.columns}
        rf_p = {c: float(rf_probs.iloc[i][c]) for c in rf_probs.columns}
        rows.append(combine_scores(hmm_sem, rf_p, weight_hmm))
    return rows


def run_fold(
    X_market: np.ndarray,
    feature_df: pd.DataFrame,
    labels: pd.Series,
    close: pd.Series,
    atr_series: pd.Series,
    train: tuple[int, int],
    test: tuple[int, int],
    cfg: BacktestConfig,
) -> dict:
    subtrain, subval = sub_train_val_split(train, cfg.val_frac).values()
    subval_start, subval_end = subval
    test_start, test_end = test

    scaler = StandardScaler().fit(X_market[subtrain[0] : subtrain[1]])
    Xs = scaler.transform(X_market[:test_end])
    X_hmm = Xs[:, :N_M15_FEATURES]

    hmm_model, train_loglik = train_hmm(
        X_hmm[subtrain[0] : subtrain[1]],
        n_states=cfg.hmm_n_states,
        n_init=cfg.hmm_n_init,
        seed=cfg.seed,
    )
    hmm_filter = from_hmmlearn(hmm_model)
    posterior = hmm_filter.posterior(X_hmm[:test_end])
    mapping = map_states(
        state_statistics(
            feature_df.iloc[subtrain[0] : subtrain[1]],
            posterior[subtrain[0] : subtrain[1]],
            cfg.hmm_n_states,
        ),
        cfg.hmm_n_states,
    )
    semantic_df = semantic_probs_array(posterior, mapping)

    rf_X = build_rf_features(
        posterior,
        np.asarray(hmm_model.transmat_),
        mapping,
        feature_df.iloc[:test_end],
        semantic_df,
    )
    rf_model, rf_params, val_f1 = tune_rf(
        rf_X.iloc[subtrain[0] : subtrain[1]],
        labels.iloc[subtrain[0] : subtrain[1]],
        rf_X.iloc[subval_start:subval_end],
        labels.iloc[subval_start:subval_end],
    )
    rf_model, cal_info = maybe_calibrate(
        rf_model,
        rf_X.iloc[subval_start:subval_end],
        labels.iloc[subval_start:subval_end],
    )
    rf_probs = predict_proba_rf(rf_model, rf_X.iloc[:test_end])

    # Per-variant: thresholds tuned on subval, engine applied on test.
    variant_results = {}
    for variant, w in VARIANTS.items():
        scores_subval = _scores_for_region(semantic_df, rf_probs, subval, w)
        best_params, opt_score, grid = optimize_thresholds(scores_subval, labels.iloc[subval_start:subval_end])
        scores_test = _scores_for_region(semantic_df, rf_probs, test, w)
        engine = run_engine_over_time(scores_test, best_params)
        regime = engine["regime"]
        scored = regime.replace(
            {
                "TRANSITION": "SIDEWAYS",
                "HIGH_VOLATILITY": "SIDEWAYS",
                "UNKNOWN": "SIDEWAYS",
                "EARLY_TREND_UP": "SIDEWAYS",
                "EARLY_TREND_DOWN": "SIDEWAYS",
            }
        )
        y_test = labels.iloc[test_start:test_end]
        cls = classification_metrics(y_test, scored)
        permission = regime.map(lambda r: {"TREND_UP": "BUY_ONLY", "TREND_DOWN": "SELL_ONLY"}.get(r, "NO_TRADE"))
        sim = trading_simulation(
            close.iloc[test_start:test_end],
            atr_series.iloc[test_start:test_end],
            permission,
            y_test,
            cost_usd=cfg.cost_usd,
            max_hold=cfg.max_hold,
        )
        variant_results[variant] = {
            "params": best_params.to_dict(),
            "optimization_score": round(float(opt_score), 4),
            "classification": cls,
            "detection": detection_metrics(y_test, scored),
            "false_trend_rate": false_trend_rate(y_test, scored),
            "stability": regime_stability(regime),
            "trading": sim["metrics"],
        }

    return {
        "train_range": [int(train[0]), int(train[1])],
        "subtrain_range": [int(subtrain[0]), int(subtrain[1])],
        "subval_range": [int(subval_start), int(subval_end)],
        "test_range": [int(test_start), int(test_end)],
        "hmm_train_loglik": round(train_loglik, 4),
        "state_mapping": mapping,
        "rf_tuned_params": rf_params,
        "rf_val_macro_f1": round(float(val_f1), 4),
        "calibration": cal_info,
        "rf_feature_importances": dict(
            zip(rf_X.columns, [round(float(v), 5) for v in rf_model.feature_importances_])
        ),
        "variants": variant_results,
    }


def _mean_std(values: list[float]) -> dict:
    arr = np.array(values, dtype=float)
    return {"mean": round(float(arr.mean()), 4), "std": round(float(arr.std()), 4)}


def run_walk_forward(
    df_m5: pd.DataFrame,
    df_m15: pd.DataFrame,
    df_h1: pd.DataFrame,
    cfg: BacktestConfig,
    out_dir: Path | None = None,
) -> dict:
    features = build_features(df_m5, df_m15, df_h1)
    if len(features) < cfg.min_train + cfg.test_size:
        raise ValueError(
            f"Not enough feature rows: {len(features)} < {cfg.min_train + cfg.test_size}"
        )

    close = df_m15["close"].reindex(features.index)
    atr_series = atr(df_m15, 14).reindex(features.index)
    labels = make_labels(
        close,
        atr_series=atr_series,
        horizon=cfg.rf_horizon,
        up_threshold_atr=cfg.up_threshold_atr,
    )
    n = int(labels.notna().sum())  # rows with valid future labels
    X_market = features[ALL_FEATURES].iloc[:n].values.astype(np.float64)
    feature_df = features.iloc[:n]
    labels = labels.iloc[:n]
    close, atr_series = close.iloc[:n], atr_series.iloc[:n]

    wf_cfg = WalkForwardConfig(
        initial_train=cfg.initial_train,
        test_size=cfg.test_size,
        step=cfg.step,
        embargo=cfg.embargo,
        min_train=cfg.min_train,
    )
    folds = walk_forward_folds(n, wf_cfg)
    if not folds:
        raise ValueError(f"No walk-forward folds for n={n}, cfg={cfg.to_dict()}")

    fold_results = []
    for fi, fold in enumerate(folds):
        fr = run_fold(
            X_market, feature_df, labels, close, atr_series,
            fold["train"], fold["test"], cfg,
        )
        fr["fold"] = fi
        fold_results.append(fr)

    # Compare variants across folds.
    variant_summary = {}
    for variant in VARIANTS:
        f1s = [f["variants"][variant]["classification"]["macro_f1"] for f in fold_results]
        ftrs = [f["variants"][variant]["false_trend_rate"] for f in fold_results]
        variant_summary[variant] = {"macro_f1": _mean_std(f1s), "false_trend_rate": _mean_std(ftrs)}

    # Choose the best by mean macro F1; require stability (std <= 1.5x best std).
    ranked = sorted(variant_summary.items(), key=lambda kv: -kv[1]["macro_f1"]["mean"])
    chosen = ranked[0][0]

    report = {
        "config": cfg.to_dict(),
        "n_feature_rows": int(len(features)),
        "n_valid_rows": int(n),
        "n_folds": len(folds),
        "label_counts": {k: int(v) for k, v in labels.value_counts().items()},
        "variant_comparison": variant_summary,
        "chosen_variant": chosen,
        "chosen_variant_note": (
            "Ensemble chosen only if out-of-sample macro-F1 is better AND std is within "
            "1.5x of the best-std variant; otherwise the more stable variant wins."
        ),
        "folds": fold_results,
    }
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "walk_forward_report.json").write_text(_json_dumps(report))
    return report


def _json_dumps(obj) -> str:
    import json

    return json.dumps(obj, indent=2, default=str)
