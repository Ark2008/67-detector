from typing import Annotated

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from app.dependencies import get_detector_factory, get_game_session_repository, get_hand_tracker_factory
from app.models.game_session import NICKNAME_MAX_LENGTH
from app.repositories.game_sessions import GameSessionRepository
from app.schemas.messages import (
    ErrorCode,
    ErrorEvent,
    GestureDetectedEvent,
    HandLandmarksMessage,
    ServerEvent,
    SessionStartedEvent,
)
from app.services.game import Game
from app.services.vision import DetectorFactory, HandTrackerFactory

router = APIRouter()


@router.websocket("/ws/game")
async def game_websocket(
    websocket: WebSocket,
    nickname: Annotated[str, Query(min_length=1, max_length=NICKNAME_MAX_LENGTH)],
    repository: Annotated[GameSessionRepository, Depends(get_game_session_repository)],
    tracker_factory: Annotated[HandTrackerFactory, Depends(get_hand_tracker_factory)],
    detector_factory: Annotated[DetectorFactory, Depends(get_detector_factory)],
) -> None:
    await websocket.accept()
    game = await Game.start(nickname, repository, tracker_factory(), detector_factory())
    await send_event(websocket, SessionStartedEvent(session_id=game.session_id, nickname=nickname, score=0))

    try:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                break
            # Бинарное сообщение — кадр камеры, текстовое — JSON с координатами рук.
            if (image := message.get("bytes")) is not None:
                event = await process_image(game, image)
            else:
                event = await process_landmarks(game, message["text"])
            if event is not None:
                await send_event(websocket, event)
    except WebSocketDisconnect:
        pass
    finally:
        await game.finish()


async def process_image(game: Game, image: bytes) -> ServerEvent | None:
    try:
        score = await game.handle_image(image)
    except ValueError as exc:
        return ErrorEvent(code=ErrorCode.INVALID_FRAME, message=f"Не удалось обработать кадр: {exc}")
    return gesture_event(game, score)


async def process_landmarks(game: Game, raw: str) -> ServerEvent | None:
    try:
        message = HandLandmarksMessage.model_validate_json(raw)
    except ValidationError as exc:
        return ErrorEvent(
            code=ErrorCode.INVALID_MESSAGE,
            message="Сообщение не соответствует формату hand_landmarks",
            details=exc.errors(include_url=False, include_context=False, include_input=False),
        )
    return gesture_event(game, await game.handle_frame(message))


def gesture_event(game: Game, score: int | None) -> GestureDetectedEvent | None:
    return None if score is None else GestureDetectedEvent(session_id=game.session_id, score=score)


async def send_event(websocket: WebSocket, event: ServerEvent) -> None:
    await websocket.send_text(event.model_dump_json())
