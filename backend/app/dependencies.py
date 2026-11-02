"""Зависимости FastAPI. Здесь подменяются mock-реализации на настоящие."""

from app.db import session_factory
from app.repositories.game_sessions import GameSessionRepository, PostgresGameSessionRepository
from app.services.vision import DetectorFactory, HandTrackerFactory, SwingGestureDetector, SwingHandTracker


def get_game_session_repository() -> GameSessionRepository:
    return PostgresGameSessionRepository(session_factory)


def get_hand_tracker_factory() -> HandTrackerFactory:
    # TODO: заменить на настоящий трекер из cv/hand_tracking, когда он будет готов.
    return SwingHandTracker


def get_detector_factory() -> DetectorFactory:
    # TODO: заменить на настоящий детектор из cv/gesture_detector, когда он будет готов.
    return SwingGestureDetector
