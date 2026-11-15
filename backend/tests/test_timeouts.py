from fastapi import status
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.models import SessionStatus
from app.repositories.game import PlayerData
from app.services.connections import Connection, ConnectionRegistry
from app.services.timeouts import close_timed_out_sessions
from tests.fakes import InMemoryGameRepository
from tests.test_session_websocket import assert_closed, url


class FakeWebSocket:
    """Записывает, что сервер отправил в сокет и с каким кодом его закрыл."""

    def __init__(self) -> None:
        self.sent: list[str] = []
        self.close_code: int | None = None

    async def send_text(self, text: str) -> None:
        self.sent.append(text)

    async def close(self, code: int) -> None:
        self.close_code = code


async def test_idle_session_is_closed_by_timeout(
    repository: InMemoryGameRepository, player: PlayerData
) -> None:
    idle = repository.add_session(player.id, score=3, idle_seconds=31)
    fresh = repository.add_session(player.id, idle_seconds=29)
    stopped = repository.add_session(player.id, status=SessionStatus.STOPPED, idle_seconds=100)

    closed = await close_timed_out_sessions(repository, ConnectionRegistry(), timeout_seconds=30)

    assert closed == 1
    timed_out = repository.sessions[idle.id]
    assert timed_out.status == SessionStatus.TIMEOUT
    assert timed_out.score == 3
    # ended_at — момент последней активности, а не срабатывания таймаута.
    assert timed_out.ended_at == idle.last_activity_at
    assert repository.sessions[fresh.id].status == SessionStatus.ACTIVE
    assert repository.sessions[stopped.id] == stopped


async def test_timeout_notifies_open_socket(repository: InMemoryGameRepository, player: PlayerData) -> None:
    idle = repository.add_session(player.id, score=7, idle_seconds=31)
    websocket = FakeWebSocket()
    registry = ConnectionRegistry()
    registry.register(idle.id, Connection(websocket))  # type: ignore[arg-type]

    await close_timed_out_sessions(repository, registry, timeout_seconds=30)

    ended_at = idle.last_activity_at.isoformat().replace("+00:00", "Z")
    assert websocket.sent == [
        f'{{"type":"session_state","status":"timeout","score":7,"ended_at":"{ended_at}"}}'
    ]
    assert websocket.close_code == status.WS_1000_NORMAL_CLOSURE


def test_background_task_closes_silent_session(
    repository: InMemoryGameRepository, player: PlayerData
) -> None:
    """Сокет открыт, но кадров нет: фоновая задача сама закрывает сессию и сокет."""
    session = repository.add_session(player.id)
    app = create_app(
        Settings(_env_file=None, session_timeout_seconds=0.2, timeout_check_interval_seconds=0.05),
        repository=repository,
    )

    with TestClient(app) as client, client.websocket_connect(url(session.id)) as ws:
        ws.receive_json()  # session_ready
        event = ws.receive_json()
        assert_closed(ws, status.WS_1000_NORMAL_CLOSURE)

    assert event["type"] == "session_state"
    assert event["status"] == "timeout"
    assert event["score"] == 0
    assert repository.sessions[session.id].status == SessionStatus.TIMEOUT
