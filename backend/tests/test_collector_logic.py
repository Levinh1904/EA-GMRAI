"""Collector logic tests (no MT5/Windows needed — data_sync is pure)."""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "collector"))

from data_sync import (  # type: ignore
    CheckpointStore,
    check_gaps,
    closed_bars_only,
    dedupe_bars,
    plan_fetch_range,
    run_sync,
)


def _bar(ts: datetime, o=100.0, h=101.0, l=99.0, c=100.5):
    return {"ts": ts, "open": o, "high": h, "low": l, "close": c, "tick_volume": 10}


def test_closed_bars_only():
    now = datetime(2026, 2, 2, 12, 0, tzinfo=timezone.utc)
    bars = [
        _bar(now - timedelta(minutes=30)),  # closed
        _bar(now - timedelta(minutes=15)),  # closed (closes exactly at now)
        _bar(now),  # forming
    ]
    out = closed_bars_only(bars, "M15", now)
    assert len(out) == 2
    assert out[-1]["ts"] == now - timedelta(minutes=15)


def test_dedupe_keeps_latest():
    now = datetime(2026, 2, 2, 12, 0, tzinfo=timezone.utc)
    t = now - timedelta(minutes=15)
    bars = [_bar(t, c=100.0), _bar(t, c=100.7)]
    out = dedupe_bars(bars)
    assert len(out) == 1 and out[0]["close"] == 100.7


def test_check_gaps_weekend_ok():
    period = timedelta(minutes=15)
    start = datetime(2026, 1, 9, 20, 0, tzinfo=timezone.utc)  # Friday
    bars = []
    t = start
    # Friday 20:00..21:00 then jump to Sunday 22:00 (weekend break, not a gap)
    while t <= start + timedelta(hours=1):
        bars.append(_bar(t))
        t += period
    bars.append(_bar(datetime(2026, 1, 11, 22, 0, tzinfo=timezone.utc)))  # Sunday
    q = check_gaps(bars, "M15")
    assert q["gap_count"] == 0
    assert q["weekend_gap_count"] == 1


def test_check_gaps_real_gap():
    now = datetime(2026, 2, 2, 12, 0, tzinfo=timezone.utc)
    bars = [
        _bar(now - timedelta(minutes=60)),
        _bar(now - timedelta(minutes=45)),
        _bar(now - timedelta(minutes=15)),  # 30-minute hole
        _bar(now),
    ]
    q = check_gaps(bars, "M15")
    assert q["gap_count"] == 1


def test_check_gaps_bad_bar():
    now = datetime(2026, 2, 2, 12, 0, tzinfo=timezone.utc)
    bars = [_bar(now - timedelta(minutes=30), h=90.0), _bar(now - timedelta(minutes=15))]
    q = check_gaps(bars, "M15")
    assert q["bad_bar_count"] == 1


def test_plan_fetch_range():
    now = datetime(2026, 2, 2, 12, 0, tzinfo=timezone.utc)
    # no checkpoint -> backfill
    start = plan_fetch_range(None, "M15", now, resync_bars=50, history_days=10)
    assert start == now - timedelta(days=10)
    # with checkpoint -> resync overlap of 50 bars
    ckpt = datetime(2026, 2, 2, 10, 0, tzinfo=timezone.utc)
    start = plan_fetch_range(ckpt, "M15", now, resync_bars=50)
    assert start == ckpt - timedelta(minutes=15 * 50)


def test_run_sync_end_to_end(tmp_path):
    now = datetime(2026, 2, 2, 12, 0, tzinfo=timezone.utc)
    period = timedelta(minutes=15)
    sent_payloads: list[list] = []
    fetched = []

    def fetch_fn(symbol, tf, start, end):
        return list(fetched)

    def send_fn(tf, candles):
        sent_payloads.append(list(candles))
        return {"inserted": len(candles), "updated": 0}

    ckpt = CheckpointStore(str(tmp_path))
    bars = [_bar(now - timedelta(minutes=15 * (i + 1))) for i in range(10)]
    fetched.extend(bars)

    r = run_sync(fetch_fn, send_fn, ckpt, "XAUUSD", "M15", now, resync_bars=5)
    assert r["closed"] == 10 and r["sent"] == 10
    assert r["checkpoint"] == bars[0]["ts"].isoformat()
    assert ckpt.load("XAUUSD", "M15") == bars[0]["ts"]

    # next cycle: fetch returns 2 new bars, but only 1 is closed yet
    new_bars = [_bar(now + timedelta(minutes=15 * i)) for i in range(1, 3)]
    fetched.clear()
    fetched.extend(new_bars)
    r2 = run_sync(fetch_fn, send_fn, ckpt, "XAUUSD", "M15", now + timedelta(minutes=30), resync_bars=5)
    assert r2["sent"] == 1  # forming bar (now+30) is never sent
    assert ckpt.load("XAUUSD", "M15") == new_bars[0]["ts"]


def test_run_sync_no_fabrication(tmp_path):
    """Missing bars are never fabricated — they are reported, not invented."""
    now = datetime(2026, 2, 2, 12, 0, tzinfo=timezone.utc)
    holes = [
        _bar(now - timedelta(minutes=15)),
        _bar(now - timedelta(minutes=75)),  # 60-minute hole before this
    ]

    def fetch_fn(symbol, tf, start, end):
        return list(holes)

    sent = []

    def send_fn(tf, candles):
        sent.extend(candles)
        return {"inserted": len(candles), "updated": 0}

    ckpt = CheckpointStore(str(tmp_path))
    r = run_sync(fetch_fn, send_fn, ckpt, "XAUUSD", "M15", now, resync_bars=5)
    assert r["gap_count"] == 1
    assert len(sent) == 2  # nothing invented to fill the hole
