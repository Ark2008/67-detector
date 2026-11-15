"""Тестовый клиент: проходит весь сценарий главного экрана без браузера и камеры.

POST /players → POST /sessions → WebSocket /ws/sessions/{session_id} с кадрами,
на которых руки «качаются» как в жесте 67 → POST /sessions/{id}/stop → GET /ratings.

Запуск из backend/ при работающем сервере:
    python scripts/ws_client.py --name Vasya
    python scripts/ws_client.py --no-stop        # оборвать сокет без «Стоп»: сессию закроет таймаут
    python scripts/ws_client.py --print-sample   # 3 готовых сообщения frame для Postman/websocat
"""

import argparse
import asyncio
import json
import math
import time
import urllib.request
from typing import Any

from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed

LANDMARKS_PER_HAND = 21


def call_api(base_url: str, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    request = urllib.request.Request(
        base_url + path,
        method=method,
        data=None if body is None else json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request) as response:
        return json.load(response)


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
    return {"handedness": handedness, "score": 0.98, "landmarks": landmarks}


def make_message(timestamp_ms: int, left_y: float, right_y: float) -> dict[str, Any]:
    return {
        "type": "frame",
        "timestamp_ms": timestamp_ms,
        "hands": [make_hand("Left", 0.3, left_y), make_hand("Right", 0.7, right_y)],
    }


async def send_frames(ws: ClientConnection, duration_s: float, fps: int, frequency_hz: float) -> None:
    start = time.perf_counter()
    while (elapsed := time.perf_counter() - start) < duration_s:
        offset = 0.15 * math.sin(2 * math.pi * frequency_hz * elapsed)
        await ws.send(json.dumps(make_message(int(time.time() * 1000), 0.5 + offset, 0.5 - offset)))
        await asyncio.sleep(1 / fps)


async def print_events(ws: ClientConnection) -> None:
    try:
        async for raw in ws:
            event = json.loads(raw)
            print(f"<- {event['type']}: {event}")
    except ConnectionClosed:
        pass
    print(f"Сокет закрыт сервером или клиентом, код {ws.close_code}")


async def run(args: argparse.Namespace) -> None:
    player = call_api(args.url, "POST", "/players", {"name": args.name})
    print(f"POST /players -> {player}")
    session = call_api(args.url, "POST", "/sessions", {"player_id": player["player_id"]})
    print(f"POST /sessions -> {session}")

    ws_url = f"{args.url.replace('http', 'ws', 1)}/ws/sessions/{session['session_id']}"
    print(f"Подключаюсь к {ws_url}, шлю кадры {args.duration} с...")
    async with connect(ws_url) as ws:
        events = asyncio.create_task(print_events(ws))
        await send_frames(ws, args.duration, args.fps, args.frequency)
        if args.no_stop:
            print("Обрываю сокет без «Стоп»: сессия останется active до таймаута.")
        else:
            stop_path = f"/sessions/{session['session_id']}/stop"
            stopped = await asyncio.to_thread(call_api, args.url, "POST", stop_path)
            print(f"POST {stop_path} -> {stopped}")
            # Сервер сам пришлёт session_state и закроет сокет.
            await asyncio.wait_for(events, timeout=5)

    ratings = call_api(args.url, "GET", "/ratings")
    print("GET /ratings ->")
    for place, row in enumerate(ratings["players"][:10], start=1):
        print(
            f"  {place}. {row['name']}: всего {row['total_score']}, лучшая сессия {row['best_session_score']}"
        )


def print_sample() -> None:
    """Три кадра «левая выше → правая выше → левая выше» = один засчитанный жест."""
    for i, (left_y, right_y) in enumerate([(0.3, 0.7), (0.7, 0.3), (0.3, 0.7)]):
        print(json.dumps(make_message(1730000000000 + i * 300, left_y, right_y)))


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--url", default="http://localhost:8000", help="адрес backend")
    parser.add_argument("--name", default="tester", help="имя игрока")
    parser.add_argument("--duration", type=float, default=5, help="сколько секунд слать кадры")
    parser.add_argument("--fps", type=int, default=15)
    parser.add_argument("--frequency", type=float, default=1.5, help="полных циклов «качелей» в секунду")
    parser.add_argument("--no-stop", action="store_true", help="не вызывать «Стоп», просто оборвать сокет")
    parser.add_argument("--print-sample", action="store_true", help="напечатать 3 сообщения и выйти")
    args = parser.parse_args()

    if args.print_sample:
        print_sample()
    else:
        asyncio.run(run(args))


if __name__ == "__main__":
    main()
