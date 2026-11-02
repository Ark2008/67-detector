import pytest
from fastapi import status
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.dependencies import get_hand_tracker_factory
from app.main import app
from app.schemas.hands import HandFrame
from tests.conftest import InMemoryGameSessionRepository
from tests.helpers import swing_frames, to_message

URL = "/ws/game?nickname=tester"


class ScriptedHandTracker:
    """Вместо поиска рук на изображении возвращает заранее заданные кадры."""

    def __init__(self, frames: list[HandFrame]) -> None:
        self._frames = iter(frames)

    def track(self, image: bytes, timestamp_ms: float) -> HandFrame:
        return next(self._frames)


def test_connect_starts_session(client: TestClient, repository: InMemoryGameSessionRepository) -> None:
    with client.websocket_connect(URL) as ws:
        event = ws.receive_json()

    assert event == {"type": "session_started", "session_id": 1, "nickname": "tester", "score": 0}
    assert repository.sessions[1].nickname == "tester"


def test_gesture_increments_score(client: TestClient, repository: InMemoryGameSessionRepository) -> None:
    with client.websocket_connect(URL) as ws:
        ws.receive_json()  # session_started
        for frame in swing_frames(5):
            ws.send_json(to_message(frame))
        events = [ws.receive_json(), ws.receive_json()]

    assert events == [
        {"type": "gesture_detected", "session_id": 1, "score": 1},
        {"type": "gesture_detected", "session_id": 1, "score": 2},
    ]
    assert repository.sessions[1].score == 2


def test_camera_frames_go_through_tracker_and_detector(
    client: TestClient, repository: InMemoryGameSessionRepository
) -> None:
    tracker = ScriptedHandTracker(swing_frames(3))
    app.dependency_overrides[get_hand_tracker_factory] = lambda: lambda: tracker

    with client.websocket_connect(URL) as ws:
        ws.receive_json()  # session_started
        for _ in range(3):
            ws.send_bytes(b"fake-jpeg")
        event = ws.receive_json()

    assert event == {"type": "gesture_detected", "session_id": 1, "score": 1}
    assert repository.sessions[1].score == 1


def test_invalid_camera_frame_returns_error(client: TestClient) -> None:
    with client.websocket_connect(URL) as ws:
        ws.receive_json()  # session_started
        ws.send_bytes(b"")
        error = ws.receive_json()

    assert error["type"] == "error"
    assert error["code"] == "invalid_frame"


def test_invalid_message_returns_error_and_keeps_connection(client: TestClient) -> None:
    with client.websocket_connect(URL) as ws:
        ws.receive_json()  # session_started

        ws.send_text("not json")
        assert ws.receive_json()["code"] == "invalid_message"

        ws.send_json(
            {"type": "hand_landmarks", "timestamp_ms": 0, "hands": [{"handedness": "Left", "landmarks": []}]}
        )
        error = ws.receive_json()
        assert error["type"] == "error"
        assert error["details"][0]["loc"] == ["hands", 0, "landmarks"]

        for frame in swing_frames(3):
            ws.send_json(to_message(frame))
        assert ws.receive_json()["type"] == "gesture_detected"


def test_disconnect_finishes_session(client: TestClient, repository: InMemoryGameSessionRepository) -> None:
    with client.websocket_connect(URL) as ws:
        ws.receive_json()

    assert repository.sessions[1].finished


def test_connection_without_nickname_is_rejected(client: TestClient) -> None:
    with pytest.raises(WebSocketDisconnect) as exc_info, client.websocket_connect("/ws/game"):
        pass

    assert exc_info.value.code == status.WS_1008_POLICY_VIOLATION
