from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.repositories.game import PlayerData, SessionData
from tests.fakes import FakeClock, InMemoryGameRepository


@pytest.fixture
def repository() -> InMemoryGameRepository:
    return InMemoryGameRepository()


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def app_settings() -> Settings:
    # Значения по умолчанию, без чтения .env; фоновая задача таймаутов в тестах молчит.
    return Settings(_env_file=None, timeout_check_interval_seconds=3600)


@pytest.fixture
def app(repository: InMemoryGameRepository, clock: FakeClock, app_settings: Settings) -> FastAPI:
    return create_app(app_settings, repository=repository, clock=clock)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def player(repository: InMemoryGameRepository) -> PlayerData:
    return repository.add_player("Петя")


@pytest.fixture
def session(repository: InMemoryGameRepository, player: PlayerData) -> SessionData:
    """Активная сессия, к которой можно подключаться по WebSocket."""
    return repository.add_session(player.id)
