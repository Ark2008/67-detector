"""Интеграционный тест с настоящим PostgreSQL.

Пропускается, если БД недоступна или не применены миграции (`alembic upgrade head`).
"""

from collections.abc import AsyncIterator

import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.models import GameSession
from app.repositories.game_sessions import PostgresGameSessionRepository


@pytest.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(settings.database_url)
    try:
        async with engine.connect() as connection:
            await connection.execute(select(GameSession.id).limit(1))
    except (OSError, SQLAlchemyError) as exc:
        await engine.dispose()
        pytest.skip(f"PostgreSQL недоступен или не применены миграции: {exc}")

    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def test_score_is_saved_to_postgres(session_factory: async_sessionmaker[AsyncSession]) -> None:
    repository = PostgresGameSessionRepository(session_factory)
    session_id = await repository.create("pytest")
    try:
        assert await repository.increment_score(session_id) == 1
        assert await repository.increment_score(session_id) == 2
        await repository.finish(session_id)

        async with session_factory() as session:
            game_session = await session.get(GameSession, session_id)
        assert game_session is not None
        assert game_session.score == 2
        assert game_session.finished_at is not None
    finally:
        async with session_factory.begin() as session:
            await session.execute(delete(GameSession).where(GameSession.id == session_id))
