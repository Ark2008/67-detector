"""Доступ к данным игры: игроки, сессии, засчитанные жесты, рейтинг. Схема — docs/db-schema.md."""

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from sqlalchemy import and_, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import GameSession, GestureEvent, Player, SessionStatus

FINISHED_STATUSES = (SessionStatus.STOPPED.value, SessionStatus.TIMEOUT.value)


@dataclass(frozen=True, slots=True)
class PlayerData:
    id: uuid.UUID
    name: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class SessionData:
    id: uuid.UUID
    player_id: uuid.UUID
    status: SessionStatus
    score: int
    started_at: datetime
    ended_at: datetime | None
    last_activity_at: datetime

    @property
    def is_active(self) -> bool:
        return self.status == SessionStatus.ACTIVE


@dataclass(frozen=True, slots=True)
class GestureData:
    """Засчитанный жест: новый счёт сессии и момент записи события."""

    score: int
    detected_at: datetime


@dataclass(frozen=True, slots=True)
class RatingRow:
    player_id: uuid.UUID
    name: str
    total_score: int
    best_session_score: int


class GameRepository(Protocol):
    async def get_or_create_player(self, name: str) -> tuple[PlayerData, bool]:
        """Найти игрока по имени без учёта регистра или создать. Второй элемент — создан ли новый."""
        ...

    async def create_session(self, player_id: uuid.UUID) -> SessionData | None:
        """Создать активную сессию. None — игрока с таким id нет."""
        ...

    async def get_session(self, session_id: uuid.UUID) -> SessionData | None: ...

    async def stop_session(self, session_id: uuid.UUID) -> SessionData | None:
        """Перевести активную сессию в stopped. Для уже завершённой вернуть её как есть. None — нет такой."""
        ...

    async def register_gesture(self, session_id: uuid.UUID) -> GestureData | None:
        """Засчитать жест: score += 1 и строка в gesture_events. None — сессия не активна."""
        ...

    async def touch_session(self, session_id: uuid.UUID) -> bool:
        """Обновить last_activity_at. False — сессия не активна."""
        ...

    async def close_timed_out_sessions(self, timeout_seconds: float) -> list[SessionData]:
        """Перевести в timeout активные сессии без активности дольше timeout_seconds и вернуть их."""
        ...

    async def get_ratings(self) -> list[RatingRow]:
        """Рейтинг по завершённым сессиям, по убыванию суммарного счёта."""
        ...


class PostgresGameRepository:
    """Каждая операция — отдельная короткая транзакция.

    WebSocket живёт долго, поэтому соединение с БД не держится всё подключение.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def get_or_create_player(self, name: str) -> tuple[PlayerData, bool]:
        # Конфликт по уникальному индексу lower(name) — игрок уже есть, тогда читаем его.
        insert_stmt = insert(Player).values(name=name).on_conflict_do_nothing().returning(Player)
        select_stmt = select(Player).where(func.lower(Player.name) == func.lower(name))
        async with self._session_factory.begin() as db:
            player = (await db.execute(insert_stmt)).scalar_one_or_none()
            created = player is not None
            if player is None:
                player = (await db.execute(select_stmt)).scalar_one()
            return _player_data(player), created

    async def create_session(self, player_id: uuid.UUID) -> SessionData | None:
        stmt = insert(GameSession).values(player_id=player_id).returning(GameSession)
        try:
            async with self._session_factory.begin() as db:
                return _session_data((await db.execute(stmt)).scalar_one())
        except IntegrityError:  # нарушен внешний ключ: игрока нет
            return None

    async def get_session(self, session_id: uuid.UUID) -> SessionData | None:
        async with self._session_factory() as db:
            session = await db.get(GameSession, session_id)
            return None if session is None else _session_data(session)

    async def stop_session(self, session_id: uuid.UUID) -> SessionData | None:
        # Идемпотентность: строка меняется, только если сессия ещё активна.
        stmt = (
            update(GameSession)
            .where(GameSession.id == session_id, GameSession.status == SessionStatus.ACTIVE.value)
            .values(status=SessionStatus.STOPPED.value, ended_at=func.now())
            .returning(GameSession)
        )
        async with self._session_factory.begin() as db:
            session = (await db.execute(stmt)).scalar_one_or_none()
            if session is None:
                session = await db.get(GameSession, session_id)
            return None if session is None else _session_data(session)

    async def register_gesture(self, session_id: uuid.UUID) -> GestureData | None:
        score_stmt = (
            update(GameSession)
            .where(GameSession.id == session_id, GameSession.status == SessionStatus.ACTIVE.value)
            .values(score=GameSession.score + 1, last_activity_at=func.now())
            .returning(GameSession.score)
        )
        event_stmt = insert(GestureEvent).values(session_id=session_id).returning(GestureEvent.detected_at)
        async with self._session_factory.begin() as db:
            score = (await db.execute(score_stmt)).scalar_one_or_none()
            if score is None:
                return None
            detected_at = (await db.execute(event_stmt)).scalar_one()
            return GestureData(score=score, detected_at=detected_at)

    async def touch_session(self, session_id: uuid.UUID) -> bool:
        stmt = (
            update(GameSession)
            .where(GameSession.id == session_id, GameSession.status == SessionStatus.ACTIVE.value)
            .values(last_activity_at=func.now())
            .returning(GameSession.id)
        )
        async with self._session_factory.begin() as db:
            return (await db.execute(stmt)).scalar_one_or_none() is not None

    async def close_timed_out_sessions(self, timeout_seconds: float) -> list[SessionData]:
        stmt = (
            update(GameSession)
            .where(
                GameSession.status == SessionStatus.ACTIVE.value,
                GameSession.last_activity_at < func.now() - timedelta(seconds=timeout_seconds),
            )
            # ended_at = last_activity_at, а не now(): время сессии не растягивается на ожидание таймаута.
            .values(status=SessionStatus.TIMEOUT.value, ended_at=GameSession.last_activity_at)
            .returning(GameSession)
        )
        async with self._session_factory.begin() as db:
            return [_session_data(session) for session in (await db.execute(stmt)).scalars()]

    async def get_ratings(self) -> list[RatingRow]:
        total_score = func.coalesce(func.sum(GameSession.score), 0).label("total_score")
        best_session_score = func.coalesce(func.max(GameSession.score), 0).label("best_session_score")
        stmt = (
            select(Player.id, Player.name, total_score, best_session_score)
            # Активные сессии в рейтинг не входят — только завершённые.
            .outerjoin(
                GameSession,
                and_(GameSession.player_id == Player.id, GameSession.status.in_(FINISHED_STATUSES)),
            )
            .group_by(Player.id, Player.name)
            .order_by(total_score.desc(), best_session_score.desc(), Player.name)
        )
        async with self._session_factory() as db:
            return [
                RatingRow(
                    player_id=row.id,
                    name=row.name,
                    total_score=row.total_score,
                    best_session_score=row.best_session_score,
                )
                for row in await db.execute(stmt)
            ]


def _player_data(player: Player) -> PlayerData:
    return PlayerData(id=player.id, name=player.name, created_at=player.created_at)


def _session_data(session: GameSession) -> SessionData:
    return SessionData(
        id=session.id,
        player_id=session.player_id,
        status=SessionStatus(session.status),
        score=session.score,
        started_at=session.started_at,
        ended_at=session.ended_at,
        last_activity_at=session.last_activity_at,
    )
