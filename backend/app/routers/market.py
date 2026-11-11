from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import MarketCandle, User
from app.timeutil import ensure_utc

market_router = APIRouter(prefix="/market", tags=["market"])


def _active_source(db: Session, symbol: str, timeframe: str) -> str | None:
    """Source of the newest candle (single source of truth — never mix brokers).

    Real `ftmo_mt5` data is preferred; demo `synthetic_demo` is only a fallback
    when no real feed exists yet."""
    has_ftmo = (
        db.query(MarketCandle.id)
        .filter(MarketCandle.symbol == symbol, MarketCandle.timeframe == timeframe,
                MarketCandle.source == "ftmo_mt5")
        .first()
    )
    if has_ftmo:
        return "ftmo_mt5"
    row = (
        db.query(MarketCandle.source)
        .filter(MarketCandle.symbol == symbol, MarketCandle.timeframe == timeframe)
        .order_by(MarketCandle.ts.desc())
        .first()
    )
    return row[0] if row else None


@market_router.get("/candles")
def candles(
    timeframe: str = Query("M15", pattern="^(M5|M15|H1)$"),
    symbol: str = Query("XAUUSD"),
    source: str | None = Query(None),
    from_ts: datetime | None = Query(None, alias="from"),
    to_ts: datetime | None = Query(None, alias="to"),
    limit: int = Query(500, ge=1, le=5000),
    offset: int = Query(0, ge=0),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Paginated closed candles — never the full history in one response.

    `source` defaults to the newest candle's source (single source of truth —
    real `ftmo_mt5` and demo `synthetic_demo` feeds are never mixed)."""
    q = db.query(MarketCandle).filter(
        MarketCandle.symbol == symbol, MarketCandle.timeframe == timeframe
    )
    eff_source = source or _active_source(db, symbol, timeframe)
    if eff_source:
        q = q.filter(MarketCandle.source == eff_source)
    if from_ts is not None:
        q = q.filter(MarketCandle.ts >= ensure_utc(from_ts))
    if to_ts is not None:
        q = q.filter(MarketCandle.ts <= ensure_utc(to_ts))
    total = q.count()
    rows = q.order_by(MarketCandle.ts.asc()).offset(offset).limit(limit).all()
    return {
        "source": eff_source,
        "total": total,
        "limit": limit,
        "offset": offset,
        "candles": [
            {
                "ts": ensure_utc(r.ts).isoformat(),
                "open": r.open,
                "high": r.high,
                "low": r.low,
                "close": r.close,
                "tick_volume": r.tick_volume,
                "spread": r.spread,
                "source": r.source,
            }
            for r in rows
        ],
    }


@market_router.get("/latest")
def latest(
    symbol: str = Query("XAUUSD"),
    source: str | None = Query(None),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    out = {}
    for tf in ("M5", "M15", "H1"):
        eff_source = source or _active_source(db, symbol, tf)
        row = (
            db.query(MarketCandle)
            .filter(MarketCandle.symbol == symbol, MarketCandle.timeframe == tf)
        )
        if eff_source:
            row = row.filter(MarketCandle.source == eff_source)
        row = row.order_by(MarketCandle.ts.desc()).first()
        out[tf] = (
            {
                "ts": ensure_utc(row.ts).isoformat(),
                "open": row.open,
                "high": row.high,
                "low": row.low,
                "close": row.close,
                "tick_volume": row.tick_volume,
                "spread": row.spread,
                "source": row.source,
            }
            if row
            else None
        )
    return {"symbol": symbol, "latest": out}
