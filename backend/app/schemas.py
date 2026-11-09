"""Pydantic request schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class CandleIn(BaseModel):
    symbol: str = "XAUUSD"
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    tick_volume: int = 0
    spread: int | None = None
    real_volume: int | None = None
    source: str = "ftmo_mt5"


class CandleBatchIn(BaseModel):
    candles: list[CandleIn] = Field(min_length=1, max_length=10_000)


class LoginIn(BaseModel):
    username: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    role: str


class TrainingConfigIn(BaseModel):
    hmm_n_states: int = Field(default=5, ge=2, le=10)
    hmm_n_init: int = Field(default=10, ge=1, le=50)
    seed: int = 42
    train_frac: float = Field(default=0.70, gt=0.3, lt=0.9)
    val_frac: float = Field(default=0.15, gt=0.01, lt=0.4)
    rf_horizon: int = Field(default=12, ge=2, le=96)
    up_threshold_atr: float = Field(default=0.75, gt=0.0, le=5.0)
    weight_hmm: float = Field(default=0.5, ge=0.0, le=1.0)


class BacktestConfigIn(BaseModel):
    name: str = ""
    initial_train: int = Field(default=5000, ge=500)
    test_size: int = Field(default=500, ge=100)
    embargo: int = Field(default=12, ge=0, le=200)
    hmm_n_states: int = Field(default=5, ge=2, le=10)
    hmm_n_init: int = Field(default=10, ge=1, le=50)
    rf_horizon: int = Field(default=12, ge=2, le=96)
    up_threshold_atr: float = Field(default=0.75, gt=0.0, le=5.0)
    cost_usd: float = Field(default=30.0, ge=0.0)
    max_hold: int = Field(default=24, ge=1, le=500)


class StatusChangeIn(BaseModel):
    status: Literal["candidate", "approved", "rejected", "archived"]
    force: bool = False

    @field_validator("status")
    @classmethod
    def _check(cls, v):
        return v
