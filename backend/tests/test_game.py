import pytest

from app.repositories.game import SessionData
from app.schemas.hands import HandFrame
from app.services.game import SessionGame, SessionNotActiveError
from app.services.vision import stub_detect_gesture
from tests.fakes import FakeClock, InMemoryGameRepository
from tests.helpers import make_frame, swing_frames


@pytest.fixture
def game(repository: InMemoryGameRepository, session: SessionData, clock: FakeClock) -> SessionGame:
    return SessionGame(
        session_id=session.id,
        repository=repository,
        detect_gesture=stub_detect_gesture,
        cooldown_ms=1500,
        window_size=30,
        touch_interval_seconds=2,
        clock=clock,
    )


async def feed(game: SessionGame, frames: list[dict]) -> list[int]:
    """Скормить кадры и вернуть счёт после каждого засчитанного жеста."""
    gestures = [await game.handle_frame(HandFrame.model_validate(frame)) for frame in frames]
    return [gesture.score for gesture in gestures if gesture is not None]


async def test_continuous_swinging_scores_once_per_cooldown(game: SessionGame, clock: FakeClock) -> None:
    scores = []
    # 6 секунд непрерывных «качелей», кадр каждые 100 мс.
    for frame in swing_frames(60, step_ms=100):
        scores += await feed(game, [frame])
        clock.advance(0.1)

    # Первый жест на третьем кадре, дальше — по одному за каждый cooldown (1,5 с).
    assert scores == [1, 2, 3, 4]


async def test_gesture_updates_activity_without_extra_write(
    game: SessionGame, repository: InMemoryGameRepository
) -> None:
    assert await feed(game, swing_frames(3)) == [1]

    # last_activity_at обновляет сама запись жеста, отдельный touch не нужен.
    assert repository.touch_count == 0


async def test_activity_is_written_at_most_once_per_interval(
    game: SessionGame, repository: InMemoryGameRepository, clock: FakeClock
) -> None:
    for i in range(50):  # 5 секунд кадров без рук
        await feed(game, [make_frame(i * 100)])
        clock.advance(0.1)

    assert repository.touch_count == 2


async def test_gesture_in_finished_session_is_not_counted(
    game: SessionGame, repository: InMemoryGameRepository, session: SessionData
) -> None:
    await repository.stop_session(session.id)

    with pytest.raises(SessionNotActiveError):
        await feed(game, swing_frames(3))

    assert repository.sessions[session.id].score == 0
    assert repository.gesture_events == []


async def test_frame_in_finished_session_is_rejected(
    game: SessionGame, repository: InMemoryGameRepository, session: SessionData, clock: FakeClock
) -> None:
    await repository.stop_session(session.id)
    clock.advance(2)

    with pytest.raises(SessionNotActiveError):
        await feed(game, [make_frame(0)])
