from fastapi import APIRouter

from app.routers import admin, jobs
from app.routers.auth import auth_router, limiter
from app.routers.backtest import backtest_router
from app.routers.features import features_router
from app.routers.history import history_router
from app.routers.ingest import ingest_router
from app.routers.market import market_router
from app.routers.notifications import forecast_router, telegram_router
from app.routers.onnx import onnx_router
from app.routers.quality import quality_router
from app.routers.regime import regime_router
from app.routers.registry import registry_router
from app.routers.reference import reference_router
from app.routers.stats import stats_router, system_router
from app.routers.trade_model import trade_model_router
from app.routers.training import training_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth_router)
api_router.include_router(ingest_router)
api_router.include_router(market_router)
api_router.include_router(features_router)
api_router.include_router(quality_router)
api_router.include_router(training_router)
api_router.include_router(backtest_router)
api_router.include_router(registry_router)
api_router.include_router(onnx_router)
api_router.include_router(regime_router)
api_router.include_router(trade_model_router)
api_router.include_router(reference_router)
api_router.include_router(history_router)
api_router.include_router(stats_router)
api_router.include_router(system_router)
api_router.include_router(telegram_router)
api_router.include_router(forecast_router)
api_router.include_router(admin.users_router)
api_router.include_router(admin.keys_router)
api_router.include_router(jobs.jobs_router)

__all__ = ["api_router", "limiter"]
