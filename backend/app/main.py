import asyncio
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.api.players import router as players_router
from app.api.ratings import router as ratings_router
from app.api.sessions import router as sessions_router
from app.config import Settings, settings
from app.db import engine, session_factory
from app.repositories.game import GameRepository, PostgresGameRepository
from app.services.connections import ConnectionRegistry
from app.services.game import Clock
from app.services.timeouts import run_timeout_watcher
from app.services.vision import DetectGesture, default_detect_gesture
from app.websocket.sessions import router as sessions_websocket_router


def create_app(
    app_settings: Settings = settings,
    repository: GameRepository | None = None,
    detect_gesture: DetectGesture = default_detect_gesture,
    clock: Clock = time.monotonic,
) -> FastAPI:
    """Собрать приложение. Параметры нужны тестам, чтобы подменить БД, CV и часы."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        watcher = asyncio.create_task(
            run_timeout_watcher(
                app.state.repository,
                app.state.registry,
                app_settings.session_timeout_seconds,
                app_settings.timeout_check_interval_seconds,
            )
        )
        yield
        watcher.cancel()
        with suppress(asyncio.CancelledError):
            await watcher
        await engine.dispose()

    app = FastAPI(title="Six-seven", lifespan=lifespan)
    app.state.settings = app_settings
    app.state.repository = repository or PostgresGameRepository(session_factory)
    app.state.registry = ConnectionRegistry()
    app.state.detect_gesture = detect_gesture
    app.state.clock = clock

    app.add_middleware(
        CORSMiddleware, allow_origins=app_settings.cors_origins, allow_methods=["*"], allow_headers=["*"]
    )
    app.include_router(health_router)
    app.include_router(players_router)
    app.include_router(sessions_router)
    app.include_router(ratings_router)
    app.include_router(sessions_websocket_router)
    return app


app = create_app()
