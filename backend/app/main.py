from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.infra.http.exception_handlers import register_exception_handlers


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.services.scheduler_service import scheduler_service
    from app.services.copy_trading_service import copy_trading_service

    await scheduler_service.start()
    await copy_trading_service.start()
    yield
    await copy_trading_service.stop()
    await scheduler_service.stop()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Polymarket Intelligence API",
        version="1.0.0",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_exception_handlers(app)

    from app.api import auth
    from app.api import pipeline, markets, decisions, bets
    from app.api import settings as settings_router
    from app.api import prompts, scheduler, dashboard, wallet, stats, system, copy_trading

    # Auth — no security dependency
    app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])

    # All other routers — Depends(get_current_user) on each APIRouter
    app.include_router(pipeline.router, prefix="/api/v1/pipeline", tags=["pipeline"])
    app.include_router(markets.router, prefix="/api/v1/markets", tags=["markets"])
    app.include_router(decisions.router, prefix="/api/v1/decisions", tags=["decisions"])
    app.include_router(bets.router, prefix="/api/v1/bets", tags=["bets"])
    app.include_router(settings_router.router, prefix="/api/v1/settings", tags=["settings"])
    app.include_router(prompts.router, prefix="/api/v1/prompts", tags=["prompts"])
    app.include_router(scheduler.router, prefix="/api/v1/scheduler", tags=["scheduler"])
    app.include_router(dashboard.router, prefix="/api/v1/dashboard", tags=["dashboard"])
    app.include_router(wallet.router, prefix="/api/v1/wallet", tags=["wallet"])
    app.include_router(stats.router, prefix="/api/v1/stats", tags=["stats"])
    app.include_router(system.router, prefix="/api/v1/system", tags=["system"])
    app.include_router(copy_trading.router, prefix="/api/v1/copy-trading", tags=["copy-trading"])

    @app.get("/api/health")
    async def health():
        return {"status": "ok"}

    return app


app = create_app()
