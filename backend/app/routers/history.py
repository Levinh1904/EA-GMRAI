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


@history_router.post("/run")
def start_run(
    regenerate: bool = Query(False),
    symbol: str = Query("XAUUSD"),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    run = RegimeHistoryRun(symbol=symbol, timeframe="M15", status="pending", config_json=HistoryConfig(symbol=symbol).to_dict())
    db.add(run)
    db.commit()
    worker.submit("regime_history", {"run_id": run.id}, lambda s: run_history_job(s, run.id, HistoryConfig(symbol=symbol)))
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
    bars = load_run_bars(db, run_id)
    total = len(bars)
    page = bars.iloc[offset : offset + limit]
    return {
        "run_id": run_id,
        "total": total,
        "limit": limit,
        "offset": offset,
        "bars": [
            {
                "ts": ts.isoformat(),
                "regime": row["regime"],
                "confidence": row["confidence"],
                "permission": row["permission"],
                "hmm_state": row["hmm_state"],
                "hmm_posterior": row["hmm_posterior"],
                "rf_probs": row["rf_probs"],
                "reason_codes": row["reason_codes"],
                "open": row["open"],
                "high": row["high"],
                "low": row["low"],
                "close": row["close"],
                "atr_ratio": row["atr_ratio"],
                "adx_norm": row["adx_norm"],
                "efficiency_ratio": row["efficiency_ratio"],
                "h1_trend_context": row["h1_trend_context"],
                "m5_momentum": row["m5_momentum"],
            }
            for ts, row in page.iterrows()
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


@history_router.get("/runs/{run_id}/stats/duration")
def stats_duration(
    run_id: int,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_run_or_404(db, run_id)
    segs = load_run_segments(db, run_id)
    return {"run_id": run_id, "regimes": duration_statistics(segs),
            "total_transitions": transition_count(segs)}


@history_router.get("/runs/{run_id}/stats/trends")
def stats_trends(
    run_id: int,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_run_or_404(db, run_id)
    return {"run_id": run_id, **trend_analysis(load_run_segments(db, run_id))}


@history_router.get("/runs/{run_id}/stats/sideways")
def stats_sideways(
    run_id: int,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_run_or_404(db, run_id)
    return {"run_id": run_id, **sideways_analysis(load_run_segments(db, run_id))}


@history_router.get("/runs/{run_id}/stats/early_trend")
def stats_early_trend(
    run_id: int,
    window: int = Query(12, ge=2, le=96),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    run = _get_run_or_404(db, run_id)
    bars = load_run_bars(db, run_id)
    labels = reference_labels(db, run)
    return {"run_id": run_id, **early_trend_analysis(bars, labels, window=window)}


@history_router.get("/runs/{run_id}/stats/transitions")
def stats_transitions(
    run_id: int,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_run_or_404(db, run_id)
    return {"run_id": run_id, **transition_matrix(load_run_segments(db, run_id))}


@history_router.get("/runs/{run_id}/stats/periods")
def stats_periods(
    run_id: int,
    period: str = Query("day", pattern="^(day|week|month|quarter|year)$"),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_run_or_404(db, run_id)
    return {"run_id": run_id,
            **period_aggregation(load_run_bars(db, run_id), load_run_segments(db, run_id), period)}


@history_router.get("/runs/{run_id}/stats/multi_tf")
def stats_multi_tf(
    run_id: int,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_run_or_404(db, run_id)
    return {"run_id": run_id, **multi_tf_context(load_run_bars(db, run_id))}


@history_router.get("/runs/{run_id}/compare")
def compare(
    run_id: int,
    vs_run_id: int | None = Query(None),
    vs_reference: bool = Query(False),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    run = _get_run_or_404(db, run_id)
    bars = load_run_bars(db, run_id)
    if vs_reference:
        labels = reference_labels(db, run)
        return {"run_id": run_id, "mode": "reference_labels", **compare_vs_reference(bars, labels)}
    if vs_run_id is None:
        raise HTTPException(400, "Need vs_run_id or vs_reference=true")
    other = _get_run_or_404(db, vs_run_id)
    other_bars = load_run_bars(db, vs_run_id)
    return {"mode": "run_vs_run",
            **compare_runs(bars, other_bars, f"run_{run_id}", f"run_{vs_run_id}")}


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
