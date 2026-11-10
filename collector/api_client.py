"""HTTPS ingestion API client — retries with exponential backoff, timeouts.

Never retries 4xx (permanent errors); retries 5xx/connection errors.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any

import requests

logger = logging.getLogger("gmrai.collector.api")

MAX_ATTEMPTS = 5
BASE_DELAY_SECONDS = 5.0


class ApiClientError(RuntimeError):
    pass


def _json_safe(candle: dict) -> dict:
    """Convert datetime values to ISO strings (JSON cannot carry datetimes)."""
    out = dict(candle)
    for key in ("ts",):
        value = out.get(key)
        if isinstance(value, datetime):
            out[key] = value.isoformat()
    return out


class ApiClient:
    def __init__(self, base_url: str, api_key: str, collector_id: str, timeout: int = 60):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.collector_id = collector_id
        self.timeout = timeout

    def send_candles(self, timeframe: str, candles: list[dict]) -> dict:
        """POST /api/v1/ingest/candles with retry/backoff."""
        url = f"{self.base_url}/api/v1/ingest/candles"
        headers = {
            "X-API-Key": self.api_key,
            "X-Collector-ID": self.collector_id,
            "Content-Type": "application/json",
        }
        payload = {"candles": [_json_safe(c) for c in candles]}
        last_err: Exception | None = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                resp = requests.post(
                    url, json=payload, headers=headers, timeout=self.timeout, params={"timeframe": timeframe}
                )
                if resp.status_code == 200:
                    return resp.json()
                if 400 <= resp.status_code < 500:
                    raise ApiClientError(
                        f"Permanent ingestion error {resp.status_code}: {resp.text[:300]}"
                    )
                last_err = ApiClientError(f"Ingestion HTTP {resp.status_code}: {resp.text[:200]}")
            except requests.RequestException as e:
                last_err = e
            if attempt < MAX_ATTEMPTS:
                delay = BASE_DELAY_SECONDS * (2 ** (attempt - 1))
                logger.warning("send_candles attempt %d failed (%s); retry in %.0fs", attempt, last_err, delay)
                time.sleep(delay)
        raise ApiClientError(f"Ingestion failed after {MAX_ATTEMPTS} attempts: {last_err}")
