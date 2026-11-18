"""Feature browser — computed live from candles.

This endpoint originally read the `market_features` table, which no service ever
wrote to, so it always returned `{"total": 0, "features": []}`. Rather than keep
a decorative endpoint, the features are now computed on demand from the real
candles with the same causal pipeline the models use (`ml/features.build_features`),
so what you see here is exactly what the models see.

The response is windowed and capped: computing the full history on every request
would be needlessly expensive.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.ml.features import ALL_FEATURES, FEATURE_VERSION, build_features
from app.ml.features_v2 import (
    ALL_FEATURES as ALL_FEATURES_V2,
    FEATURE_VERSION as FEATURE_VERSION_V2,
    build_features_v2,
)
from app.models import User
from app.services.source import active_source
from app.services.training import load_candles
from app.timeutil import ensure_utc

features_router = APIRouter(prefix="/features", tags=["features"])

MAX_WINDOW = 5000


@features_router.get("")
def list_features(
    symbol: str = Query("XAUUSD"),
    limit: int = Query(500, ge=1, le=MAX_WINDOW),
    offset: int = Query(0, ge=0),
    source: str | None = Query(None),
    version: str = Query("v1", pattern="^(v1|v2)$"),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Latest feature rows, computed causally from candles (no stored table)."""
    eff_source = active_source(db, symbol, "M15", source)
    columns = ALL_FEATURES_V2 if version == "v2" else ALL_FEATURES
    feature_version = FEATURE_VERSION_V2 if version == "v2" else FEATURE_VERSION
    if eff_source is None:
        return {
            "total": 0,
            "feature_version": feature_version,
            "source": None,
            "columns": columns,
            "features": [],
            "note": "Chưa có nến M15 — không thể tính feature.",
        }

    df_m5, df_m15, df_h1 = load_candles(
        db,
        symbol,
        m5_limit=20_000 if version == "v2" else 8000,
        m15_limit=20_000 if version == "v2" else 6000,
        h1_limit=8_000 if version == "v2" else 3000,
        source=eff_source,
    )
    try:
        feats = (
            build_features_v2(df_m5, df_m15, df_h1)
            if version == "v2"
            else build_features(df_m5, df_m15, df_h1)
        )
    except ValueError as e:
        raise HTTPException(400, str(e))

    total = len(feats)
    window = feats.iloc[max(0, total - offset - limit) : total - offset] if offset < total else feats.iloc[0:0]
    rows = window.tail(limit)

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "feature_version": feature_version,
        "source": eff_source,
        "columns": columns,
        "features": [
            {
                "ts": ensure_utc(ts).isoformat(),
                **{c: (None if __import__("math").isnan(float(v)) else round(float(v), 6)) for c, v in row.items()},
            }
            for ts, row in rows.iterrows()
        ],
        "note": (
            f"Feature {feature_version} được tính trực tiếp từ nến bằng pipeline causal "
            "(không nhìn tương lai). Bảng market_features không còn được dùng."
        ),
    }
