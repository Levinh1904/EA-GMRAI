from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import MarketCandle, User
from app.timeutil import ensure_utc

market_router = APIRouter(prefix="/market", tags=["market"])


@market_router.get("/candles")
def candles(
    timeframe: str = Query("M15", pattern="^(M5|M15|H1)$"),
    symbol: str = Query("XAUUSD"),
    from_ts: datetime | None = Query(None, alias="from"),
    to_ts: datetime | None = Query(None, alias="to"),
    limit: int = Query(500, ge=1, le=5000),
    offset: int = Query(0, ge=0),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Paginated closed candles — never the full history in one response."""
    q = db.query(MarketCandle).filter(
        MarketCandle.symbol == symbol, MarketCandle.timeframe == timeframe
    )
    if from_ts is not None:
        q = q.filter(MarketCandle.ts >= ensure_utc(from_ts))
    if to_ts is not None:
        q = q.filter(MarketCandle.ts <= ensure_utc(to_ts))
    total = q.count()
    rows = q.order_by(MarketCandle.ts.asc()).offset(offset).limit(limit).all()
    return {
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
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    out = {}
    for tf in ("M5", "M15", "H1"):
        row = (
            db.query(MarketCandle)
            .filter(MarketCandle.symbol == symbol, MarketCandle.timeframe == tf)
            .order_by(MarketCandle.ts.desc())
            .first()
        )
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
