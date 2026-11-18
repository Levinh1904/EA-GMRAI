"""Active data-source resolution — one feed at a time, never mixed.

Real `ftmo_mt5` data wins whenever it exists; `synthetic_demo` is only used as
a fallback while a real feed has not arrived yet. Every read path (training,
prediction, quality, stats, history) resolves its source here so candles from
different brokers can never be interleaved in one computation.
"""
from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import MarketCandle

REAL_SOURCE = "ftmo_mt5"


def active_source(
    db: Session,
    symbol: str = "XAUUSD",
    timeframe: str = "M15",
    requested: str | None = None,
) -> str | None:
    """Explicit `requested` source wins; else real feed; else newest source."""
    if requested:
        return requested
    has_real = (
        db.query(MarketCandle.id)
        .filter(
            MarketCandle.symbol == symbol,
            MarketCandle.timeframe == timeframe,
            MarketCandle.source == REAL_SOURCE,
        )
        .first()
    )
    if has_real:
        return REAL_SOURCE
    row = (
        db.query(MarketCandle.source)
        .filter(MarketCandle.symbol == symbol, MarketCandle.timeframe == timeframe)
        .order_by(MarketCandle.ts.desc())
        .first()
    )
    return row[0] if row else None


def source_max_ts(
    db: Session, symbol: str = "XAUUSD", timeframe: str = "M15", source: str | None = None
) -> object:
    q = db.query(func.max(MarketCandle.ts)).filter(
        MarketCandle.symbol == symbol, MarketCandle.timeframe == timeframe
    )
    if source:
        q = q.filter(MarketCandle.source == source)
    return q.scalar()
