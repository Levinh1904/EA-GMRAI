"""Sync engine: checkpoint-based incremental sync, closed bars only, client-side
gap/duplicate checks. Pure logic — MT5 access is injected, so this module is
unit-testable outside Windows (see backend/tests/test_collector_logic.py)."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

logger = logging.getLogger("gmrai.collector.sync")

TIMEFRAME_SECONDS = {"M5": 300, "M15": 900, "H1": 3600}


class SyncError(RuntimeError):
    pass


# ---------- checkpoint ----------

class CheckpointStore:
    """Persists the last synced bar time per (symbol, timeframe)."""

    def __init__(self, directory: str):
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)

    def _path(self, symbol: str, timeframe: str) -> Path:
        return self.dir / f"{symbol}_{timeframe}.json"

    def load(self, symbol: str, timeframe: str) -> datetime | None:
        p = self._path(symbol, timeframe)
        if not p.exists():
            return None
        try:
            data = json.loads(p.read_text())
            return datetime.fromisoformat(data["last_ts"])
        except (ValueError, KeyError):
            logger.warning("Corrupt checkpoint %s — starting fresh", p)
            return None

    def save(self, symbol: str, timeframe: str, ts: datetime) -> None:
        self._path(symbol, timeframe).write_text(json.dumps({"last_ts": ts.isoformat()}))

    def reset(self, symbol: str, timeframe: str) -> None:
        p = self._path(symbol, timeframe)
        if p.exists():
            p.unlink()


# ---------- pure sync logic ----------

def period_seconds(timeframe: str) -> int:
    if timeframe not in TIMEFRAME_SECONDS:
        raise ValueError(f"Unsupported timeframe {timeframe}")
    return TIMEFRAME_SECONDS[timeframe]


def closed_bars_only(bars: list[dict], timeframe: str, now: datetime) -> list[dict]:
    """Drop the forming (unclosed) bar: keep only ts + period <= now."""
    period = timedelta(seconds=period_seconds(timeframe))
    return [b for b in bars if b["ts"] + period <= now]


def dedupe_bars(bars: list[dict]) -> list[dict]:
    seen: dict[datetime, dict] = {}
    for b in bars:
        seen[b["ts"]] = b  # keep the latest version of a duplicated bar
    return sorted(seen.values(), key=lambda b: b["ts"])


def _is_weekend_span(start: datetime, end: datetime) -> bool:
    span = (end - start).total_seconds()
    if span < 86400 * 1.5:
        return False
    d = start
    while d < end:
        if d.weekday() == 5:
            return True
        d += timedelta(hours=24)
    return False


def check_gaps(bars: list[dict], timeframe: str) -> dict:
    """Client-side gap check. Weekend breaks are expected, not errors."""
    period = period_seconds(timeframe)
    gaps, weekend_gaps, bad = [], [], 0
    prev: dict | None = None
    for b in bars:
        o, h, l, c = b["open"], b["high"], b["low"], b["close"]
        if not (h >= max(o, c) and l <= min(o, c) and h >= l and min(o, h, l, c) > 0):
            bad += 1
        if prev is not None:
            delta = (b["ts"] - prev["ts"]).total_seconds()
            if delta <= 0:
                bad += 1  # duplicate or out-of-order (dedupe happens before this)
            elif delta > period * 1.5:
                if _is_weekend_span(prev["ts"], b["ts"]):
                    weekend_gaps.append((prev["ts"].isoformat(), b["ts"].isoformat()))
                else:
                    gaps.append((prev["ts"].isoformat(), b["ts"].isoformat()))
        prev = b
    return {"gap_count": len(gaps), "weekend_gap_count": len(weekend_gaps), "bad_bar_count": bad}


def plan_fetch_range(
    checkpoint_ts: datetime | None,
    timeframe: str,
    now: datetime,
    resync_bars: int,
    history_days: int | None = None,
) -> datetime:
    """Start time for the next fetch.

    - No checkpoint: backfill from now - history_days (or a sane default).
    - With checkpoint: re-fetch the last `resync_bars` bars to absorb late
      updates, i.e. start = checkpoint - resync_bars * period.
    """
    period = timedelta(seconds=period_seconds(timeframe))
    if checkpoint_ts is None:
        days = history_days or 365
        return now - timedelta(days=days)
    start = checkpoint_ts - period * resync_bars
    return start


def run_sync(
    fetch_fn: Callable[[str, datetime, datetime], list[dict]],
    send_fn: Callable[[str, list[dict]], dict],
    checkpoint: CheckpointStore,
    symbol: str,
    timeframe: str,
    now: datetime,
    resync_bars: int = 50,
    history_days: int | None = None,
) -> dict:
    """One sync cycle for one timeframe. Returns a summary dict."""
    period = timedelta(seconds=period_seconds(timeframe))
    last_ts = checkpoint.load(symbol, timeframe)
    start = plan_fetch_range(last_ts, timeframe, now, resync_bars, history_days)

    raw = fetch_fn(symbol, timeframe, start, now)
    if raw is None:
        raise SyncError(f"fetch returned None for {timeframe}")

    closed = closed_bars_only(raw, timeframe, now)
    closed = dedupe_bars(closed)
    quality = check_gaps(closed, timeframe)
    if quality["bad_bar_count"] > 0:
        logger.warning("%s: %d bad bars detected client-side", timeframe, quality["bad_bar_count"])

    result = {"fetched": len(raw), "closed": len(closed), "sent": 0, "inserted": 0, "updated": 0}
    result.update(quality)

    if closed:
        # Never fabricate missing data: gaps are reported, not filled.
        resp = send_fn(timeframe, closed)
        result["sent"] = len(closed)
        result["inserted"] = int(resp.get("inserted", 0))
        result["updated"] = int(resp.get("updated", 0))
        new_last = max(b["ts"] for b in closed)
        checkpoint.save(symbol, timeframe, new_last)
        result["checkpoint"] = new_last.isoformat()
    return result
