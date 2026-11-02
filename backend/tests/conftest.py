from collections.abc import Iterator
from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_game_session_repository
from app.main import app


@dataclass(slots=True)
class StoredSession:
    nickname: str
    score: int = 0
    finished: bool = False


class InMemoryGameSessionRepository:
    """Хранит сессии в памяти, чтобы тесты WebSocket не требовали PostgreSQL."""

    def __init__(self) -> None:
        self.sessions: dict[int, StoredSession] = {}

    async def create(self, nickname: str) -> int:
        session_id = len(self.sessions) + 1
        self.sessions[session_id] = StoredSession(nickname)
        return session_id

    async def increment_score(self, session_id: int) -> int:
        session = self.sessions[session_id]
        session.score += 1
        return session.score

    async def finish(self, session_id: int) -> None:
        self.sessions[session_id].finished = True


@pytest.fixture
def repository() -> InMemoryGameSessionRepository:
    return InMemoryGameSessionRepository()


@pytest.fixture
def client(repository: InMemoryGameSessionRepository) -> Iterator[TestClient]:
    app.dependency_overrides[get_game_session_repository] = lambda: repository
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
