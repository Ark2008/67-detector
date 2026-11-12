"""Сообщения WebSocket /ws/sessions/{session_id}. Спецификация — docs/websocket.md."""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Literal, TypeAlias

from pydantic import BaseModel

from app.models import SessionStatus
from app.schemas.hands import HandFrame

# Клиент → сервер


class FrameMessage(HandFrame):
    type: Literal["frame"]


# Сервер → клиент


class SessionReadyEvent(BaseModel):
    type: Literal["session_ready"] = "session_ready"
    session_id: uuid.UUID
    status: SessionStatus
    score: int


class GestureDetectedEvent(BaseModel):
    type: Literal["gesture_detected"] = "gesture_detected"
    score: int
    detected_at: datetime
    cooldown_ms: int


class SessionStateEvent(BaseModel):
    type: Literal["session_state"] = "session_state"
    status: SessionStatus
    score: int
    ended_at: datetime | None


class ErrorCode(StrEnum):
    INVALID_PAYLOAD = "invalid_payload"
    SESSION_NOT_FOUND = "session_not_found"
    INTERNAL_ERROR = "internal_error"


class ErrorEvent(BaseModel):
    type: Literal["error"] = "error"
    code: ErrorCode
    message: str


ServerEvent: TypeAlias = SessionReadyEvent | GestureDetectedEvent | SessionStateEvent | ErrorEvent
