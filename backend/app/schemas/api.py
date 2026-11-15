"""Тела запросов и ответов REST. Спецификация — docs/contracts.md."""

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, StringConstraints

from app.models import PLAYER_NAME_MAX_LENGTH, SessionStatus

PlayerName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=PLAYER_NAME_MAX_LENGTH)
]


class PlayerCreateRequest(BaseModel):
    name: PlayerName


class PlayerResponse(BaseModel):
    player_id: uuid.UUID
    name: str
    created_at: datetime


class SessionCreateRequest(BaseModel):
    player_id: uuid.UUID


class SessionStartedResponse(BaseModel):
    session_id: uuid.UUID
    status: SessionStatus
    score: int
    started_at: datetime


class SessionStoppedResponse(SessionStartedResponse):
    ended_at: datetime | None


class RatingPlayer(BaseModel):
    player_id: uuid.UUID
    name: str
    total_score: int
    best_session_score: int


class RatingsResponse(BaseModel):
    players: list[RatingPlayer]
