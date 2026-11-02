"""Сообщения WebSocket /ws/game. Спецификация — docs/websocket.md."""

from enum import StrEnum
from typing import Any, Literal, TypeAlias

from pydantic import BaseModel

from app.schemas.hands import HandFrame

# Клиент → сервер


class HandLandmarksMessage(HandFrame):
    type: Literal["hand_landmarks"]


# Сервер → клиент


class SessionStartedEvent(BaseModel):
    type: Literal["session_started"] = "session_started"
    session_id: int
    nickname: str
    score: int


class GestureDetectedEvent(BaseModel):
    type: Literal["gesture_detected"] = "gesture_detected"
    session_id: int
    score: int


class ErrorCode(StrEnum):
    INVALID_MESSAGE = "invalid_message"
    INVALID_FRAME = "invalid_frame"


class ErrorEvent(BaseModel):
    type: Literal["error"] = "error"
    code: ErrorCode
    message: str
    details: list[dict[str, Any]] = []


ServerEvent: TypeAlias = SessionStartedEvent | GestureDetectedEvent | ErrorEvent
