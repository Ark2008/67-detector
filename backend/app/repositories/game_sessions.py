from typing import Protocol

from sqlalchemy import func, insert, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import GameSession


class GameSessionRepository(Protocol):
    async def create(self, nickname: str) -> int: ...

    async def increment_score(self, session_id: int) -> int: ...

    async def finish(self, session_id: int) -> None: ...


class PostgresGameSessionRepository:
    """Каждая операция — отдельная короткая транзакция.

    WebSocket живёт долго, поэтому соединение с БД не держится всё подключение.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def create(self, nickname: str) -> int:
        stmt = insert(GameSession).values(nickname=nickname).returning(GameSession.id)
        async with self._session_factory.begin() as session:
            return (await session.execute(stmt)).scalar_one()

    async def increment_score(self, session_id: int) -> int:
        stmt = (
            update(GameSession)
            .where(GameSession.id == session_id)
            .values(score=GameSession.score + 1)
            .returning(GameSession.score)
        )
        async with self._session_factory.begin() as session:
            return (await session.execute(stmt)).scalar_one()

    async def finish(self, session_id: int) -> None:
        stmt = update(GameSession).where(GameSession.id == session_id).values(finished_at=func.now())
        async with self._session_factory.begin() as session:
            await session.execute(stmt)
