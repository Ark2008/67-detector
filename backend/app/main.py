from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.health import router as health_router
from app.db import engine
from app.websocket.game import router as game_websocket_router


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    await engine.dispose()


app = FastAPI(title="Six-seven", lifespan=lifespan)
app.include_router(health_router)
app.include_router(game_websocket_router)
