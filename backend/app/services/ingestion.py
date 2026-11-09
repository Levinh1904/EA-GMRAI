"""Candle ingestion: validation, closed-bar check, upsert, sync logs."""
from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import DataSyncLog, MarketCandle
from app.timeutil import ensure_utc, timeframe_seconds, utcnow

logger = logging.getLogger("gmrai.ingestion")

TIMEFRAMES = {"M5", "M15", "H1"}
MAX_BATCH = 10_000


class IngestionError(ValueError):
    pass


def validate_candle(c: dict, timeframe: str, now: datetime) -> dict:
    """Validate one candle; raises IngestionError on invalid input."""
    if c.get("symbol") not in {"XAUUSD"}:
        raise IngestionError(f"Unsupported symbol {c.get('symbol')!r}")
    if timeframe not in TIMEFRAMES:
        raise IngestionError(f"Unsupported timeframe {timeframe!r}")
    ts = c.get("ts")
    if not isinstance(ts, datetime):
        raise IngestionError("Candle 'ts' must be a datetime (UTC)")
    ts = ensure_utc(ts)
    period = timeframe_seconds(timeframe)
    if ts + timedelta(seconds=period) > now:
        raise IngestionError(f"Rejecting forming candle at {ts.isoformat()}")

    o, h, l, cl = c.get("open"), c.get("high"), c.get("low"), c.get("close")
    if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in (o, h, l, cl)):
        raise IngestionError(f"Non-finite OHLC at {ts.isoformat()}")
    if o <= 0 or h <= 0 or l <= 0 or cl <= 0:
        raise IngestionError(f"Non-positive OHLC at {ts.isoformat()}")
    if h < max(o, cl) or l > min(o, cl) or h < l:
        raise IngestionError(f"OHLC consistency violated at {ts.isoformat()}")

    tick_volume = c.get("tick_volume", 0)
    if not isinstance(tick_volume, int) or tick_volume < 0:
        raise IngestionError(f"Invalid tick_volume at {ts.isoformat()}")

    return {
        "symbol": c["symbol"],
        "timeframe": timeframe,
        "ts": ts,
        "open": float(o),
        "high": float(h),
        "low": float(l),
        "close": float(cl),
        "tick_volume": int(tick_volume),
        "spread": int(c["spread"]) if c.get("spread") is not None else None,
        "real_volume": int(c["real_volume"]) if c.get("real_volume") is not None else None,
        "source": str(c.get("source", "ftmo_mt5"))[:32],
    }


def ingest_candles(
    db: Session,
    candles: list[dict],
    timeframe: str,
    collector_id: str = "unknown",
    now: datetime | None = None,
    strict: bool = False,
) -> dict:
    """Validate + upsert a batch of closed candles. Returns summary."""
    now = now or utcnow()
    if not candles:
        return {"received": 0, "inserted": 0, "updated": 0, "rejected": 0}
    if len(candles) > MAX_BATCH:
        raise IngestionError(f"Batch too large: {len(candles)} > {MAX_BATCH}")

    valid, rejected = [], 0
    for c in candles:
        try:
            valid.append(validate_candle(c, timeframe, now))
        except IngestionError as e:
            logger.warning("Rejected candle: %s", e)
            rejected += 1
            if strict:
                raise

    inserted = updated = 0
    if valid:
        symbol = valid[0]["symbol"]
        keys = [(v["ts"],) for v in valid]
        # Fetch existing rows for these keys.
        times = [v["ts"] for v in valid]
        existing = (
            db.execute(
                select(MarketCandle).where(
                    MarketCandle.symbol == symbol,
                    MarketCandle.timeframe == timeframe,
                    MarketCandle.ts.in_(times),
                )
            )
            .scalars()
            .all()
        )
        existing_by_ts = {ensure_utc(e.ts): e for e in existing}
        for v in valid:
            row = existing_by_ts.get(v["ts"])
            if row is None:
                db.add(MarketCandle(**v))
                inserted += 1
            else:
                for field in ("open", "high", "low", "close", "tick_volume", "spread", "real_volume", "source"):
                    setattr(row, field, v[field])
                updated += 1
        db.commit()

    log = DataSyncLog(
        collector_id=collector_id,
        symbol=valid[0]["symbol"] if valid else "XAUUSD",
        timeframe=timeframe,
        started_at=None,
        finished_at=now,
        candles_received=len(candles),
        candles_inserted=inserted,
        candles_updated=updated,
        status="partial" if rejected else "ok",
        message=f"{rejected} rejected" if rejected else None,
    )
    db.add(log)
    db.commit()

    return {
        "received": len(candles),
        "inserted": inserted,
        "updated": updated,
        "rejected": rejected,
    }
