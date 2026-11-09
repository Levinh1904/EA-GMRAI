"""Data quality checks: gaps, duplicates, bad candles, staleness."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.models import DataQualityReport, MarketCandle
from app.timeutil import ensure_utc, timeframe_seconds, utcnow

logger = logging.getLogger("gmrai.quality")


def _is_weekend_span(start: datetime, end: datetime) -> bool:
    """True if the gap spans a full Saturday (market closed weekend)."""
    span = (end - start).total_seconds()
    if span < 86400 * 1.5:
        return False
    d = start
    seen_saturday = False
    while d < end:
        if d.weekday() == 5:  # Saturday
            seen_saturday = True
        d += timedelta(hours=24)
    return seen_saturday


def run_quality_check(
    db: Session,
    symbol: str = "XAUUSD",
    timeframe: str = "M15",
    now: datetime | None = None,
) -> dict:
    now = now or utcnow()
    period = timeframe_seconds(timeframe)
    rows = (
        db.query(MarketCandle.ts)
        .filter(MarketCandle.symbol == symbol, MarketCandle.timeframe == timeframe)
        .order_by(MarketCandle.ts)
        .all()
    )
    times = [ensure_utc(r[0]) for r in rows]

    gaps, weekend_gaps, duplicates = [], [], 0
    prev = None
    for i, t in enumerate(times):
        if prev is not None:
            delta = (t - prev).total_seconds()
            if t == prev:
                duplicates += 1
            elif delta > period * 1.5:
                if _is_weekend_span(prev, t):
                    weekend_gaps.append({"from": prev.isoformat(), "to": t.isoformat()})
                else:
                    gaps.append(
                        {
                            "from": prev.isoformat(),
                            "to": t.isoformat(),
                            "missing_bars": int(delta / period) - 1,
                        }
                    )
        prev = t

    bad_candles = (
        db.query(func.count(MarketCandle.id))
        .filter(
            MarketCandle.symbol == symbol,
            MarketCandle.timeframe == timeframe,
            (MarketCandle.high < MarketCandle.low)
            | (MarketCandle.open <= 0)
            | (MarketCandle.high < func.max(MarketCandle.open, MarketCandle.close))
            | (MarketCandle.low > func.min(MarketCandle.open, MarketCandle.close)),
        )
        .scalar()
    ) or 0

    latest = times[-1] if times else None
    stale = latest is not None and (now - latest).total_seconds() > settings.max_age_minutes(timeframe) * 60

    report = DataQualityReport(
        symbol=symbol,
        timeframe=timeframe,
        checked_at=now,
        window_start=times[0] if times else None,
        window_end=latest,
        total_candles=len(times),
        missing_count=sum(g["missing_bars"] for g in gaps),
        duplicate_count=duplicates,
        gap_count=len(gaps),
        bad_candle_count=int(bad_candles),
        stale_ts=latest,
        report_json={
            "gaps": gaps[:200],
            "weekend_gaps_count": len(weekend_gaps),
            "stale": stale,
        },
    )
    db.add(report)
    db.commit()
    return {
        "report_id": report.id,
        "total_candles": report.total_candles,
        "gap_count": report.gap_count,
        "duplicate_count": report.duplicate_count,
        "bad_candle_count": report.bad_candle_count,
        "latest_ts": latest.isoformat() if latest else None,
        "stale": stale,
    }
