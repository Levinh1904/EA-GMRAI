"""Operational Regime Engine.

Aggregates HMM semantic probabilities + RF probabilities into operational
regimes with thresholds, hysteresis, confirmation and reason codes.
Thresholds are NOT hand-picked: optimize_thresholds() tunes them on the
validation slice; the engine only runs with validated params.

EngineState is the stateful core used both by backtests (loop over bars)
and by live prediction (persisted in model_predictions.components_json).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd
from sklearn.metrics import f1_score

OPERATIONAL_REGIMES = [
    "SIDEWAYS",
    "TREND_UP",
    "TREND_DOWN",
    "EARLY_TREND_UP",
    "EARLY_TREND_DOWN",
    "TRANSITION",
    "HIGH_VOLATILITY",
    "UNKNOWN",
]

BASE_REGIMES = ["SIDEWAYS", "TRANSITION", "HIGH_VOLATILITY"]
PERMISSIONS = {"TREND_UP": "BUY_ONLY", "TREND_DOWN": "SELL_ONLY"}


@dataclass
class EngineParams:
    weight_hmm: float = 0.5
    theta_enter: float = 0.55
    theta_exit: float = 0.45
    confirm_bars: int = 2
    theta_early: float = 0.35
    delta_early: float = 0.10
    highvol_threshold: float = 0.45
    agreement_threshold: float = 0.80

    def to_dict(self) -> dict:
        return asdict(self)


def combine_scores(hmm_semantic: dict, rf_probs: dict, weight_hmm: float = 0.5) -> dict:
    """Weighted combination of HMM semantic probabilities and RF probabilities."""
    w = weight_hmm

    def get(d, k):
        return float(d.get(k, 0.0) or 0.0)

    up = w * get(hmm_semantic, "TREND_UP") + (1 - w) * get(rf_probs, "TREND_UP")
    down = w * get(hmm_semantic, "TREND_DOWN") + (1 - w) * get(rf_probs, "TREND_DOWN")
    side = w * get(hmm_semantic, "SIDEWAYS") + (1 - w) * get(rf_probs, "SIDEWAYS")
    trans = get(hmm_semantic, "TRANSITION")
    highvol = get(hmm_semantic, "HIGH_VOLATILITY")
    total = up + down + side + trans + highvol
    if total > 0:
        up, down, side, trans, highvol = (x / total for x in (up, down, side, trans, highvol))

    agreement = 1.0 - 0.5 * (
        abs(get(hmm_semantic, "TREND_UP") - get(rf_probs, "TREND_UP"))
        + abs(get(hmm_semantic, "TREND_DOWN") - get(rf_probs, "TREND_DOWN"))
        + abs(get(hmm_semantic, "SIDEWAYS") - get(rf_probs, "SIDEWAYS"))
    )
    return {
        "p_up": up,
        "p_down": down,
        "p_side": side,
        "p_trans": trans,
        "p_highvol": highvol,
        "agreement": agreement,
    }


def _base_regime(row: dict, params: EngineParams) -> str:
    if row["p_highvol"] >= params.highvol_threshold:
        return "HIGH_VOLATILITY"
    if row["p_trans"] > row["p_side"]:
        return "TRANSITION"
    return "SIDEWAYS"


def _class_confidence(regime: str, row: dict) -> float:
    key = {
        "TREND_UP": "p_up",
        "TREND_DOWN": "p_down",
        "SIDEWAYS": "p_side",
        "TRANSITION": "p_trans",
        "HIGH_VOLATILITY": "p_highvol",
    }.get(regime)
    if key is None:
        return 0.0
    conf = float(row[key])
    conf *= 0.95 + 0.05 * min(1.0, float(row.get("agreement", 0.0)))
    return round(min(conf, 1.0), 4)


class EngineState:
    """Stateful hysteresis machine. Persist via snapshot()/restore()."""

    def __init__(self, params: EngineParams):
        self.params = params
        self.state = "UNKNOWN"
        self.up_confirm = 0
        self.down_confirm = 0
        self.exit_count = 0
        self.prev_up = None
        self.prev_down = None

    def snapshot(self) -> dict:
        return {
            "state": self.state,
            "up_confirm": self.up_confirm,
            "down_confirm": self.down_confirm,
            "exit_count": self.exit_count,
            "prev_up": self.prev_up,
            "prev_down": self.prev_down,
        }

    def restore(self, snap: dict) -> None:
        self.state = snap.get("state", "UNKNOWN")
        self.up_confirm = int(snap.get("up_confirm", 0))
        self.down_confirm = int(snap.get("down_confirm", 0))
        self.exit_count = int(snap.get("exit_count", 0))
        self.prev_up = snap.get("prev_up")
        self.prev_down = snap.get("prev_down")

    def step(self, row: dict) -> dict:
        up, down = row["p_up"], row["p_down"]
        base = _base_regime(row, self.params)
        reasons: list[str] = []
        regime = base
        advisory = None

        if self.state == "TREND_UP":
            if up >= self.params.theta_exit:
                regime = "TREND_UP"
                reasons.append("HYSTERESIS_HOLD")
                self.exit_count = 0
            else:
                self.exit_count += 1
                if self.exit_count >= self.params.confirm_bars:
                    self.state = base
                    regime = base
                    reasons.append("EXIT_BELOW_THRESHOLD")
                    self.exit_count = 0
                else:
                    regime = "TREND_UP"
                    reasons.append("HYSTERESIS_HOLD")
        elif self.state == "TREND_DOWN":
            if down >= self.params.theta_exit:
                regime = "TREND_DOWN"
                reasons.append("HYSTERESIS_HOLD")
                self.exit_count = 0
            else:
                self.exit_count += 1
                if self.exit_count >= self.params.confirm_bars:
                    self.state = base
                    regime = base
                    reasons.append("EXIT_BELOW_THRESHOLD")
                    self.exit_count = 0
                else:
                    regime = "TREND_DOWN"
                    reasons.append("HYSTERESIS_HOLD")
        else:
            if up >= self.params.theta_enter and up > down:
                self.up_confirm += 1
                self.down_confirm = 0
                if self.up_confirm >= self.params.confirm_bars:
                    self.state = "TREND_UP"
                    regime = "TREND_UP"
                    reasons.append(f"CONFIRM_{self.params.confirm_bars}")
                    self.up_confirm = 0
                else:
                    regime = base
                    reasons.append("PENDING_CONFIRM")
            elif down >= self.params.theta_enter and down > up:
                self.down_confirm += 1
                self.up_confirm = 0
                if self.down_confirm >= self.params.confirm_bars:
                    self.state = "TREND_DOWN"
                    regime = "TREND_DOWN"
                    reasons.append(f"CONFIRM_{self.params.confirm_bars}")
                    self.down_confirm = 0
                else:
                    regime = base
                    reasons.append("PENDING_CONFIRM")
            else:
                self.up_confirm = self.down_confirm = 0
                regime = base
            if regime in ("TREND_UP", "TREND_DOWN"):
                self.state = regime
            else:
                self.state = base

        # Early trend advisory (does not change the state machine)
        if regime in BASE_REGIMES:
            if (
                self.prev_up is not None
                and up >= self.params.theta_early
                and up - self.prev_up >= self.params.delta_early
            ):
                advisory = "EARLY_TREND_UP"
            elif (
                self.prev_down is not None
                and down >= self.params.theta_early
                and down - self.prev_down >= self.params.delta_early
            ):
                advisory = "EARLY_TREND_DOWN"

        if advisory is not None:
            regime = advisory
            reasons.append("EARLY_DELTA_RISE")

        if row.get("agreement", 0.0) >= self.params.agreement_threshold:
            reasons.append("RF_HMM_AGREE")
        else:
            reasons.append("RF_HMM_DIVERGE")

        confidence = _class_confidence(regime, row)
        if confidence < self.params.theta_early and regime != "UNKNOWN":
            reasons.append("LOW_CONFIDENCE")

        self.prev_up, self.prev_down = up, down
        return {
            "regime": regime,
            "confidence": confidence,
            "reason_codes": reasons,
            "engine_state": self.snapshot(),
        }


def run_engine_over_time(score_rows: list[dict], params: EngineParams) -> pd.DataFrame:
    """Run the stateful engine over per-bar combined scores (backtest use)."""
    engine = EngineState(params)
    regimes, confidences, reasons_all = [], [], []
    for row in score_rows:
        out = engine.step(row)
        regimes.append(out["regime"])
        confidences.append(out["confidence"])
        reasons_all.append(out["reason_codes"])
    return pd.DataFrame({"regime": regimes, "confidence": confidences, "reason_codes": reasons_all})


def optimize_thresholds(
    score_rows: list[dict],
    y_true: pd.Series,
    grid: dict | None = None,
) -> tuple[EngineParams, float, list[dict]]:
    """Grid-search engine params on the validation slice.

    Score = macro-F1 (TREND_UP/TREND_DOWN/SIDEWAYS vs labels) - 0.5 * false trend rate.
    Non-trend operational regimes are scored as SIDEWAYS.
    """
    grid = grid or {
        "theta_enter": [0.50, 0.55, 0.60, 0.65],
        "gap": [0.05, 0.10, 0.15],
        "confirm_bars": [1, 2, 3],
    }
    results: list[dict] = []
    best_params, best_score = None, -np.inf
    for te in grid["theta_enter"]:
        for gap in grid["gap"]:
            for k in grid["confirm_bars"]:
                params = EngineParams(
                    theta_enter=te,
                    theta_exit=max(te - gap, 0.30),
                    confirm_bars=k,
                )
                engine = run_engine_over_time(score_rows, params)
                pred = engine["regime"].replace(
                    {
                        "TRANSITION": "SIDEWAYS",
                        "HIGH_VOLATILITY": "SIDEWAYS",
                        "UNKNOWN": "SIDEWAYS",
                        "EARLY_TREND_UP": "SIDEWAYS",
                        "EARLY_TREND_DOWN": "SIDEWAYS",
                    }
                )
                f1 = f1_score(
                    y_true.values,
                    pred.values,
                    labels=["TREND_UP", "TREND_DOWN", "SIDEWAYS"],
                    average="macro",
                    zero_division=0,
                )
                pred_arr = pred.values
                y_arr = y_true.values
                trend_mask = np.isin(pred_arr, ["TREND_UP", "TREND_DOWN"])
                ftr = (
                    float((pred_arr[trend_mask] != y_arr[trend_mask]).sum() / max(trend_mask.sum(), 1))
                    if trend_mask.sum() > 0
                    else 0.0
                )
                score = f1 - 0.5 * ftr
                results.append(
                    {
                        "params": params.to_dict(),
                        "f1_macro": round(f1, 4),
                        "false_trend_rate": round(ftr, 4),
                        "score": round(score, 4),
                    }
                )
                if score > best_score:
                    best_score, best_params = score, params
    return best_params, best_score, results
