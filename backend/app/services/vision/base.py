"""Контракт Backend → CV (docs/contracts.md): окно кадров → распознан ли жест.

Типы описаны через dict, чтобы модуль из cv/ не зависел от backend и pydantic:
кадр выглядит так же, как сообщение `frame` из docs/websocket.md, только без поля `type`.
"""

from collections.abc import Callable
from typing import Literal, TypeAlias, TypedDict

GESTURE_SIX_SEVEN = "six_seven"
GESTURE_NONE = "none"


class LandmarkDict(TypedDict):
    x: float
    y: float
    z: float


class HandDict(TypedDict):
    handedness: Literal["Left", "Right"]
    score: float
    landmarks: list[LandmarkDict]  # 21 точка, порядок MediaPipe


class FrameDict(TypedDict):
    timestamp_ms: float
    hands: list[HandDict]  # 0, 1 или 2 руки


class GestureResult(TypedDict):
    gesture: Literal["six_seven", "none"]


# detect_gesture(frames) -> {"gesture": "six_seven" | "none"}
#
# frames — скользящее окно последних кадров сессии, от старых к новым, от 1 до
# FRAME_WINDOW_SIZE штук. Функция без состояния между вызовами: про сессии и cooldown
# не знает, порог распознавания применяет сама. Вызывается из рабочего потока.
DetectGesture: TypeAlias = Callable[[list[FrameDict]], GestureResult]
