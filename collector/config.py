"""Collector configuration — loaded from environment/.env (local machine only)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    pass


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


@dataclass
class CollectorConfig:
    # MT5
    mt5_path: str = field(default_factory=lambda: _env("MT5_PATH", ""))
    mt5_login: int | None = None
    mt5_password: str = ""
    mt5_server: str = ""
    symbol: str = _env("MT5_SYMBOL", "XAUUSD")
    timeframes: tuple[str, ...] = ("M5", "M15", "H1")

    # Ingestion API
    api_url: str = _env("GMRAI_INGEST_URL", "https://your-server.example.com/api/v1")
    api_key: str = _env("GMRAI_API_KEY", "change-me")
    collector_id: str = _env("GMRAI_COLLECTOR_ID", "windows-pc-01")

    # Sync behavior
    sync_interval_seconds: int = int(_env("GMRAI_SYNC_INTERVAL_SECONDS", "60"))
    resync_bars: int = int(_env("GMRAI_RESYNC_BARS", "50"))
    max_batch: int = int(_env("GMRAI_MAX_BATCH", "5000"))
    history_days: int = int(_env("MT5_HISTORY_DAYS", "365"))

    # Runtime
    checkpoint_dir: str = field(default_factory=lambda: _env("GMRAI_CHECKPOINT_DIR", "./checkpoints"))
    log_dir: str = field(default_factory=lambda: _env("GMRAI_LOG_DIR", "./logs"))
    log_level: str = _env("GMRAI_LOG_LEVEL", "INFO")
    backfill_days: int | None = None

    def __post_init__(self):
        login = os.environ.get("MT5_LOGIN", "")
        if login:
            self.mt5_login = int(login)
        self.mt5_password = os.environ.get("MT5_PASSWORD", "")
        self.mt5_server = os.environ.get("MT5_SERVER", "")


def load_config() -> CollectorConfig:
    return CollectorConfig()
