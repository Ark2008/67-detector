import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from app.models import SessionStatus
from app.repositories.game import GestureData, PlayerData, RatingRow, SessionData


class InMemoryGameRepository:
    """Хранит данные в памяти, чтобы тесты REST и WebSocket не требовали PostgreSQL."""

    def __init__(self) -> None:
        self.players: dict[uuid.UUID, PlayerData] = {}
        self.sessions: dict[uuid.UUID, SessionData] = {}
        self.gesture_events: list[tuple[uuid.UUID, datetime]] = []
        self.touch_count = 0

    async def get_or_create_player(self, name: str) -> tuple[PlayerData, bool]:
        for player in self.players.values():
            if player.name.lower() == name.lower():
                return player, False
        player = PlayerData(id=uuid.uuid4(), name=name, created_at=_now())
        self.players[player.id] = player
        return player, True

    async def create_session(self, player_id: uuid.UUID) -> SessionData | None:
        if player_id not in self.players:
            return None
        now = _now()
        session = SessionData(
            id=uuid.uuid4(),
            player_id=player_id,
            status=SessionStatus.ACTIVE,
            score=0,
            started_at=now,
            ended_at=None,
            last_activity_at=now,
        )
        self.sessions[session.id] = session
        return session

    async def get_session(self, session_id: uuid.UUID) -> SessionData | None:
        return self.sessions.get(session_id)

    async def stop_session(self, session_id: uuid.UUID) -> SessionData | None:
        session = self.sessions.get(session_id)
        if session is not None and session.is_active:
            session = replace(session, status=SessionStatus.STOPPED, ended_at=_now())
            self.sessions[session_id] = session
        return session

    async def register_gesture(self, session_id: uuid.UUID) -> GestureData | None:
        session = self.sessions.get(session_id)
        if session is None or not session.is_active:
            return None
        now = _now()
        self.sessions[session_id] = replace(session, score=session.score + 1, last_activity_at=now)
        self.gesture_events.append((session_id, now))
        return GestureData(score=session.score + 1, detected_at=now)

    async def touch_session(self, session_id: uuid.UUID) -> bool:
        session = self.sessions.get(session_id)
        if session is None or not session.is_active:
            return False
        self.touch_count += 1
        self.sessions[session_id] = replace(session, last_activity_at=_now())
        return True

    async def close_timed_out_sessions(self, timeout_seconds: float) -> list[SessionData]:
        deadline = _now() - timedelta(seconds=timeout_seconds)
        closed = [
            replace(session, status=SessionStatus.TIMEOUT, ended_at=session.last_activity_at)
            for session in self.sessions.values()
            if session.is_active and session.last_activity_at < deadline
        ]
        self.sessions.update({session.id: session for session in closed})
        return closed

    async def get_ratings(self) -> list[RatingRow]:
        rows = []
        for player in self.players.values():
            scores = [
                session.score
                for session in self.sessions.values()
                if session.player_id == player.id and not session.is_active
            ]
            rows.append(
                RatingRow(
                    player_id=player.id,
                    name=player.name,
                    total_score=sum(scores),
                    best_session_score=max(scores, default=0),
                )
            )
        return sorted(rows, key=lambda row: (-row.total_score, -row.best_session_score, row.name))

    # Помощники тестов: подготовить данные в обход API.

    def add_player(self, name: str) -> PlayerData:
        player = PlayerData(id=uuid.uuid4(), name=name, created_at=_now())
        self.players[player.id] = player
        return player

    def add_session(
        self,
        player_id: uuid.UUID,
        *,
        score: int = 0,
        status: SessionStatus = SessionStatus.ACTIVE,
        idle_seconds: float = 0,
    ) -> SessionData:
        """Сессия с заданным счётом и статусом, последняя активность — idle_seconds назад."""
        last_activity_at = _now() - timedelta(seconds=idle_seconds)
        session = SessionData(
            id=uuid.uuid4(),
            player_id=player_id,
            status=status,
            score=score,
            started_at=last_activity_at,
            ended_at=None if status == SessionStatus.ACTIVE else last_activity_at,
            last_activity_at=last_activity_at,
        )
        self.sessions[session.id] = session
        return session


class FakeClock:
    """Часы сервера для тестов cooldown: время идёт только по команде."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _now() -> datetime:
    return datetime.now(UTC)
