"""Full training pipeline: candles -> features -> HMM + RF -> evaluation ->
artifacts -> registry rows. Runs inside the background worker."""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler
from sqlalchemy.orm import Session

from app.config import settings
from app.ml.backtest_engine import N_M15_FEATURES
from app.ml.evaluation import classification_metrics, false_trend_rate
from app.ml.features import ALL_FEATURES, FEATURE_VERSION, build_features, candles_to_df
from app.ml.history import build_segments
from app.ml.hmm_inference import from_hmmlearn
from app.ml.hmm_model import map_states, save_hmm_artifact, state_statistics, train_hmm
from app.ml.indicators import atr
from app.ml.labels import make_labels
from app.ml.onnx_export import export_rf_onnx, parity_check
from app.ml.regime_engine import (
    PERMISSIONS,
    EngineParams,
    combine_scores,
    optimize_thresholds,
    run_engine_over_time_causal,
)
from app.ml.state_detector import compute_state_inputs, detect_state_series
from app.ml.rf_model import (
    build_rf_features,
    maybe_calibrate,
    predict_proba_rf,
    semantic_probs_array,
    train_rf,
    tune_rf,
)
from app.ml.splits import chronological_indices, purged_subtrain_subval, sub_train_val_split
from app.models import (
    HmmModel,
    MarketCandle,
    ModelVersion,
    RandomForestModel,
    TrainingRun,
)
from app.services.source import active_source
from app.timeutil import ensure_utc, utcnow

logger = logging.getLogger("gmrai.training")


@dataclass
class TrainingConfig:
    symbol: str = "XAUUSD"
    hmm_n_states: int = 5
    hmm_n_init: int = 10
    seed: int = 42
    train_frac: float = 0.70
    val_frac: float = 0.15
    rf_horizon: int = 12
    up_threshold_atr: float = 0.75
    weight_hmm: float = 0.5

    def to_dict(self) -> dict:
        return asdict(self)


def load_candles(
    db: Session,
    symbol: str = "XAUUSD",
    m5_limit: int = 120_000,
    m15_limit: int = 30_000,
    h1_limit: int = 12_000,
    source: str | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Load the three timeframes from ONE data source.

    `source=None` resolves the active feed (real `ftmo_mt5`, else labeled demo),
    so feature building/training can never interleave two brokers' prices.
    """
    eff_source = active_source(db, symbol, "M15", source)

    def fetch(tf: str, limit: int) -> pd.DataFrame:
        q = (
            db.query(MarketCandle)
            .filter(MarketCandle.symbol == symbol, MarketCandle.timeframe == tf)
        )
        if eff_source:
            q = q.filter(MarketCandle.source == eff_source)
        rows = q.order_by(MarketCandle.ts.desc()).limit(limit).all()
        candles = [
            {
                "ts": ensure_utc(r.ts),
                "open": r.open,
                "high": r.high,
                "low": r.low,
                "close": r.close,
                "tick_volume": r.tick_volume,
                "spread": r.spread,
            }
            for r in reversed(rows)
        ]
        return candles_to_df(candles)

    return fetch("M5", m5_limit), fetch("M15", m15_limit), fetch("H1", h1_limit)


def _segment_direction_accuracy(
    regimes: pd.Series,
    index: pd.Index,
    df_m15: pd.DataFrame,
    features: pd.DataFrame,
) -> dict:
    """Segment direction accuracy, exactly the UI's definition.

    A trend segment is correct when end_price is above start_price for UP and
    below for DOWN; EARLY_TREND_* counts as its direction, as in
    `history_stats.direction_accuracy`. This is a path metric: it can be
    positive while the 12-bar classification F1 is still weak.
    """
    if len(regimes) == 0:
        return {"up": 0.0, "down": 0.0, "overall": 0.0, "segments": 0,
                "up_segments": 0, "down_segments": 0}
    bars = df_m15[["open", "high", "low", "close"]].reindex(index).copy()
    bars["atr_ratio"] = features["atr_ratio"].reindex(index)
    bars["adx_norm"] = features["adx_norm"].reindex(index)
    bars["efficiency_ratio"] = features["efficiency_ratio"].reindex(index)
    bars["h1_trend_context"] = features["h1_trend_context"].reindex(index)
    bars["confidence"] = 0.5
    bars["regime"] = regimes.values
    bars["permission"] = [PERMISSIONS.get(r, "NO_TRADE") for r in regimes.values]
    bars = bars.dropna(subset=["open", "high", "low", "close"])
    segs = build_segments(bars, 900, gap_split_multiple=1.5, touch_tolerance=0.1)
    out = {"up": 0.0, "down": 0.0, "overall": 0.0, "segments": 0,
           "up_segments": 0, "down_segments": 0}
    if not segs:
        return out
    sdf = pd.DataFrame(segs)
    sdf = sdf[sdf["regime"].isin(
        ("TREND_UP", "TREND_DOWN", "EARLY_TREND_UP", "EARLY_TREND_DOWN")
    )]
    if sdf.empty:
        return out
    sdf["dir"] = np.where(sdf["regime"].isin(("TREND_UP", "EARLY_TREND_UP")), "UP", "DOWN")
    sdf["signed"] = np.where(
        sdf["dir"] == "UP",
        sdf["end_price"] - sdf["start_price"],
        sdf["start_price"] - sdf["end_price"],
    )
    sdf["correct"] = sdf["signed"] > 0
    up = sdf[sdf["dir"] == "UP"]
    down = sdf[sdf["dir"] == "DOWN"]
    out.update(
        {
            "up": round(float(up["correct"].mean()) * 100, 2) if len(up) else 0.0,
            "down": round(float(down["correct"].mean()) * 100, 2) if len(down) else 0.0,
            "overall": round(float(sdf["correct"].mean()) * 100, 2),
            "segments": int(len(sdf)),
            "up_segments": int(len(up)),
            "down_segments": int(len(down)),
        }
    )
    return out


def run_training(db: Session, cfg: TrainingConfig, run_id: int | None = None) -> dict:
    """Train HMM + RF, evaluate all variants on the chronological test set,
    persist artifacts and registry rows. Returns a summary dict."""
    if run_id is not None:
        run = db.get(TrainingRun, run_id)
        run.status = "running"
        run.started_at = utcnow()
        db.commit()

    df_m5, df_m15, df_h1 = load_candles(db, cfg.symbol)
    active_source_used = active_source(db, cfg.symbol, "M15")
    features = build_features(df_m5, df_m15, df_h1)
    if len(features) < 1500:
        raise ValueError(f"Not enough data: {len(features)} feature rows (need >= 1500)")

    close = df_m15["close"].reindex(features.index)
    atr_series = atr(df_m15, 14).reindex(features.index)
    labels = make_labels(close, atr_series=atr_series, horizon=cfg.rf_horizon, up_threshold_atr=cfg.up_threshold_atr)
    n = int(labels.notna().sum())
    features = features.iloc[:n]
    labels = labels.iloc[:n]
    # Causal state-detector inputs: must be supplied to the engine during
    # tuning/evaluation exactly as live/history do, otherwise thresholds and the
    # chosen variant describe a different engine than the one that ships.
    state_df = detect_state_series(df_m15).reindex(features.index)
    state_inputs = compute_state_inputs(df_m15).reindex(features.index)

    split = chronological_indices(n, cfg.train_frac, cfg.val_frac)
    train, val, test = split["train"], split["val"], split["test"]
    # Fit on train+val (the val slice used to be discarded, wasting ~15% of
    # data) and keep `test` strictly out-of-sample.
    fit_end = val[1]
    raw_sub = sub_train_val_split((train[0], fit_end), 0.2)
    purged = purged_subtrain_subval(raw_sub["subtrain"], raw_sub["subval"], cfg.rf_horizon)
    subtrain, subval = purged["subtrain"], purged["subval"]
    test = (fit_end, n)
    test_start, test_end = test

    scaler = StandardScaler().fit(features[ALL_FEATURES].iloc[subtrain[0] : subtrain[1]].values)
    Xs = scaler.transform(features[ALL_FEATURES].values.astype(np.float64))
    X_hmm = Xs[:, :N_M15_FEATURES]

    hmm_model, train_loglik = train_hmm(
        X_hmm[subtrain[0] : subtrain[1]],
        n_states=cfg.hmm_n_states,
        n_init=cfg.hmm_n_init,
        seed=cfg.seed,
    )
    val_loglik = float(hmm_model.score(X_hmm[subval[0] : subval[1]]))
    hmm_filter = from_hmmlearn(hmm_model)
    posterior = hmm_filter.posterior(X_hmm)
    mapping = map_states(
        state_statistics(
            features.iloc[subtrain[0] : subtrain[1]],
            posterior[subtrain[0] : subtrain[1]],
            cfg.hmm_n_states,
        ),
        cfg.hmm_n_states,
    )
    semantic_df = semantic_probs_array(posterior, mapping)

    rf_X = build_rf_features(posterior, np.asarray(hmm_model.transmat_), mapping, features, semantic_df)
    rf_model, rf_params, val_f1 = tune_rf(
        rf_X.iloc[subtrain[0] : subtrain[1]],
        labels.iloc[subtrain[0] : subtrain[1]],
        rf_X.iloc[subval[0] : subval[1]],
        labels.iloc[subval[0] : subval[1]],
    )
    rf_model, cal_info = maybe_calibrate(
        rf_model, rf_X.iloc[subval[0] : subval[1]], labels.iloc[subval[0] : subval[1]]
    )
    rf_probs = predict_proba_rf(rf_model, rf_X)

    def scores_for(idx: tuple[int, int], w: float) -> list[dict]:
        rows = []
        for i in range(idx[0], idx[1]):
            hmm_sem = {c: float(semantic_df.iloc[i][c]) for c in semantic_df.columns}
            rf_p = {c: float(rf_probs.iloc[i][c]) for c in rf_probs.columns}
            row = combine_scores(hmm_sem, rf_p, w)
            ts = features.index[i]
            if ts in state_df.index and pd.notna(state_df.loc[ts, "state"]):
                row["state"] = str(state_df.loc[ts, "state"])
                row["state_strength"] = float(state_df.loc[ts, "strength"])
            if ts in state_inputs.index:
                row["state_displacement"] = float(state_inputs.loc[ts, "displacement"])
            row["h1_trend_context"] = float(features["h1_trend_context"].iloc[i])
            row["hour_utc"] = int(ts.hour)
            rows.append(row)
        return rows

    def segment_metric_for(params: EngineParams, rows: list[dict], idx: tuple[int, int]) -> dict:
        eng = run_engine_over_time_causal(rows, params)
        return _segment_direction_accuracy(
            eng["regime"], features.index[idx[0] : idx[1]], df_m15, features
        )

    variant_results = {}
    engine_params: dict = {}
    extra_grid = {
        "min_signal_bars": [1, 3, 5, 9],
        "min_hold_bars": [0, 8, 16],
        "state_override_strength": [0.0, 0.45],
    }
    for variant, w in {"hmm_only": 1.0, "combined": cfg.weight_hmm, "rf_only": 0.0}.items():
        s_val = scores_for(subval, w)
        best_params, opt_score, grid_results = optimize_thresholds(
            s_val,
            labels.iloc[subval[0] : subval[1]],
            causal=True,
            extra_grid=extra_grid,
        )
        # The F1/FTR objective is not the user-facing metric. Re-rank the top
        # F1 candidates on causal *segment* direction accuracy (the same formula
        # as /history/stats/direction_accuracy) and keep that config.
        ranked_params = sorted(grid_results, key=lambda r: -r["score"])
        candidates: list[EngineParams] = [best_params]
        for r in ranked_params[:8]:
            candidates.append(EngineParams(**r["params"]))
        candidates.append(
            EngineParams(
                theta_enter=0.50,
                theta_exit=0.35,
                confirm_bars=1,
                min_signal_bars=1,
                min_hold_bars=8,
                state_override_strength=0.45,
            )
        )
        seen: set[tuple] = set()
        best_choice, best_key = None, None
        best_choice_seg = None
        for cand in candidates:
            key = json.dumps(cand.to_dict(), sort_keys=True)
            if key in seen:
                continue
            seen.add(key)
            seg = segment_metric_for(cand, s_val, subval)
            if seg["segments"] < 20:
                continue
            cand_key = (min(seg["up"], seg["down"]), seg["overall"], seg["segments"])
            if best_key is None or cand_key > best_key:
                best_key, best_choice, best_choice_seg = cand_key, cand, seg
        if best_choice is None:
            best_choice, best_choice_seg = best_params, segment_metric_for(best_params, s_val, subval)
        best_params = best_choice
        s_test = scores_for(test, w)
        eng = run_engine_over_time_causal(s_test, best_params)
        seg_test = segment_metric_for(best_params, s_test, test)
        scored = eng["regime"].replace(
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
        variant_results[variant] = {
            "engine_params": best_params.to_dict(),
            "validation_opt_score": round(float(opt_score), 4),
            "validation_segment_accuracy": best_choice_seg,
            "test_macro_f1": cls["macro_f1"],
            "test_accuracy": cls["accuracy"],
            "false_trend_rate": false_trend_rate(y_test, scored),
            "segment_direction_accuracy": seg_test,
            "classification": cls,
        }

    # Select on the causal path metric, not only the 12-bar classification F1.
    def _rank_key(item):
        v = item[1]["validation_segment_accuracy"]
        # Balanced: protect the weaker direction but still reward overall
        # accuracy. A pure min() would pick a variant with one strong side and
        # a mediocre total; a pure overall() hides a weak direction.
        balanced = 0.7 * min(v["up"], v["down"]) + 0.3 * v["overall"]
        return (balanced, v["segments"], item[1]["test_macro_f1"])

    ranked = sorted(variant_results.items(), key=_rank_key, reverse=True)
    chosen = ranked[0][0]
    engine_params = variant_results[chosen]["engine_params"]
    engine_params["weight_hmm"] = {"hmm_only": 1.0, "combined": cfg.weight_hmm, "rf_only": 0.0}[chosen]

    # ---- artifacts ----
    artifacts = Path(settings.artifact_dir)
    run_ts = utcnow().strftime("%Y%m%dT%H%M%S")
    hmm_dir = artifacts / "hmm" / run_ts
    rf_dir = artifacts / "rf" / run_ts
    hmm_artifact_path = hmm_dir / "model.json"
    rf_artifact_path = rf_dir / "model.joblib"
    rf_onnx_path = rf_dir / "model.onnx"

    save_hmm_artifact(
        hmm_artifact_path,
        {
            "startprob": np.asarray(hmm_model.startprob_).tolist(),
            "transmat": np.asarray(hmm_model.transmat_).tolist(),
            "means": np.asarray(hmm_model.means_).tolist(),
            "covars_diag": np.diagonal(np.asarray(hmm_model.covars_), axis1=1, axis2=2).tolist(),
        },
        scaler.mean_[:N_M15_FEATURES].tolist(),
        scaler.scale_[:N_M15_FEATURES].tolist(),
        ALL_FEATURES[:N_M15_FEATURES],
        mapping,
        {
            "n_states": cfg.hmm_n_states,
            "seed": cfg.seed,
            "train_loglik": round(train_loglik, 4),
            "val_loglik": round(val_loglik, 4),
            "feature_version": FEATURE_VERSION,
            "purge_bars": cfg.rf_horizon,
            "dataset_range": {
                "subtrain": list(subtrain),
                "subval": list(subval),
                "test": [test_start, test_end],
            },
        },
    )
    rf_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(rf_model, rf_artifact_path)
    export_rf_onnx(rf_model, rf_X.columns.tolist(), rf_onnx_path)
    parity = parity_check(rf_model, rf_X.iloc[:100].values, rf_onnx_path)

    # ---- registry rows ----
    dataset_range = {
        "subtrain": [int(subtrain[0]), int(subtrain[1])],
        "subval": [int(subval[0]), int(subval[1])],
        "test": [int(test_start), int(test_end)],
        "purge_bars": cfg.rf_horizon,
    }
    hmm_row = HmmModel(
        name=f"HMM-5s-{run_ts}",
        n_states=cfg.hmm_n_states,
        covariance_type="diag",
        feature_version=FEATURE_VERSION,
        hyperparams_json={"n_init": cfg.hmm_n_init, "seed": cfg.seed},
        dataset_range_json=dataset_range,
        state_mapping_json=mapping,
        transition_matrix_json=np.asarray(hmm_model.transmat_).tolist(),
        train_log_likelihood=round(train_loglik, 4),
        validation_log_likelihood=round(val_loglik, 4),
        status="candidate",
        artifact_path=str(hmm_artifact_path),
    )
    db.add(hmm_row)
    db.flush()
    hmm_version = ModelVersion(
        model_type="hmm",
        model_id=hmm_row.id,
        version=1,
        status="candidate",
        metrics_json={
            "train_loglik": round(train_loglik, 4),
            "val_loglik": round(val_loglik, 4),
            "engine_params": engine_params,
            "chosen_variant": chosen,
            "variant_results": {k: {kk: vv for kk, vv in v.items() if kk != "classification"} for k, v in variant_results.items()},
        },
        artifact_path=str(hmm_artifact_path),
    )
    db.add(hmm_version)
    db.flush()

    rf_row = RandomForestModel(
        name=f"RF-{run_ts}",
        feature_version=FEATURE_VERSION,
        label_spec_json={"horizon": cfg.rf_horizon, "up_threshold_atr": cfg.up_threshold_atr},
        hyperparams_json=rf_params,
        dataset_range_json=dataset_range,
        metrics_json={
            "val_macro_f1": round(float(val_f1), 4),
            "test_macro_f1": variant_results[chosen]["test_macro_f1"],
            "segment_direction_accuracy": variant_results[chosen]["segment_direction_accuracy"],
            "calibration": cal_info,
            "onnx_parity": parity,
        },
        feature_importances_json=dict(
            zip(rf_X.columns, [round(float(v), 6) for v in rf_model.feature_importances_])
        ),
        status="candidate",
        artifact_path=str(rf_artifact_path),
        onnx_path=str(rf_onnx_path),
    )
    db.add(rf_row)
    db.flush()
    rf_version = ModelVersion(
        model_type="random_forest",
        model_id=rf_row.id,
        version=1,
        status="candidate",
        metrics_json={
            "test_macro_f1": variant_results[chosen]["test_macro_f1"],
            "false_trend_rate": variant_results[chosen]["false_trend_rate"],
            "segment_direction_accuracy": variant_results[chosen]["segment_direction_accuracy"],
            "chosen_variant": chosen,
        },
        artifact_path=str(rf_artifact_path),
    )
    db.add(rf_version)
    db.commit()

    # ---- auto-approval gate (chỉ khi đạt mọi điều kiện kiểm định) ----
    f1_ok = variant_results[chosen]["test_macro_f1"] >= settings.approve_min_f1
    ftr_ok = variant_results[chosen]["false_trend_rate"] <= settings.approve_max_false_trend_rate
    seg = variant_results[chosen]["segment_direction_accuracy"]
    seg_ok = (
        min(seg["up"], seg["down"]) >= settings.approve_min_segment_accuracy * 100
        and seg["segments"] >= settings.approve_min_trend_segments
    )
    auto_approved = f1_ok and ftr_ok and seg_ok
    if auto_approved:
        for v in (hmm_version, rf_version):
            v.status = "approved"
        hmm_row.status = "approved"
        rf_row.status = "approved"
        db.commit()

    summary = {
        "hmm_model_id": hmm_row.id,
        "rf_model_id": rf_row.id,
        "hmm_version_id": hmm_version.id,
        "rf_version_id": rf_version.id,
        "feature_rows": int(len(features)),
        "train_loglik": round(train_loglik, 4),
        "val_loglik": round(val_loglik, 4),
        "state_mapping": mapping,
        "rf_val_macro_f1": round(float(val_f1), 4),
        "variant_results": variant_results,
        "chosen_variant": chosen,
        "engine_params": engine_params,
        "data_source": active_source_used,
        "purge_bars": cfg.rf_horizon,
        "dataset_range": dataset_range,
        "calibration": cal_info,
        "onnx_parity": parity,
        "auto_approved": auto_approved,
        "approval_reasons": {
            "f1_ok": f1_ok,
            "ftr_ok": ftr_ok,
            "segment_ok": seg_ok,
            "min_f1": settings.approve_min_f1,
            "max_ftr": settings.approve_max_false_trend_rate,
            "min_segment_accuracy": settings.approve_min_segment_accuracy,
            "segment_direction_accuracy": seg,
        },
    }
    if run_id is not None:
        run = db.get(TrainingRun, run_id)
        run.status = "done"
        run.finished_at = utcnow()
        run.metrics_json = summary
        db.commit()
    return summary
