"""Historical Market Regime Analyzer — API endpoints."""
from __future__ import annotations

import io

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user, require_admin
from app.ml.history import HistoryConfig
from app.ml.history_stats import (
    compare_runs,
    compare_vs_reference,
    duration_statistics,
    early_trend_analysis,
    multi_tf_context,
    period_aggregation,
    sideways_analysis,
    transition_count,
    transition_matrix,
    trend_analysis,
)
from app.models import RegimeHistoryRun, User
from app.services import history as history_service
from app.services.history import (
    HistoryJobError,
    load_run_bars,
    load_run_segments,
    reference_labels,
    run_history_job,
)
from app.services import stats_cache
from app.services.worker import worker
from app.timeutil import ensure_utc

history_router = APIRouter(prefix="/history", tags=["history"])

HISTORY_REGIMES = [
    "TREND_UP", "TREND_DOWN", "SIDEWAYS", "EARLY_TREND_UP", "EARLY_TREND_DOWN",
    "TRANSITION", "HIGH_VOLATILITY", "UNKNOWN",
]


def _get_run_or_404(db: Session, run_id: int) -> RegimeHistoryRun:
    run = db.get(RegimeHistoryRun, run_id)
    if run is None:
        raise HTTPException(404, "History run not found")
    return run


def _cached_stats(run: RegimeHistoryRun, kind: str, compute, params: dict | None = None):
    """Serve an expensive stats result from the per-process cache.

    Only *completed* runs are cached: `regime_history_bars` / `_segments` are
    written once for a done run, so a cached answer cannot go stale. A running
    run is recomputed every time (it is still being written).
    """
    if run.status != "done":
        return compute()
    key = (run.id, kind, tuple(sorted((params or {}).items())))
    return stats_cache.get_or_compute(key, compute)


def _parse_hours(raw: str | None) -> list[int] | None:
    """Parse `hours=6,8,14,17` (UTC). None=model default; ''=all hours."""
    if raw is None:
        return None
    raw = raw.strip().lower()
    if raw in ("", "all", "*"):
        return []
    try:
        values = sorted({int(part.strip()) for part in raw.split(",") if part.strip()})
    except ValueError:
        raise HTTPException(400, "hours must be comma-separated integers 0-23")
    if not values or any(v < 0 or v > 23 for v in values):
        raise HTTPException(400, "hours must be comma-separated integers 0-23")
    return values


@history_router.post("/run")
def start_run(
    regenerate: bool = Query(False),
    symbol: str = Query("XAUUSD"),
    hours: str | None = Query(
        None,
        description="UTC entry hours, e.g. 6,8,14,17. Empty/all = no filter; omit = model default.",
    ),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    cfg = HistoryConfig(symbol=symbol, allowed_entry_hours_utc=_parse_hours(hours))
    run = RegimeHistoryRun(
        symbol=symbol,
        timeframe="M15",
        status="pending",
        config_json=cfg.to_dict(),
    )
    db.add(run)
    db.commit()
    worker.submit("regime_history", {"run_id": run.id}, lambda s: run_history_job(s, run.id, cfg))
    return {"status": "scheduled", "run_id": run.id}


@history_router.get("/runs")
def list_runs(
    limit: int = Query(20, ge=1, le=100),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = db.query(RegimeHistoryRun).order_by(RegimeHistoryRun.id.desc()).limit(limit).all()
    return {
        "runs": [
            {
                "id": r.id,
                "symbol": r.symbol,
                "timeframe": r.timeframe,
                "status": r.status,
                "data_source": r.data_source,
                "bar_count": r.bar_count,
                "segment_count": r.segment_count,
                "data_start": ensure_utc(r.data_start).isoformat() if r.data_start else None,
                "data_end": ensure_utc(r.data_end).isoformat() if r.data_end else None,
                "hmm_model_version_id": r.hmm_model_version_id,
                "rf_model_version_id": r.rf_model_version_id,
                "allowed_entry_hours_utc": (r.config_json or {}).get("allowed_entry_hours_utc"),
                "error": r.error,
                "created_at": ensure_utc(r.created_at).isoformat(),
                "finished_at": ensure_utc(r.finished_at).isoformat() if r.finished_at else None,
            }
            for r in rows
        ]
    }


@history_router.get("/runs/{run_id}")
def get_run(
    run_id: int,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    run = _get_run_or_404(db, run_id)
    return {
        "id": run.id,
        "symbol": run.symbol,
        "timeframe": run.timeframe,
        "status": run.status,
        "data_source": run.data_source,
        "config": run.config_json,
        "bar_count": run.bar_count,
        "segment_count": run.segment_count,
        "data_start": ensure_utc(run.data_start).isoformat() if run.data_start else None,
        "data_end": ensure_utc(run.data_end).isoformat() if run.data_end else None,
        "hmm_model_version_id": run.hmm_model_version_id,
        "rf_model_version_id": run.rf_model_version_id,
        "feature_version": run.feature_version,
        "error": run.error,
        "created_at": ensure_utc(run.created_at).isoformat(),
        "started_at": ensure_utc(run.started_at).isoformat() if run.started_at else None,
        "finished_at": ensure_utc(run.finished_at).isoformat() if run.finished_at else None,
    }


@history_router.get("/runs/{run_id}/bars")
def get_bars(
    run_id: int,
    limit: int = Query(1000, ge=1, le=20000),
    offset: int = Query(0, ge=0),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_run_or_404(db, run_id)
    from sqlalchemy import func

    from app.models import RegimeHistoryBar

    total = (
        db.query(func.count(RegimeHistoryBar.id))
        .filter(RegimeHistoryBar.run_id == run_id)
        .scalar()
    ) or 0
    rows = (
        db.query(RegimeHistoryBar)
        .filter(RegimeHistoryBar.run_id == run_id)
        .order_by(RegimeHistoryBar.ts)
        .offset(offset)
        .limit(limit)
        .all()
    )
    return {
        "run_id": run_id,
        "total": total,
        "limit": limit,
        "offset": offset,
        "bars": [
            {
                "ts": ensure_utc(r.ts).isoformat(),
                "regime": r.regime,
                "confidence": r.confidence,
                "permission": r.permission,
                "hmm_state": r.hmm_state,
                "hmm_posterior": r.hmm_probs_json,
                "rf_probs": r.rf_probs_json,
                "reason_codes": r.reason_codes_json,
                "open": r.open,
                "high": r.high,
                "low": r.low,
                "close": r.close,
                "atr_ratio": r.atr_ratio,
                "adx_norm": r.adx_norm,
                "efficiency_ratio": r.efficiency_ratio,
                "h1_trend_context": r.h1_trend_context,
                "m5_momentum": r.m5_momentum,
                "reference_regime": r.reference_regime,
                "reference_reason": r.reference_reason,
                "di_gap": r.di_gap,
                "ema_slope": r.ema_slope,
                "ref_channel_high": r.ref_channel_high,
                "ref_channel_low": r.ref_channel_low,
                "ref_displacement": r.ref_displacement,
            }
            for r in rows
        ],
    }


@history_router.get("/runs/{run_id}/regime-band")
def get_regime_band(
    run_id: int,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Compact per-bar regime series for chart bands (one row per bar, no OHLC).

    `/bars` returns ~630 bytes/bar because it carries OHLC, HMM posteriors, RF
    probabilities and reference diagnostics. A regime band needs only the label
    and the timestamp, so this endpoint returns the minimum (~40 bytes/bar) and
    the chart stops waiting on tens of megabytes to draw a coloured strip.
    """
    _get_run_or_404(db, run_id)
    from app.models import RegimeHistoryBar

    rows = (
        db.query(
            RegimeHistoryBar.ts,
            RegimeHistoryBar.regime,
            RegimeHistoryBar.confidence,
            RegimeHistoryBar.reference_regime,
        )
        .filter(RegimeHistoryBar.run_id == run_id)
        .order_by(RegimeHistoryBar.ts)
        .all()
    )
    return {
        "run_id": run_id,
        "total": len(rows),
        "bars": [
            {
                "ts": ensure_utc(r[0]).isoformat(),
                "regime": r[1],
                "confidence": r[2],
                "reference_regime": r[3],
            }
            for r in rows
        ],
    }


@history_router.get("/runs/{run_id}/segments")
def get_segments(
    run_id: int,
    regime: str | None = Query(None),
    min_duration: int | None = Query(None, ge=1),
    max_duration: int | None = Query(None, ge=1),
    limit: int = Query(500, ge=1, le=5000),
    offset: int = Query(0, ge=0),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_run_or_404(db, run_id)
    segs = load_run_segments(db, run_id)
    if regime:
        segs = [s for s in segs if s["regime"] == regime]
    if min_duration:
        segs = [s for s in segs if s["duration_minutes"] >= min_duration]
    if max_duration:
        segs = [s for s in segs if s["duration_minutes"] <= max_duration]
    total = len(segs)
    return {"run_id": run_id, "total": total, "limit": limit, "offset": offset,
            "segments": segs[offset : offset + limit]}


@history_router.get("/runs/{run_id}/segments/{seg_id}")
def get_segment(
    run_id: int,
    seg_id: int,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_run_or_404(db, run_id)
    segs = load_run_segments(db, run_id)
    for s in segs:
        if s["id"] == seg_id:
            return s
    raise HTTPException(404, "Segment not found")


@history_router.get("/cache/stats")
def cache_stats(_: User = Depends(require_admin)):
    """Cache effectiveness for the expensive history stats (admin only)."""
    return stats_cache.info()


@history_router.post("/cache/invalidate")
def cache_invalidate(
    run_id: int | None = Query(None),
    _: User = Depends(require_admin),
):
    removed = stats_cache.invalidate(run_id)
    return {"invalidated": removed, "scope": run_id if run_id else "all"}


@history_router.post("/predictions/backfill")
def predictions_backfill(
    symbol: str = Query("XAUUSD"),
    max_bars: int = Query(500, ge=1, le=5000),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Score closed bars that have no prediction yet (gap after downtime).

    Runs automatically every few minutes; this endpoint exists to force it
    immediately and to see what was missing.
    """
    from app.services.prediction import backfill_predictions

    return backfill_predictions(db, symbol, max_bars=max_bars)


@history_router.get("/runs/{run_id}/stats/duration")
def stats_duration(
    run_id: int,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    run = _get_run_or_404(db, run_id)

    def _compute():
        segs = load_run_segments(db, run_id)
        return {"run_id": run_id, "regimes": duration_statistics(segs),
                "total_transitions": transition_count(segs)}

    return _cached_stats(run, "duration", _compute)


@history_router.get("/runs/{run_id}/stats/trends")
def stats_trends(
    run_id: int,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    run = _get_run_or_404(db, run_id)
    return _cached_stats(
        run, "trends",
        lambda: {"run_id": run_id, **trend_analysis(load_run_segments(db, run_id))},
    )


@history_router.get("/runs/{run_id}/stats/sideways")
def stats_sideways(
    run_id: int,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    run = _get_run_or_404(db, run_id)
    return _cached_stats(
        run, "sideways",
        lambda: {"run_id": run_id, **sideways_analysis(load_run_segments(db, run_id))},
    )


@history_router.get("/runs/{run_id}/stats/early_trend")
def stats_early_trend(
    run_id: int,
    window: int = Query(12, ge=2, le=96),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    run = _get_run_or_404(db, run_id)

    def _compute():
        bars = load_run_bars(db, run_id)
        labels = reference_labels(db, run)
        return {"run_id": run_id, **early_trend_analysis(bars, labels, window=window)}

    return _cached_stats(run, "early_trend", _compute, {"window": window})


@history_router.get("/runs/{run_id}/stats/transitions")
def stats_transitions(
    run_id: int,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    run = _get_run_or_404(db, run_id)
    return _cached_stats(
        run, "transitions",
        lambda: {"run_id": run_id, **transition_matrix(load_run_segments(db, run_id))},
    )


@history_router.get("/runs/{run_id}/stats/periods")
def stats_periods(
    run_id: int,
    period: str = Query("day", pattern="^(day|week|month|quarter|year)$"),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    run = _get_run_or_404(db, run_id)
    return _cached_stats(
        run, "periods",
        lambda: {"run_id": run_id, **period_aggregation(
            load_run_bars(db, run_id), load_run_segments(db, run_id), period)},
        {"period": period},
    )


@history_router.get("/runs/{run_id}/stats/multi_tf")
def stats_multi_tf(
    run_id: int,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    run = _get_run_or_404(db, run_id)
    return _cached_stats(
        run, "multi_tf",
        lambda: {"run_id": run_id, **multi_tf_context(load_run_bars(db, run_id))},
    )


@history_router.get("/runs/{run_id}/compare")
def compare(
    run_id: int,
    vs_run_id: int | None = Query(None),
    vs_reference: bool = Query(False),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    run = _get_run_or_404(db, run_id)
    if vs_reference:
        def _compute_ref():
            bars = load_run_bars(db, run_id)
            labels = reference_labels(db, run)
            return {"run_id": run_id, "mode": "reference_labels",
                    **compare_vs_reference(bars, labels)}

        return _cached_stats(run, "compare_reference", _compute_ref)
    if vs_run_id is None:
        raise HTTPException(400, "Need vs_run_id or vs_reference=true")
    other = _get_run_or_404(db, vs_run_id)

    def _compute_run():
        bars = load_run_bars(db, run_id)
        other_bars = load_run_bars(db, vs_run_id)
        return {"mode": "run_vs_run",
                **compare_runs(bars, other_bars, f"run_{run_id}", f"run_{vs_run_id}")}

    return _cached_stats(run, "compare_run", _compute_run, {"vs": vs_run_id})


@history_router.get("/runs/{run_id}/stats/vs_reference")
def stats_vs_reference(
    run_id: int,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    run = _get_run_or_404(db, run_id)

    def _compute():
        from app.ml.history_stats import compare_ai_vs_reference

        bars = load_run_bars(db, run_id)
        return {
            "run_id": run_id,
            "reference_version": run.reference_version,
            "reference_config": run.reference_config_json,
            **compare_ai_vs_reference(bars),
        }

    return _cached_stats(run, "vs_reference", _compute)


@history_router.get("/runs/{run_id}/stats/direction_accuracy")
def stats_direction_accuracy(
    run_id: int,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """How often the trend direction matched realised price action.

    `per_segment`: start-of-signal → segment end (the honest "did the call
    work" number). `per_bar`: did the NEXT closed bar follow the direction.
    """
    from app.ml.history_stats import direction_accuracy

    run = _get_run_or_404(db, run_id)

    def _compute():
        bars = load_run_bars(db, run_id)
        return {"run_id": run_id,
                **direction_accuracy(load_run_segments(db, run_id), bars)}

    return _cached_stats(run, "direction_accuracy", _compute)


@history_router.get("/runs/{run_id}/stats/wrong_direction")
def stats_wrong_direction(
    run_id: int,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Deep statistics on WRONG directional calls: how bad, where, and why."""
    from app.ml.history_stats import wrong_direction_analysis

    run = _get_run_or_404(db, run_id)

    def _compute():
        bars = load_run_bars(db, run_id)
        return {"run_id": run_id,
                **wrong_direction_analysis(load_run_segments(db, run_id), bars)}

    return _cached_stats(run, "wrong_direction", _compute)


@history_router.get("/runs/{run_id}/stats/outcomes")
def stats_outcomes(
    run_id: int,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_run_or_404(db, run_id)
    from app.services.history import load_outcome_summary

    return {"run_id": run_id, **load_outcome_summary(db, run_id)}


# ---------------------------------------------------------------- exports

def _segments_df(db: Session, run_id: int) -> pd.DataFrame:
    return pd.DataFrame(load_run_segments(db, run_id))


def _report_ctx(db: Session, run_id: int) -> dict:
    run = _get_run_or_404(db, run_id)
    segs = load_run_segments(db, run_id)
    bars = load_run_bars(db, run_id)
    labels = reference_labels(db, run)
    return {
        "run": {
            "id": run.id,
            "data_source": run.data_source,
            "data_start": ensure_utc(run.data_start).isoformat() if run.data_start else None,
            "data_end": ensure_utc(run.data_end).isoformat() if run.data_end else None,
            "bars": run.bar_count,
            "segments": run.segment_count,
            "hmm_version": run.hmm_model_version_id,
            "rf_version": run.rf_model_version_id,
        },
        "duration": duration_statistics(segs),
        "trends": trend_analysis(segs),
        "sideways": sideways_analysis(segs),
        "early_trend": early_trend_analysis(bars, labels),
        "transitions": transition_matrix(segs),
        "multi_tf": multi_tf_context(bars),
        "segments": segs,
    }


@history_router.get("/day")
def analyze_day_endpoint(
    day: str | None = Query(None, description="UTC date YYYY-MM-DD; defaults to yesterday"),
    symbol: str = Query("XAUUSD"),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Per-day regime breakdown ("what happened yesterday").

    Causal: only bars with timestamp before the end of the requested day are
    used, so inspecting a past day can never see later data."""
    from app.services.day import DayAnalysisError, analyze_day

    try:
        return analyze_day(db, day, symbol)
    except DayAnalysisError as e:
        raise HTTPException(400, str(e))


@history_router.get("/runs/{run_id}/export")
def export(
    run_id: int,
    format: str = Query("csv", pattern="^(csv|xlsx|pdf)$"),
    scope: str = Query("segments", pattern="^(segments|bars|report)$"),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    run = _get_run_or_404(db, run_id)
    if scope in ("segments", "bars"):
        df = _segments_df(db, run_id) if scope == "segments" else load_run_bars(db, run_id).reset_index()
        if format == "csv":
            buf = io.StringIO()
            df.to_csv(buf, index=False)
            return Response(buf.getvalue(), media_type="text/csv",
                            headers={"Content-Disposition": f"attachment; filename=gmrai_{scope}_{run_id}.csv"})
        if format == "xlsx":
            if "ts" in df.columns:
                # openpyxl cannot write tz-aware datetimes — store naive UTC
                df = df.copy()
                df["ts"] = pd.to_datetime(df["ts"], utc=True).dt.tz_localize(None)
            out = io.BytesIO()
            with pd.ExcelWriter(out, engine="openpyxl") as writer:
                df.to_excel(writer, index=False, sheet_name=scope)
            return Response(out.getvalue(),
                            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            headers={"Content-Disposition": f"attachment; filename=gmrai_{scope}_{run_id}.xlsx"})
        raise HTTPException(400, "PDF only for scope=report")

    # report (PDF)
    from app.ml.history_export import build_pdf_report

    ctx = _report_ctx(db, run_id)
    pdf = build_pdf_report(ctx)
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f"attachment; filename=gmrai_report_{run_id}.pdf"})
