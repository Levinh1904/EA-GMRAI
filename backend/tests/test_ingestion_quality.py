"""Ingestion validation + data quality checks."""
from datetime import datetime, timedelta, timezone

import pytest

from app.models import MarketCandle
from app.services.ingestion import IngestionError, ingest_candles, validate_candle
from app.services.quality import run_quality_check


def _c(ts, o=2400.0, h=2401.0, l=2399.0, c=2400.5, **kw):
    return {"symbol": "XAUUSD", "ts": ts, "open": o, "high": h, "low": l, "close": c, "tick_volume": 100, **kw}


def test_reject_forming_candle():
    now = datetime(2026, 1, 5, 12, 0, tzinfo=timezone.utc)
    ts = datetime(2026, 1, 5, 11, 50, tzinfo=timezone.utc)  # M15 bar 11:50-12:05 not closed
    with pytest.raises(IngestionError):
        validate_candle(_c(ts), "M15", now)


def test_accept_closed_candle():
    now = datetime(2026, 1, 5, 12, 20, tzinfo=timezone.utc)
    ts = datetime(2026, 1, 5, 12, 0, tzinfo=timezone.utc)
    v = validate_candle(_c(ts), "M15", now)
    assert v["ts"] == ts


@pytest.mark.parametrize(
    "bad",
    [
        dict(high=2399.0),  # high < max(o,c)
        dict(low=2401.0),  # low > min(o,c)
        dict(high=2399.0, low=2401.0),  # high < low
        dict(open=0.0),  # non-positive
        dict(close=float("nan")),  # non-finite
        dict(tick_volume=-1),  # negative volume
    ],
)
def test_reject_bad_ohlc(bad):
    now = datetime(2026, 1, 5, 12, 20, tzinfo=timezone.utc)
    ts = datetime(2026, 1, 5, 12, 0, tzinfo=timezone.utc)
    with pytest.raises(IngestionError):
        validate_candle(_c(ts, **bad), "M15", now)


def test_ingest_upsert(db):
    from app.db import session

    now = datetime(2026, 1, 6, 12, 20, tzinfo=timezone.utc)
    candles = [_c(now - timedelta(minutes=15 * (i + 1))) for i in range(10)]
    with session() as s:
        r1 = ingest_candles(s, candles, "M15", collector_id="test-collector", now=now)
        assert r1["inserted"] == 10 and r1["updated"] == 0
        # resend with a changed close (late update) -> upsert, no duplicates
        candles2 = [dict(c, close=c["close"] + 0.5) for c in candles]
        r2 = ingest_candles(s, candles2, "M15", collector_id="test-collector", now=now)
        assert r2["inserted"] == 0 and r2["updated"] == 10
        assert s.query(MarketCandle).count() == 10
        assert s.query(MarketCandle).filter(MarketCandle.close == 2401.0).count() == 10


def test_quality_gap_detection(db):
    from app.db import session

    now = datetime(2026, 1, 6, 12, 20, tzinfo=timezone.utc)
    times = [now - timedelta(minutes=15 * (i + 1)) for i in range(20)]
    # remove bars 8..10 -> a gap of 3 bars
    keep = [t for i, t in enumerate(times) if not (8 <= i <= 10)]
    with session() as s:
        ingest_candles(s, [_c(t) for t in keep], "M15", now=now)
        out = run_quality_check(s, "XAUUSD", "M15", now=now)
        assert out["gap_count"] == 1
        assert out["total_candles"] == 17


def test_quality_weekend_gap_not_flagged(db):
    from app.db import session

    friday = datetime(2026, 1, 9, 21, 0, tzinfo=timezone.utc)  # Friday 21:00
    sunday = datetime(2026, 1, 11, 22, 0, tzinfo=timezone.utc)  # Sunday 22:00
    now = sunday + timedelta(hours=2)
    with session() as s:
        ingest_candles(s, [_c(friday), _c(sunday)], "H1", now=now)
        out = run_quality_check(s, "XAUUSD", "H1", now=now)
        assert out["gap_count"] == 0  # weekend break is expected


def test_quality_stale(db):
    from app.db import session

    old = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    now = datetime(2026, 1, 6, 12, 0, tzinfo=timezone.utc)
    with session() as s:
        ingest_candles(s, [_c(old)], "M15", now=now)
        out = run_quality_check(s, "XAUUSD", "M15", now=now)
        assert out["stale"] is True
