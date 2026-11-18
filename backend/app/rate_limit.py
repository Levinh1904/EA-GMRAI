"""Shared rate limiter.

The limiter used to be defined inside `routers/auth.py`, so only the two auth
routes could be decorated without an awkward cross-import. It lives here so any
router can import it without creating an import cycle.

Limits are deliberately per-route rather than one global bucket: an ingestion
burst must not lock an operator out of the dashboard, and vice versa.
"""
from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

# Expensive read endpoints (they materialise whole history runs).
HISTORY_STATS_LIMIT = "120/minute"
# Bulk writes from the collector.
INGEST_LIMIT = "120/minute"
# Admin-triggered heavy jobs (training/backtest/ONNX export).
HEAVY_JOB_LIMIT = "10/minute"
# Anything that sends to a third party.
OUTBOUND_LIMIT = "20/minute"
