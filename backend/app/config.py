"""Central configuration — single source of truth (env prefix GMRAI_)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GMRAI_", env_file=".env", extra="ignore")

    # Core
    database_url: str = "sqlite:///./gmrai.db"
    artifact_dir: str = "./artifacts"
    auto_create_tables: bool = True
    auto_migrate: bool = False

    # Security
    secret_key: str = "dev-secret-change-me-in-production"
    access_token_expire_minutes: int = 720
    api_key: str = "dev-ingest-key-change-me"
    admin_username: str = "admin"
    admin_password: str = "admin-change-me"
    login_rate_limit: str = "5/minute"

    # CORS (comma separated)
    cors_origins: str = "http://localhost:3000,http://localhost:8000"

    # Data freshness thresholds (minutes)
    max_age_m5_minutes: int = 30
    max_age_m15_minutes: int = 60
    max_age_h1_minutes: int = 240

    # Automation
    automation_enabled: bool = True
    sync_check_interval_seconds: int = 300
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

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

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
