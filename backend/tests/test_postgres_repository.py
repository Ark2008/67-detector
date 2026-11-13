"""Интеграционные тесты с настоящим PostgreSQL.

Пропускаются, если БД недоступна или не применены миграции (`alembic upgrade head`).
"""

import uuid
from collections.abc import AsyncIterator
from datetime import timedelta

import pytest
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.models import GameSession, GestureEvent, Player, SessionStatus
from app.repositories.game import PlayerData, PostgresGameRepository, SessionData

SessionFactory = async_sessionmaker[AsyncSession]


@pytest.fixture
async def session_factory() -> AsyncIterator[SessionFactory]:
    engine = create_async_engine(settings.database_url)
    try:
        async with engine.connect() as connection:
            await connection.execute(select(GestureEvent.id).limit(1))
    except (OSError, SQLAlchemyError) as exc:
        await engine.dispose()
        pytest.skip(f"PostgreSQL недоступен или не применены миграции: {exc}")

    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture
def repository(session_factory: SessionFactory) -> PostgresGameRepository:
    return PostgresGameRepository(session_factory)


@pytest.fixture
async def make_player(
    repository: PostgresGameRepository, session_factory: SessionFactory
) -> AsyncIterator[callable]:
    """Создаёт игроков с уникальными именами и удаляет их после теста (сессии — каскадом)."""
    player_ids: list[uuid.UUID] = []

    async def create(prefix: str = "pytest") -> PlayerData:
        player, _ = await repository.get_or_create_player(f"{prefix}-{uuid.uuid4().hex[:12]}")
        player_ids.append(player.id)
        return player

    yield create
    async with session_factory.begin() as db:
        await db.execute(delete(Player).where(Player.id.in_(player_ids)))


async def set_idle(session_factory: SessionFactory, session_id: uuid.UUID, seconds: float) -> None:
    """Сдвинуть last_activity_at сессии в прошлое."""
    stmt = (
        update(GameSession)
        .where(GameSession.id == session_id)
        .values(last_activity_at=func.now() - timedelta(seconds=seconds))
    )
    async with session_factory.begin() as db:
        await db.execute(stmt)


async def finished_session(repository: PostgresGameRepository, player: PlayerData, score: int) -> SessionData:
    session = await repository.create_session(player.id)
    for _ in range(score):
        await repository.register_gesture(session.id)
    return await repository.stop_session(session.id)


async def test_player_is_found_by_name_ignoring_case(
    repository: PostgresGameRepository, make_player: callable
) -> None:
    player = await make_player("PyTest-Петя")

    same, created = await repository.get_or_create_player(player.name.upper())

    assert not created
    assert same == player


async def test_player_name_is_unique_ignoring_case(
    session_factory: SessionFactory, make_player: callable
) -> None:
    player = await make_player("pytest")

    with pytest.raises(IntegrityError):
        async with session_factory.begin() as db:
            db.add(Player(name=player.name.upper()))


async def test_session_starts_active_with_zero_score(
    repository: PostgresGameRepository, make_player: callable
) -> None:
    player = await make_player()

    session = await repository.create_session(player.id)

    assert session.status == SessionStatus.ACTIVE
    assert session.score == 0
    assert session.ended_at is None
    assert session.last_activity_at == session.started_at
    assert await repository.get_session(session.id) == session


async def test_session_for_unknown_player_is_not_created(repository: PostgresGameRepository) -> None:
    assert await repository.create_session(uuid.uuid4()) is None
    assert await repository.get_session(uuid.uuid4()) is None


async def test_gesture_increments_score_and_writes_event(
    repository: PostgresGameRepository, session_factory: SessionFactory, make_player: callable
) -> None:
    session = await repository.create_session((await make_player()).id)

    first = await repository.register_gesture(session.id)
    second = await repository.register_gesture(session.id)

    assert (first.score, second.score) == (1, 2)
    saved = await repository.get_session(session.id)
    assert saved.score == 2
    assert saved.last_activity_at == second.detected_at
    async with session_factory() as db:
        events = await db.scalars(
            select(GestureEvent.detected_at)
            .where(GestureEvent.session_id == session.id)
            .order_by(GestureEvent.id)
        )
        assert events.all() == [first.detected_at, second.detected_at]


async def test_stop_is_idempotent(repository: PostgresGameRepository, make_player: callable) -> None:
    session = await repository.create_session((await make_player()).id)
    await repository.register_gesture(session.id)

    stopped = await repository.stop_session(session.id)
    again = await repository.stop_session(session.id)

    assert stopped.status == SessionStatus.STOPPED
    assert stopped.score == 1
    assert stopped.ended_at is not None
    assert again == stopped
    assert await repository.stop_session(uuid.uuid4()) is None


async def test_finished_session_does_not_accept_gestures(
    repository: PostgresGameRepository, session_factory: SessionFactory, make_player: callable
) -> None:
    session = await repository.create_session((await make_player()).id)
    await repository.stop_session(session.id)

    assert await repository.register_gesture(session.id) is None
    assert not await repository.touch_session(session.id)
    assert (await repository.get_session(session.id)).score == 0
    async with session_factory() as db:
        events = await db.scalar(
            select(func.count()).select_from(GestureEvent).where(GestureEvent.session_id == session.id)
        )
        assert events == 0


async def test_touch_updates_last_activity(
    repository: PostgresGameRepository, session_factory: SessionFactory, make_player: callable
) -> None:
    session = await repository.create_session((await make_player()).id)
    await set_idle(session_factory, session.id, seconds=20)

    assert await repository.touch_session(session.id)

    assert (await repository.get_session(session.id)).last_activity_at > session.last_activity_at


async def test_idle_sessions_are_closed_by_timeout(
    repository: PostgresGameRepository, session_factory: SessionFactory, make_player: callable
) -> None:
    player = await make_player()
    idle = await repository.create_session(player.id)
    fresh = await repository.create_session(player.id)
    await repository.register_gesture(idle.id)
    await set_idle(session_factory, idle.id, seconds=31)
    await set_idle(session_factory, fresh.id, seconds=29)
    last_activity_at = (await repository.get_session(idle.id)).last_activity_at

    closed = await repository.close_timed_out_sessions(timeout_seconds=30)

    # В базе разработчика могут быть и другие зависшие сессии — смотрим только на свои.
    assert [session for session in closed if session.player_id == player.id] == [
        await repository.get_session(idle.id)
    ]
    timed_out = await repository.get_session(idle.id)
    assert timed_out.status == SessionStatus.TIMEOUT
    assert timed_out.score == 1
    # ended_at — момент последней активности, а не срабатывания таймаута.
    assert timed_out.ended_at == last_activity_at
    assert (await repository.get_session(fresh.id)).status == SessionStatus.ACTIVE


async def test_ratings_count_only_finished_sessions(
    repository: PostgresGameRepository, session_factory: SessionFactory, make_player: callable
) -> None:
    leader, runner_up, newcomer = await make_player(), await make_player(), await make_player()
    await finished_session(repository, leader, score=3)
    await finished_session(repository, leader, score=1)
    await finished_session(repository, runner_up, score=2)
    timed_out = await repository.create_session(runner_up.id)
    await repository.register_gesture(timed_out.id)
    await set_idle(session_factory, timed_out.id, seconds=31)
    await repository.close_timed_out_sessions(timeout_seconds=30)
    # Активная сессия в рейтинг не входит.
    active = await repository.create_session(newcomer.id)
    await repository.register_gesture(active.id)

    ratings = await repository.get_ratings()

    own_ids = {leader.id, runner_up.id, newcomer.id}
    own = [
        (row.player_id, row.total_score, row.best_session_score)
        for row in ratings
        if row.player_id in own_ids
    ]
    assert own == [(leader.id, 4, 3), (runner_up.id, 3, 2), (newcomer.id, 0, 0)]
    totals = [row.total_score for row in ratings]
    assert totals == sorted(totals, reverse=True)


async def test_deleting_player_removes_sessions_and_events(
    repository: PostgresGameRepository, session_factory: SessionFactory, make_player: callable
) -> None:
    player = await make_player()
    session = await finished_session(repository, player, score=2)

    async with session_factory.begin() as db:
        await db.execute(delete(Player).where(Player.id == player.id))

    assert await repository.get_session(session.id) is None
    async with session_factory() as db:
        events = await db.scalar(
            select(func.count()).select_from(GestureEvent).where(GestureEvent.session_id == session.id)
        )
        assert events == 0
