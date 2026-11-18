"""Central configuration — single source of truth (env prefix GMRAI_)."""
import logging
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger("gmrai.config")

# Placeholders shipped in old templates. They must never authenticate anything.
WEAK_SECRETS = {
    "",
    "dev-secret-change-me-in-production",
    "dev-ingest-key-change-me",
    "change-me",
    "admin-change-me",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GMRAI_", env_file=".env", extra="ignore")

    # Core
    database_url: str = "sqlite:///./gmrai.db"
    artifact_dir: str = "./artifacts"
    auto_create_tables: bool = True
    auto_migrate: bool = False

    # Security — no usable defaults: values come from .env / environment.
    secret_key: str = ""
    access_token_expire_minutes: int = 720
    api_key: str = ""
    admin_username: str = "admin"
    admin_password: str = ""
    allow_weak_secrets: bool = False
    login_rate_limit: str = "5/minute"
    password_change_rate_limit: str = "5/minute"

    # CORS (comma separated)
    cors_origins: str = "http://localhost:3000,http://localhost:8000"

    # Telegram notifications (leave empty to disable)
    telegram_enabled: bool = False
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    # How often the scheduler *checks* for a new signal. The actual send rate is
    # dictated by `telegram_min_bar_seconds` (one message per closed bar max),
    # so a short check interval costs nothing and keeps the alert snappy.
    telegram_interval_seconds: int = 30
    # Minimum spacing between two signal messages = the decision timeframe.
    # 900s = M15, matching the MT5 chart the models are trained on. This is the
    # real throttle: at most one alert per closed M15 candle.
    telegram_min_bar_seconds: int = 900
    # An alert is only meaningful while the next bar is still forming. Backfill
    # can label a candle hours after it closed; alerting on that would announce
    # stale history as breaking news. 1800s = 2 M15 bars of grace.
    telegram_max_bar_age_seconds: int = 1800
    # Telegram renders message times in the phone's timezone, but everything in
    # this system is UTC. The message includes both so the two views cannot be
    # confused. +7 = Vietnam; set to None/0 to omit the local line.
    telegram_local_offset_hours: int = 7

    # Data retention (days). 0 disables pruning for that table.
    # History runs/bars are never pruned unless retention_history_runs is set:
    # they are the analysed dataset, not operational noise.
    retention_system_log_days: int = 30
    retention_telegram_days: int = 90
    retention_sync_log_days: int = 30
    retention_quality_days: int = 90
    retention_jobs_days: int = 14
    retention_forecast_days: int = 365
    retention_predictions_days: int = 365
    retention_history_runs: int = 0
    retention_interval_seconds: int = 86400

    # Data freshness thresholds (minutes)
    max_age_m5_minutes: int = 30
    max_age_m15_minutes: int = 60
    max_age_h1_minutes: int = 240

    # Automation
    automation_enabled: bool = True
    sync_check_interval_seconds: int = 300
    # Catch-up for bars that closed while the app was down. The live path only
    # scores the newest candle, so without this a restart leaves unlabelled bars.
    backfill_interval_seconds: int = 300
    retrain_check_interval_seconds: int = 600
    min_new_candles_for_retrain: int = 200

    # Model defaults
    hmm_n_states: int = 5
    hmm_n_init: int = 10
    hmm_seed: int = 42
    train_fraction: float = 0.70
    val_fraction: float = 0.15
    rf_horizon: int = 12
    rf_up_threshold_atr: float = 0.75
    approve_min_f1: float = 0.55
    approve_max_false_trend_rate: float = 0.25
    approve_min_segment_accuracy: float = 0.45
    approve_min_trend_segments: int = 20

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def weak_secrets(self) -> list[str]:
        """Names of security settings still empty or set to a template placeholder."""
        bad = []
        if self.secret_key in WEAK_SECRETS or len(self.secret_key) < 32:
            bad.append("GMRAI_SECRET_KEY")
        if self.api_key in WEAK_SECRETS:
            bad.append("GMRAI_API_KEY")
        if self.admin_password in WEAK_SECRETS:
            bad.append("GMRAI_ADMIN_PASSWORD")
        return bad

    def assert_secure(self) -> None:
        """Refuse to start with placeholder secrets unless explicitly allowed.

        `GMRAI_ALLOW_WEAK_SECRETS=true` exists only for throwaway local runs; a
        deployment must rotate secrets with `python -m scripts.rotate_secrets`."""
        bad = self.weak_secrets
        if not bad or self.allow_weak_secrets:
            if bad:
                logger.warning(
                    "Weak/insecure secrets in use (%s) — allowed by GMRAI_ALLOW_WEAK_SECRETS",
                    ", ".join(bad),
                )
            return
        raise RuntimeError(
            "Refusing to start: insecure security configuration ("
            + ", ".join(bad)
            + "). Run `python -m scripts.rotate_secrets` to generate real values, "
            "or set GMRAI_ALLOW_WEAK_SECRETS=true for a throwaway local run."
        )

    def max_age_minutes(self, timeframe: str) -> int:
        return {
            "M5": self.max_age_m5_minutes,
            "M15": self.max_age_m15_minutes,
            "H1": self.max_age_h1_minutes,
        }.get(timeframe, self.max_age_m15_minutes)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
