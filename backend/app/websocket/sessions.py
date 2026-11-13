"""WebSocket сессии демонстрации. Спецификация — docs/websocket.md."""

import logging
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from pydantic import ValidationError

from app.dependencies import ClockDep, DetectGestureDep, RegistryDep, RepositoryDep, SettingsDep
from app.repositories.game import GameRepository, SessionData
from app.schemas.messages import (
    ErrorCode,
    ErrorEvent,
    FrameMessage,
    GestureDetectedEvent,
    ServerEvent,
    SessionReadyEvent,
)
from app.services.connections import Connection, session_state_event
from app.services.game import SessionGame, SessionNotActiveError

logger = logging.getLogger(__name__)
router = APIRouter()

SESSION_NOT_FOUND = ErrorEvent(
    code=ErrorCode.SESSION_NOT_FOUND, message="Сессия не существует или уже завершена"
)


@router.websocket("/ws/sessions/{session_id}")
async def session_websocket(
    websocket: WebSocket,
    session_id: str,
    repository: RepositoryDep,
    registry: RegistryDep,
    detect_gesture: DetectGestureDep,
    settings: SettingsDep,
    clock: ClockDep,
) -> None:
    await websocket.accept()
    connection = Connection(websocket)

    session = await find_session(repository, session_id)
    if session is None or not session.is_active:
        await connection.close(SESSION_NOT_FOUND, code=status.WS_1008_POLICY_VIOLATION)
        return

    # У сессии одно подключение: новое вытесняет прежнее (например, после перезагрузки вкладки).
    previous = registry.register(session.id, connection)
    if previous is not None:
        await previous.close(code=status.WS_1008_POLICY_VIOLATION)

    game = SessionGame(
        session_id=session.id,
        repository=repository,
        detect_gesture=detect_gesture,
        cooldown_ms=settings.cooldown_ms,
        window_size=settings.frame_window_size,
        touch_interval_seconds=settings.activity_touch_interval_seconds,
        clock=clock,
    )
    try:
        await connection.send(
            SessionReadyEvent(session_id=session.id, status=session.status, score=session.score)
        )
        await receive_frames(websocket, connection, game, repository, settings.cooldown_ms)
    except WebSocketDisconnect:
        pass
    finally:
        # Сессию здесь не завершаем: без «Стоп» её закроет фоновая задача по таймауту.
        registry.unregister(session.id, connection)


async def find_session(repository: GameRepository, session_id: str) -> SessionData | None:
    try:
        return await repository.get_session(uuid.UUID(session_id))
    except ValueError:  # session_id в адресе — не UUID
        return None


async def receive_frames(
    websocket: WebSocket,
    connection: Connection,
    game: SessionGame,
    repository: GameRepository,
    cooldown_ms: int,
) -> None:
    while True:
        message = await websocket.receive()
        # connection.closed — сокет уже закрыли «Стоп» или таймаут из другой задачи.
        if message["type"] == "websocket.disconnect" or connection.closed:
            return
        try:
            event = await process_message(message.get("text"), game, cooldown_ms)
        except SessionNotActiveError:
            # Сессию завершили мимо реестра подключений (например, другой процесс backend).
            session = await repository.get_session(game.session_id)
            await connection.close(SESSION_NOT_FOUND if session is None else session_state_event(session))
            return
        except Exception:
            logger.exception("Ошибка обработки кадра сессии %s", game.session_id)
            event = ErrorEvent(code=ErrorCode.INTERNAL_ERROR, message="Не удалось обработать кадр")
        if event is not None:
            await connection.send(event)


async def process_message(text: str | None, game: SessionGame, cooldown_ms: int) -> ServerEvent | None:
    if text is None:
        return ErrorEvent(code=ErrorCode.INVALID_PAYLOAD, message="Ожидается текстовое JSON-сообщение")
    try:
        frame = FrameMessage.model_validate_json(text)
    except ValidationError as exc:
        return ErrorEvent(code=ErrorCode.INVALID_PAYLOAD, message=describe_validation_error(exc))

    gesture = await game.handle_frame(frame)
    if gesture is None:
        return None
    return GestureDetectedEvent(score=gesture.score, detected_at=gesture.detected_at, cooldown_ms=cooldown_ms)


def describe_validation_error(exc: ValidationError) -> str:
    """Первая ошибка валидации одной строкой, например `hands.0.landmarks: List should have ...`."""
    error = exc.errors(include_url=False, include_context=False, include_input=False)[0]
    location = ".".join(str(part) for part in error["loc"])
    return f"{location}: {error['msg']}" if location else error["msg"]
