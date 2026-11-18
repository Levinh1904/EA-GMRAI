"""In-process TTL cache for the expensive history statistics.

Why: every `/history/runs/{id}/stats/*` request re-loaded *all* bars or segments
of the run from SQLite (up to ~80k rows with several JSON columns) and recomputed
everything. With 13 tabs, clicking through a run re-materialised the same data
dozen of times.

Safety of caching: a history run is immutable once `status == "done"` — bars,
segments and outcomes are written once, and a regenerate creates a NEW run id.
So the cache key `(run_id, kind, params)` can never return stale data for a run
that is still being written; runs in other states are not cached at all.

The cache is per-process and bounded, so a multi-worker deployment simply gets
more misses, never wrong answers.
"""
from __future__ import annotations

import threading
import time
from collections import OrderedDict
from typing import Any, Callable

MAX_ENTRIES = 64
DEFAULT_TTL = 300.0  # 5 minutes — runs are immutable, so this is conservative

_lock = threading.Lock()
_store: OrderedDict[tuple, tuple[float, Any]] = OrderedDict()
_stats = {"hits": 0, "misses": 0, "evictions": 0}


def get_or_compute(key: tuple, compute: Callable[[], Any], ttl: float = DEFAULT_TTL) -> Any:
    """Return a cached value for `key`, computing it on miss."""
    now = time.monotonic()
    with _lock:
        entry = _store.get(key)
        if entry is not None:
            ts, value = entry
            if now - ts < ttl:
                _stats["hits"] += 1
                _store.move_to_end(key)
                return value
            # Expired: drop and recompute.
            del _store[key]

    # Compute outside the lock: a slow stats call must not block other keys.
    value = compute()

    with _lock:
        _stats["misses"] += 1
        _store[key] = (now, value)
        _store.move_to_end(key)
        while len(_store) > MAX_ENTRIES:
            _store.popitem(last=False)
            _stats["evictions"] += 1
    return value


def invalidate(run_id: int | None = None) -> int:
    """Drop cached entries for one run (or everything). Returns entries removed.

    Invalidating everything also resets the hit/miss counters: the counters only
    describe the current cache generation, so a full clear starts a fresh
    measurement window.
    """
    with _lock:
        if run_id is None:
            n = len(_store)
            _store.clear()
            _stats["hits"] = 0
            _stats["misses"] = 0
            _stats["evictions"] = 0
            return n
        doomed = [k for k in _store if k and k[0] == run_id]
        for k in doomed:
            del _store[k]
        return len(doomed)


def info() -> dict:
    with _lock:
        total = _stats["hits"] + _stats["misses"]
        return {
            "entries": len(_store),
            "max_entries": MAX_ENTRIES,
            "ttl_seconds": DEFAULT_TTL,
            **_stats,
            "hit_rate_pct": round(100.0 * _stats["hits"] / total, 1) if total else None,
        }
