"""Координаты рук в формате MediaPipe Hand Landmarker (docs/websocket.md)."""

from enum import StrEnum

from pydantic import BaseModel, Field, FiniteFloat, field_validator

LANDMARKS_PER_HAND = 21
MAX_HANDS = 2


class Handedness(StrEnum):
    LEFT = "Left"
    RIGHT = "Right"


class Landmark(BaseModel):
    """Точка руки: x, y нормированы на размер кадра (0..1, y растёт вниз), z — относительная глубина."""

    x: FiniteFloat = Field(ge=0, le=1)
    y: FiniteFloat = Field(ge=0, le=1)
    z: FiniteFloat


class Hand(BaseModel):
    handedness: Handedness
    score: float = Field(ge=0, le=1)
    # Порядок точек как в MediaPipe: 0 — запястье, 1-4 — большой палец, ..., 17-20 — мизинец.
    landmarks: list[Landmark] = Field(min_length=LANDMARKS_PER_HAND, max_length=LANDMARKS_PER_HAND)


class HandFrame(BaseModel):
    """Руки, найденные на одном кадре камеры: 0, 1 или 2."""

    timestamp_ms: FiniteFloat = Field(ge=0)
    hands: list[Hand] = Field(max_length=MAX_HANDS)

    @field_validator("hands")
    @classmethod
    def unique_handedness(cls, hands: list[Hand]) -> list[Hand]:
        if len({hand.handedness for hand in hands}) != len(hands):
            raise ValueError("handedness must be unique within a frame")
        return hands
