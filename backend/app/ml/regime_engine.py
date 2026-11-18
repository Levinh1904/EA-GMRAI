"""Operational Regime Engine.

Aggregates HMM semantic probabilities + RF probabilities into operational
regimes with thresholds, hysteresis, confirmation and reason codes.
Thresholds are NOT hand-picked: optimize_thresholds() tunes them on the
validation slice; the engine only runs with validated params.

EngineState is the stateful core used both by backtests (loop over bars)
and by live prediction (persisted in model_predictions.components_json).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

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
    # Current-state override: when the state detector is confident that a
    # trend is ALREADY in progress, the (structurally lagging) model output
    # must not keep reporting SIDEWAYS. 0 disables the override.
    # 0.45 was measured on 23k real M15 bars: vs 0 (disabled) it raises
    # same-time detection F1 0.649 -> 0.695, cuts missed trend windows
    # 20 -> 8 and shortens detection delay 15.7 -> 13.3 bars.
    state_override_strength: float = 0.45
    # NOTE (measured): an additional |displacement|/H1 entry gate looked good on
    # a fixed set of pre-existing segments but made end-to-end results WORSE
    # (61.7% vs 71.8% correct) because flipping the gate on and off fragmented
    # long trends into short ones. It stays available but defaults to OFF;
    # `min_signal_bars` is the effective filter.
    min_disp_signal: float = 0.0
    require_h1_agreement: bool = False
    # Minimum published trend length (bars). HISTORICAL default 9 preserved for
    # backwards compatibility with already-approved models. Run #9 evidence:
    # delaying publication until bar 9 made entries late and collapsed the
    # end-of-segment direction accuracy to 36-39%. New training selects this
    # value (1 = publish from the first confirmed bar) on a causal validation
    # slice; 1 + min_hold_bars=8 measured 63.1% walk-forward OOS.
    min_signal_bars: int = 9
    # Minimum bars to stay in a trend after entry, even if the probability
    # drops below theta_exit. 0 disables. This is the causal replacement for the
    # old retrospective short-trend collapse.
    min_hold_bars: int = 0
    # Optional entry session filter (UTC hours, 0-23). Empty = all hours.
    # Only entries are filtered; an open trend may run past the window.
    allowed_entry_hours_utc: list[int] = field(default_factory=list)
    # Direction-asymmetric entry filters. The long side is structurally weaker:
    # measured on run #19 with realistic next-open/spread/slippage, filtering
    # longs to H1>=0.20 + |displacement|>=1.2 raised full PnL 88.4k -> 92.8k,
    # OOS 23.1k -> 31.0k and cut max drawdown 51.2k -> 45.8k. Shorts unchanged.
    long_min_h1_context: float = 0.0
    long_min_disp_signal: float = 0.0
    short_min_h1_context: float = 0.0
    short_min_disp_signal: float = 0.0

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
        # Early-trend advisories are directional: report the confidence of the
        # direction they point at (they used to fall through to 0.0, which made
        # every EARLY_TREND_* signal look maximally uncertain).
        "EARLY_TREND_UP": "p_up",
        "EARLY_TREND_DOWN": "p_down",
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
        self.trend_age = 0

    def snapshot(self) -> dict:
        return {
            "state": self.state,
            "up_confirm": self.up_confirm,
            "down_confirm": self.down_confirm,
            "exit_count": self.exit_count,
            "prev_up": self.prev_up,
            "prev_down": self.prev_down,
            "trend_age": self.trend_age,
        }

    def restore(self, snap: dict) -> None:
        self.state = snap.get("state", "UNKNOWN")
        self.up_confirm = int(snap.get("up_confirm", 0))
        self.down_confirm = int(snap.get("down_confirm", 0))
        self.exit_count = int(snap.get("exit_count", 0))
        self.prev_up = snap.get("prev_up")
        self.prev_down = snap.get("prev_down")
        self.trend_age = int(snap.get("trend_age", 0))

    def step(self, row: dict) -> dict:
        up, down = row["p_up"], row["p_down"]
        base = _base_regime(row, self.params)
        reasons: list[str] = []
        regime = base
        advisory = None
        in_trend = self.state in ("TREND_UP", "TREND_DOWN")
        if in_trend:
            self.trend_age += 1
        else:
            self.trend_age = 0
        hold_active = in_trend and self.trend_age <= self.params.min_hold_bars

        def _entry_gate(direction: str) -> tuple[bool, str]:
            if self.params.min_disp_signal <= 0 and not self.params.require_h1_agreement:
                return True, "gate_disabled"
            from app.ml.state_detector import StateDetectorConfig, signal_quality

            qcfg = StateDetectorConfig(
                min_disp_signal=self.params.min_disp_signal,
                require_h1_agreement=self.params.require_h1_agreement,
            )
            return signal_quality(
                row.get("state_displacement"), row.get("h1_trend_context"), direction, qcfg
            )

        gate_up_ok, gate_up_reason = _entry_gate("TREND_UP")
        gate_down_ok, gate_down_reason = _entry_gate("TREND_DOWN")

        def _direction_extra(direction: str) -> tuple[bool, str]:
            h1_min = self.params.long_min_h1_context if direction == "TREND_UP" else self.params.short_min_h1_context
            disp_min = self.params.long_min_disp_signal if direction == "TREND_UP" else self.params.short_min_disp_signal
            if h1_min > 0:
                h1 = row.get("h1_trend_context")
                if h1 is None or not np.isfinite(float(h1)):
                    return False, "no_h1"
                if direction == "TREND_UP" and float(h1) < h1_min:
                    return False, "weak_h1"
                if direction == "TREND_DOWN" and float(h1) > -h1_min:
                    return False, "weak_h1"
            if disp_min > 0:
                disp = row.get("state_displacement")
                if disp is None or not np.isfinite(float(disp)):
                    return False, "no_displacement"
                if abs(float(disp)) < disp_min:
                    return False, "weak_displacement"
            return True, "ok"

        extra_up_ok, extra_up_reason = _direction_extra("TREND_UP")
        extra_down_ok, extra_down_reason = _direction_extra("TREND_DOWN")
        hour = row.get("hour_utc")
        hour_ok = True
        if self.params.allowed_entry_hours_utc and hour is not None:
            hour_ok = int(hour) in self.params.allowed_entry_hours_utc

        if self.state == "TREND_UP":
            if up >= self.params.theta_exit or hold_active:
                regime = "TREND_UP"
                reasons.append("MIN_HOLD" if hold_active and up < self.params.theta_exit else "HYSTERESIS_HOLD")
                self.exit_count = 0
            else:
                self.exit_count += 1
                if self.exit_count >= self.params.confirm_bars:
                    self.state = base
                    regime = base
                    reasons.append("EXIT_BELOW_THRESHOLD")
                    self.exit_count = 0
                    self.trend_age = 0
                else:
                    regime = "TREND_UP"
                    reasons.append("HYSTERESIS_HOLD")
        elif self.state == "TREND_DOWN":
            if down >= self.params.theta_exit or hold_active:
                regime = "TREND_DOWN"
                reasons.append("MIN_HOLD" if hold_active and down < self.params.theta_exit else "HYSTERESIS_HOLD")
                self.exit_count = 0
            else:
                self.exit_count += 1
                if self.exit_count >= self.params.confirm_bars:
                    self.state = base
                    regime = base
                    reasons.append("EXIT_BELOW_THRESHOLD")
                    self.exit_count = 0
                    self.trend_age = 0
                else:
                    regime = "TREND_DOWN"
                    reasons.append("HYSTERESIS_HOLD")
        else:
            if up >= self.params.theta_enter and up > down:
                if not hour_ok:
                    self.up_confirm = 0
                    reasons.append("HOUR_FILTERED")
                    regime = base
                elif not gate_up_ok:
                    self.up_confirm = 0
                    reasons.append(f"ENTRY_FILTERED_{gate_up_reason.upper()}")
                    regime = base
                elif not extra_up_ok:
                    self.up_confirm = 0
                    reasons.append(f"LONG_FILTERED_{extra_up_reason.upper()}")
                    regime = base
                else:
                    self.up_confirm += 1
                    self.down_confirm = 0
                    if self.up_confirm >= self.params.confirm_bars:
                        self.state = "TREND_UP"
                        regime = "TREND_UP"
                        self.trend_age = 1
                        reasons.append(f"CONFIRM_{self.params.confirm_bars}")
                        self.up_confirm = 0
                    else:
                        regime = base
                        reasons.append("PENDING_CONFIRM")
            elif down >= self.params.theta_enter and down > up:
                if not hour_ok:
                    self.down_confirm = 0
                    reasons.append("HOUR_FILTERED")
                    regime = base
                elif not gate_down_ok:
                    self.down_confirm = 0
                    reasons.append(f"ENTRY_FILTERED_{gate_down_reason.upper()}")
                    regime = base
                elif not extra_down_ok:
                    self.down_confirm = 0
                    reasons.append(f"SHORT_FILTERED_{extra_down_reason.upper()}")
                    regime = base
                else:
                    self.down_confirm += 1
                    self.up_confirm = 0
                    if self.down_confirm >= self.params.confirm_bars:
                        self.state = "TREND_DOWN"
                        regime = "TREND_DOWN"
                        self.trend_age = 1
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

        # Early trend advisory (does not change the state machine). Respect the
        # session filter too: an EARLY_TREND outside the selected hours would
        # otherwise appear in direction-accuracy stats even though it is NO_TRADE.
        if regime in BASE_REGIMES and hour_ok:
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

        # ---- Current-state override -------------------------------------
        # The supervised path labels bars by their FUTURE move, so it is
        # structurally late. When the (causal) state detector is confident a
        # trend is already running, report that trend instead of holding
        # SIDEWAYS. The detector never fires on weak evidence, so this cannot
        # invent a trend out of noise.
        state = row.get("state")
        strength = float(row.get("state_strength") or 0.0)
        # Quality gate: publishing every detected trend reversed 40%+ of the
        # time on short segments; only decisive evidence is promoted.
        gate_ok = True
        gate_reason = "ok"
        if self.params.min_disp_signal > 0 or self.params.require_h1_agreement:
            from app.ml.state_detector import StateDetectorConfig, signal_quality

            qcfg = StateDetectorConfig(
                min_disp_signal=self.params.min_disp_signal,
                require_h1_agreement=self.params.require_h1_agreement,
            )
            gate_ok, gate_reason = signal_quality(
                row.get("state_displacement"), row.get("h1_trend_context"), state or "", qcfg
            )
        if (
            self.params.state_override_strength > 0
            and state in ("TREND_UP", "TREND_DOWN")
            and strength >= self.params.state_override_strength
            # Only the "nothing is happening" regimes are overridden: a
            # HIGH_VOLATILITY warning must never be masked by a trend call.
            and regime in ("SIDEWAYS", "TRANSITION")
            and gate_ok
            and hour_ok
            and (extra_up_ok if state == "TREND_UP" else extra_down_ok)
        ):
            regime = state
            confidence = round(max(strength, _class_confidence(state, row)), 4)
            reasons.append("STATE_DETECTOR_OVERRIDE")
            self.state = state
            self.trend_age = 1
            self.up_confirm = self.down_confirm = 0
            self.exit_count = 0
        else:
            if (
                state in ("TREND_UP", "TREND_DOWN")
                and strength >= self.params.state_override_strength
                and not gate_ok
            ):
                reasons.append(f"SIGNAL_FILTERED_{gate_reason.upper()}")
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


def collapse_short_trends_causal(
    regimes: list[str], min_bars: int, base: str = "SIDEWAYS"
) -> tuple[list[str], int]:
    """CAUSAL version: relabel a trend only from the bar it becomes long enough.

    The retrospective version below looks ahead: it needs to know the run's
    total length to decide whether its first bar was a trend. That is look-ahead
    — at the first bar of a 5-bar run nothing yet distinguishes it from the first
    bar of a 40-bar run.

    Here a bar is labelled by the run length *observed so far*, so bar k of a run
    stays SIDEWAYS until the run reaches ``min_bars``, then turns TREND. This is
    what a live system can actually produce.

    Trade-off, stated plainly: the first ``min_bars - 1`` bars of every real
    trend are reported as SIDEWAYS. Measured on 394 live bars that is the
    difference between 272 and 126 trend bars — a much quieter (and honest)
    signal.
    """
    if min_bars <= 1:
        return list(regimes), 0
    out: list[str] = []
    run_dir: str | None = None
    run_len = 0
    collapsed = 0
    for r in regimes:
        d = _trend_of(r)
        if d is None:
            run_dir, run_len = None, 0
            out.append(r)
            continue
        if d == run_dir:
            run_len += 1
        else:
            run_dir, run_len = d, 1
        if run_len < min_bars:
            out.append(base)
            if run_len == 1:
                collapsed += 1
        else:
            out.append(r)
    return out, collapsed


def collapse_short_trends(
    regimes: list[str], min_bars: int, base: str = "SIDEWAYS"
) -> tuple[list[str], int]:
    """Replace trend runs shorter than ``min_bars`` with ``base``.

    Publishing a 1-8 bar "trend" produced a signal that reversed before the
    segment ended in 68-76% of cases (measured on 23k real M15 bars). Those
    runs are noise, not trends: relabelling them suppresses the reversal
    without inventing any new signal.

    NOTE: this is RETROSPECTIVE — it requires the run's full length, so it must
    never be used to produce a live label or to measure live accuracy. Use
    ``collapse_short_trends_causal`` for anything that claims to be tradeable.
    Kept for offline research where look-ahead is explicitly acceptable.

    Returns ``(regimes, n_collapsed_runs)``.
    """
    if min_bars <= 1:
        return list(regimes), 0
    out = list(regimes)
    n = len(out)
    collapsed = 0
    i = 0
    while i < n:
        direction = _trend_of(out[i])
        if direction is None:
            i += 1
            continue
        j = i
        while j + 1 < n and _trend_of(out[j + 1]) == direction:
            j += 1
        if (j - i + 1) < min_bars:
            for k in range(i, j + 1):
                out[k] = base
            collapsed += 1
        i = j + 1
    return out, collapsed


def _trend_of(regime: str) -> str | None:
    if regime in ("TREND_UP", "EARLY_TREND_UP"):
        return "UP"
    if regime in ("TREND_DOWN", "EARLY_TREND_DOWN"):
        return "DOWN"
    return None


def run_engine_over_time(score_rows: list[dict], params: EngineParams) -> pd.DataFrame:
    """Run the stateful engine over per-bar combined scores (backtest use)."""
    engine = EngineState(params)
    regimes, confidences, reasons_all = [], [], []
    for row in score_rows:
        out = engine.step(row)
        regimes.append(out["regime"])
        confidences.append(out["confidence"])
        reasons_all.append(out["reason_codes"])

    # Post-pass: trend runs too short to be real are relabelled as SIDEWAYS.
    if params.min_signal_bars > 1:
        regimes, _collapsed = collapse_short_trends(regimes, params.min_signal_bars)

    return pd.DataFrame({"regime": regimes, "confidence": confidences, "reason_codes": reasons_all})


def run_engine_over_time_causal(score_rows: list[dict], params: EngineParams) -> pd.DataFrame:
    """Replay the engine with the SAME causal post-pass used by live/history.

    `run_engine_over_time` above uses the retrospective collapse and must not be
    used to measure tradeable accuracy. Training / backtest selection call this.
    """
    engine = EngineState(params)
    regimes, confidences, reasons_all = [], [], []
    for row in score_rows:
        out = engine.step(row)
        regimes.append(out["regime"])
        confidences.append(out["confidence"])
        reasons_all.append(out["reason_codes"])
    if params.min_signal_bars > 1:
        regimes, _collapsed = collapse_short_trends_causal(regimes, params.min_signal_bars)
    return pd.DataFrame({"regime": regimes, "confidence": confidences, "reason_codes": reasons_all})


def optimize_thresholds(
    score_rows: list[dict],
    y_true: pd.Series,
    grid: dict | None = None,
    causal: bool = False,
    extra_grid: dict | None = None,
) -> tuple[EngineParams, float, list[dict]]:
    """Grid-search engine params on the validation slice.

    Score = macro-F1 (TREND_UP/TREND_DOWN/SIDEWAYS vs labels) - 0.5 * false trend rate.
    Non-trend operational regimes are scored as SIDEWAYS.

    `causal=True` uses the live/history collapse (default False keeps the
    historical research behaviour pinned by tests). `extra_grid` may add
    `min_signal_bars`, `min_hold_bars` and `state_override_strength` values;
    every combination is evaluated with the same objective.
    """
    grid = grid or {
        "theta_enter": [0.50, 0.55, 0.60, 0.65],
        "gap": [0.05, 0.10, 0.15],
        "confirm_bars": [1, 2, 3],
    }
    extras = extra_grid or {}
    msb_values = extras.get("min_signal_bars", [None])
    hold_values = extras.get("min_hold_bars", [None])
    override_values = extras.get("state_override_strength", [None])
    runner = run_engine_over_time_causal if causal else run_engine_over_time
    results: list[dict] = []
    best_params, best_score = None, -np.inf
    for te in grid["theta_enter"]:
        for gap in grid["gap"]:
            for k in grid["confirm_bars"]:
                for msb in msb_values:
                    for hold in hold_values:
                        for override in override_values:
                            kwargs = dict(
                                theta_enter=te,
                                theta_exit=max(te - gap, 0.30),
                                confirm_bars=k,
                            )
                            if msb is not None:
                                kwargs["min_signal_bars"] = int(msb)
                            if hold is not None:
                                kwargs["min_hold_bars"] = int(hold)
                            if override is not None:
                                kwargs["state_override_strength"] = float(override)
                            params = EngineParams(**kwargs)
                            engine = runner(score_rows, params)
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
