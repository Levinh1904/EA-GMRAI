from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user, ingest_identity
from app.models import MarketCandle, MarketTick, User
from app.services.source import active_source
from app.timeutil import ensure_utc, utcnow

market_router = APIRouter(prefix="/market", tags=["market"])


class TickIn(BaseModel):
    symbol: str = "XAUUSD"
    bid: float
    ask: float
    last: float | None = None
    spread: int = 0
    ts: datetime | None = None


def _active_source(db: Session, symbol: str, timeframe: str) -> str | None:
    """Source of the newest candle (single source of truth — never mix brokers)."""
    return active_source(db, symbol, timeframe)


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


@market_router.post("/tick")
def post_tick(
    body: TickIn,
    identity: dict = Depends(ingest_identity),
    db: Session = Depends(get_db),
):
    """Collector posts the latest Bid/Ask tick (display-only, X-API-Key auth)."""
    now = utcnow()
    tick = db.query(MarketTick).filter(MarketTick.symbol == body.symbol).first()
    if tick is None:
        tick = MarketTick(symbol=body.symbol, ts=now, bid=body.bid, ask=body.ask,
                          last=body.last if body.last is not None else body.bid, spread=body.spread)
        db.add(tick)
    else:
        tick.ts = body.ts or now
        tick.bid = body.bid
        tick.ask = body.ask
        tick.last = body.last if body.last is not None else body.bid
        tick.spread = body.spread
        tick.source = identity.get("collector_id", "ftmo_mt5")[:32]
        tick.updated_at = now
    db.commit()
    return {"status": "ok", "symbol": body.symbol, "bid": body.bid, "ask": body.ask}


@market_router.get("/tick")
def get_tick(
    symbol: str = Query("XAUUSD"),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Latest live tick + age. Stale when older than a configurable threshold."""
    from app.config import settings

    tick = db.query(MarketTick).filter(MarketTick.symbol == symbol).first()
    if tick is None:
        return {"symbol": symbol, "bid": None, "ask": None, "last": None,
                "ts": None, "age_seconds": None, "stale": True, "live": False}
    ts = ensure_utc(tick.ts)
    age = (utcnow() - ts).total_seconds()
    return {
        "symbol": symbol,
        "bid": tick.bid,
        "ask": tick.ask,
        "last": tick.last,
        "spread": tick.spread,
        "ts": ts.isoformat(),
        "age_seconds": round(age, 1),
        "stale": age > settings.max_age_m5_minutes * 60,
        "live": True,
        "note": "Giá Bid/Ask trực tiếp — chỉ hiển thị, không dùng cho phân tích AI.",
    }
