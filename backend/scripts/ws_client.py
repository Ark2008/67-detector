"""Тестовый WebSocket-клиент для /ws/game.

По умолчанию шлёт JSON с координатами рук, которые «качаются» как в жесте 67.
С --frames шлёт бинарные «кадры камеры» (заглушки, их понимает только mock-трекер).

Запуск из backend/ при работающем сервере:
    python scripts/ws_client.py --nickname Vasya
    python scripts/ws_client.py --frames
    python scripts/ws_client.py --print-sample   # 3 готовых сообщения для Postman/websocat
"""

import argparse
import asyncio
import json
import math
import time
from typing import Any
from urllib.parse import urlencode

from websockets.asyncio.client import ClientConnection, connect

LANDMARKS_PER_HAND = 21
# Не настоящее изображение: mock-трекер содержимое кадра не смотрит.
FAKE_IMAGE = b"\xff\xd8\xff fake jpeg"


def make_hand(handedness: str, wrist_x: float, wrist_y: float) -> dict[str, Any]:
    """Рука MediaPipe: запястье (точка 0) и 5 пальцев по 4 точки, растопыренных вверх."""
    landmarks = [{"x": wrist_x, "y": wrist_y, "z": 0.0}]
    for finger in range(5):
        for joint in range(1, 5):
            landmarks.append(
                {
                    "x": round(wrist_x + (finger - 2) * 0.02, 4),
                    "y": round(wrist_y - joint * 0.03, 4),
                    "z": 0.0,
                }
            )
    assert len(landmarks) == LANDMARKS_PER_HAND
    return {"handedness": handedness, "landmarks": landmarks}


def make_message(timestamp_ms: float, left_y: float, right_y: float) -> dict[str, Any]:
    return {
        "type": "hand_landmarks",
        "timestamp_ms": round(timestamp_ms, 1),
        "hands": [make_hand("Left", 0.3, left_y), make_hand("Right", 0.7, right_y)],
    }


async def send_landmarks(ws: ClientConnection, duration_s: float, fps: int, frequency_hz: float) -> None:
    start = time.perf_counter()
    while (elapsed := time.perf_counter() - start) < duration_s:
        offset = 0.15 * math.sin(2 * math.pi * frequency_hz * elapsed)
        await ws.send(json.dumps(make_message(elapsed * 1000, 0.5 + offset, 0.5 - offset)))
        await asyncio.sleep(1 / fps)


async def send_camera_frames(ws: ClientConnection, duration_s: float, fps: int) -> None:
    start = time.perf_counter()
    while time.perf_counter() - start < duration_s:
        await ws.send(FAKE_IMAGE)
        await asyncio.sleep(1 / fps)


async def print_events(ws: ClientConnection) -> None:
    async for raw in ws:
        event = json.loads(raw)
        print(f"<- {event['type']}: {event}")


async def run(args: argparse.Namespace) -> None:
    url = f"{args.url}?{urlencode({'nickname': args.nickname})}"
    kind = "кадры камеры" if args.frames else "координаты рук"
    print(f"Подключаюсь к {url}, шлю {kind} {args.duration} с...")
    async with connect(url) as ws, asyncio.TaskGroup() as tg:
        tg.create_task(print_events(ws))
        if args.frames:
            await send_camera_frames(ws, args.duration, args.fps)
        else:
            await send_landmarks(ws, args.duration, args.fps, args.frequency)
        await asyncio.sleep(0.5)  # дождаться последних событий
        await ws.close()
    print("Готово, соединение закрыто.")


def print_sample() -> None:
    """Три кадра «левая выше → правая выше → левая выше» = один засчитанный жест."""
    for i, (left_y, right_y) in enumerate([(0.3, 0.7), (0.7, 0.3), (0.3, 0.7)]):
        print(json.dumps(make_message(i * 300, left_y, right_y)))


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--url", default="ws://localhost:8000/ws/game")
    parser.add_argument("--nickname", default="tester")
    parser.add_argument("--duration", type=float, default=5, help="сколько секунд слать кадры")
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--frequency", type=float, default=1.5, help="полных циклов «качелей» в секунду")
    parser.add_argument("--frames", action="store_true", help="слать бинарные кадры вместо координат")
    parser.add_argument("--print-sample", action="store_true", help="напечатать 3 сообщения и выйти")
    args = parser.parse_args()

    if args.print_sample:
        print_sample()
    else:
        asyncio.run(run(args))


if __name__ == "__main__":
    main()
