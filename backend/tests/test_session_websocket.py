import uuid
from typing import Any

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from starlette.testclient import WebSocketTestSession
from starlette.websockets import WebSocketDisconnect

from app.config import Settings
from app.main import create_app
from app.models import SessionStatus
from app.repositories.game import PlayerData, SessionData
from tests.fakes import FakeClock, InMemoryGameRepository
from tests.helpers import make_frame, swing_messages, to_message


def url(session_id: object) -> str:
    return f"/ws/sessions/{session_id}"


def assert_closed(ws: WebSocketTestSession, code: int) -> None:
    with pytest.raises(WebSocketDisconnect) as exc_info:
        ws.receive_json()
    assert exc_info.value.code == code


def stop(client: TestClient, session: SessionData) -> dict[str, Any]:
    return client.post(f"/sessions/{session.id}/stop").json()


def wait_until_processed(ws: WebSocketTestSession) -> None:
    """Дождаться обработки всех отправленных кадров.

    Сообщения обрабатываются по порядку, поэтому ответ на заведомо неверное сообщение
    означает, что все кадры до него обработаны и других событий сервер не прислал.
    """
    ws.send_text("sync")
    assert ws.receive_json()["code"] == "invalid_payload"


# Подключение


def test_connect_sends_session_ready(client: TestClient, session: SessionData) -> None:
    with client.websocket_connect(url(session.id)) as ws:
        event = ws.receive_json()

    assert event == {"type": "session_ready", "session_id": str(session.id), "status": "active", "score": 0}


@pytest.mark.parametrize("session_id", [uuid.uuid4(), "not-a-uuid"])
def test_unknown_session_gets_error_and_is_closed(client: TestClient, session_id: object) -> None:
    with client.websocket_connect(url(session_id)) as ws:
        error = ws.receive_json()
        assert_closed(ws, status.WS_1008_POLICY_VIOLATION)

    assert error["type"] == "error"
    assert error["code"] == "session_not_found"


def test_finished_session_gets_error_and_is_closed(
    client: TestClient, repository: InMemoryGameRepository, player: PlayerData
) -> None:
    finished = repository.add_session(player.id, status=SessionStatus.STOPPED)

    with client.websocket_connect(url(finished.id)) as ws:
        assert ws.receive_json()["code"] == "session_not_found"
        assert_closed(ws, status.WS_1008_POLICY_VIOLATION)


def test_new_connection_replaces_previous(client: TestClient, session: SessionData) -> None:
    with client.websocket_connect(url(session.id)) as first:
        first.receive_json()  # session_ready
        with client.websocket_connect(url(session.id)) as second:
            assert second.receive_json()["type"] == "session_ready"
            assert_closed(first, status.WS_1008_POLICY_VIOLATION)

            for message in swing_messages(3):
                second.send_json(message)
            assert second.receive_json()["type"] == "gesture_detected"


# Жест и анти-дребезг


def test_gesture_is_counted(
    client: TestClient, repository: InMemoryGameRepository, session: SessionData
) -> None:
    with client.websocket_connect(url(session.id)) as ws:
        ws.receive_json()  # session_ready
        for message in swing_messages(3):
            ws.send_json(message)
        event = ws.receive_json()

    assert set(event) == {"type", "score", "detected_at", "cooldown_ms"}
    assert event["type"] == "gesture_detected"
    assert event["score"] == 1
    assert event["cooldown_ms"] == 1500
    assert repository.sessions[session.id].score == 1
    assert [session_id for session_id, _ in repository.gesture_events] == [session.id]


def test_gesture_during_cooldown_is_dropped(
    client: TestClient, repository: InMemoryGameRepository, session: SessionData, clock: FakeClock
) -> None:
    with client.websocket_connect(url(session.id)) as ws:
        ws.receive_json()  # session_ready
        for message in swing_messages(3):
            ws.send_json(message)
        assert ws.receive_json()["score"] == 1

        clock.advance(1.4)  # cooldown 1500 мс ещё не истёк
        for message in swing_messages(5, start_ms=2000):
            ws.send_json(message)
        # Второй жест не отправлен клиенту и не записан.
        wait_until_processed(ws)

    assert repository.sessions[session.id].score == 1
    assert len(repository.gesture_events) == 1


def test_gesture_after_cooldown_is_counted_again(
    client: TestClient, repository: InMemoryGameRepository, session: SessionData, clock: FakeClock
) -> None:
    with client.websocket_connect(url(session.id)) as ws:
        ws.receive_json()  # session_ready
        for message in swing_messages(3):
            ws.send_json(message)
        assert ws.receive_json()["score"] == 1

        clock.advance(1.5)
        for message in swing_messages(3, start_ms=2000):
            ws.send_json(message)
        assert ws.receive_json()["score"] == 2

    assert repository.sessions[session.id].score == 2


def test_counted_gesture_frames_do_not_trigger_again(
    client: TestClient, repository: InMemoryGameRepository, session: SessionData, clock: FakeClock
) -> None:
    with client.websocket_connect(url(session.id)) as ws:
        ws.receive_json()  # session_ready
        for message in swing_messages(3):
            ws.send_json(message)
        assert ws.receive_json()["score"] == 1

        # Cooldown истёк, но новых взмахов нет: старые кадры жеста не должны засчитаться повторно.
        clock.advance(2)
        ws.send_json(to_message(make_frame(700)))
        wait_until_processed(ws)

    assert repository.sessions[session.id].score == 1


# Кадры


def test_frames_without_hands_keep_session_alive(
    client: TestClient, repository: InMemoryGameRepository, session: SessionData, clock: FakeClock
) -> None:
    with client.websocket_connect(url(session.id)) as ws:
        ws.receive_json()  # session_ready
        ws.send_json(to_message(make_frame(0)))
        clock.advance(2)  # last_activity_at пишется в БД не чаще раза в 2 с
        ws.send_json(to_message(make_frame(2000)))
        ws.send_json(to_message(make_frame(2050)))
        wait_until_processed(ws)

    assert repository.touch_count == 1


@pytest.mark.parametrize(
    ("payload", "message_part"),
    [
        ("not json", "Invalid JSON"),
        ({"type": "hand_landmarks", "timestamp_ms": 0, "hands": []}, "type"),
        ({"type": "frame", "hands": []}, "timestamp_ms"),
        (
            {
                "type": "frame",
                "timestamp_ms": 0,
                "hands": [{"handedness": "Left", "score": 0.9, "landmarks": []}],
            },
            "hands.0.landmarks",
        ),
        ({"type": "frame", "timestamp_ms": 0, "hands": [make_frame(0, left_y=0.5)["hands"][0]] * 3}, "hands"),
    ],
)
def test_invalid_payload_returns_error_and_keeps_connection(
    client: TestClient, session: SessionData, payload: Any, message_part: str
) -> None:
    with client.websocket_connect(url(session.id)) as ws:
        ws.receive_json()  # session_ready

        if isinstance(payload, str):
            ws.send_text(payload)
        else:
            ws.send_json(payload)
        error = ws.receive_json()
        assert set(error) == {"type", "code", "message"}
        assert error["code"] == "invalid_payload"
        assert message_part in error["message"]

        for message in swing_messages(3):
            ws.send_json(message)
        assert ws.receive_json()["type"] == "gesture_detected"


def test_binary_message_returns_error(client: TestClient, session: SessionData) -> None:
    with client.websocket_connect(url(session.id)) as ws:
        ws.receive_json()  # session_ready
        ws.send_bytes(b"\xff\xd8\xff jpeg")

        assert ws.receive_json()["code"] == "invalid_payload"


def test_cv_receives_sliding_window_of_frames(
    repository: InMemoryGameRepository, session: SessionData
) -> None:
    windows: list[list[dict[str, Any]]] = []

    def recording_detect(frames: list[dict[str, Any]]) -> dict[str, str]:
        windows.append(frames)
        return {"gesture": "none"}

    app = create_app(
        Settings(_env_file=None, frame_window_size=3), repository=repository, detect_gesture=recording_detect
    )
    messages = swing_messages(5)
    with TestClient(app) as client, client.websocket_connect(url(session.id)) as ws:
        ws.receive_json()  # session_ready
        for message in messages:
            ws.send_json(message)
        wait_until_processed(ws)

    frames = [{key: value for key, value in message.items() if key != "type"} for message in messages]
    assert windows == [frames[:1], frames[:2], frames[:3], frames[1:4], frames[2:5]]


def test_cv_failure_returns_internal_error_and_keeps_connection(
    repository: InMemoryGameRepository, session: SessionData
) -> None:
    def broken_detect(frames: list[dict[str, Any]]) -> dict[str, str]:
        raise RuntimeError("модель не загрузилась")

    app = create_app(Settings(_env_file=None), repository=repository, detect_gesture=broken_detect)
    with TestClient(app) as client, client.websocket_connect(url(session.id)) as ws:
        ws.receive_json()  # session_ready
        for _ in range(2):
            ws.send_json(to_message(make_frame(0)))
            error = ws.receive_json()
            assert error["type"] == "error"
            assert error["code"] == "internal_error"


# Завершение сессии


def test_stop_sends_session_state_and_closes_socket(
    client: TestClient, repository: InMemoryGameRepository, session: SessionData
) -> None:
    with client.websocket_connect(url(session.id)) as ws:
        ws.receive_json()  # session_ready
        for message in swing_messages(3):
            ws.send_json(message)
        ws.receive_json()  # gesture_detected

        stopped = stop(client, session)

        event = ws.receive_json()
        assert_closed(ws, status.WS_1000_NORMAL_CLOSURE)

    assert event == {
        "type": "session_state",
        "status": "stopped",
        "score": 1,
        "ended_at": stopped["ended_at"],
    }
    assert repository.sessions[session.id].status == SessionStatus.STOPPED


def test_disconnect_without_stop_leaves_session_active(
    client: TestClient, repository: InMemoryGameRepository, session: SessionData
) -> None:
    with client.websocket_connect(url(session.id)) as ws:
        ws.receive_json()  # session_ready

    # Сессию закроет фоновая задача по таймауту, а не обрыв сокета.
    assert repository.sessions[session.id].status == SessionStatus.ACTIVE


async def test_session_finished_elsewhere_closes_socket_on_next_frame(
    repository: InMemoryGameRepository, session: SessionData
) -> None:
    # «Стоп» пришёл мимо реестра подключений — например, в другой процесс backend.
    app = create_app(Settings(_env_file=None, activity_touch_interval_seconds=0), repository=repository)
    with TestClient(app) as client, client.websocket_connect(url(session.id)) as ws:
        ws.receive_json()  # session_ready
        await repository.stop_session(session.id)

        ws.send_json(to_message(make_frame(0)))

        event = ws.receive_json()
        assert event["type"] == "session_state"
        assert event["status"] == "stopped"
        assert_closed(ws, status.WS_1000_NORMAL_CLOSURE)
