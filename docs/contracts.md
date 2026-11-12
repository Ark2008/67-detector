# Контракты модулей

| Откуда | Куда | Назначение | Статус |
| --- | --- | --- | --- |
| Frontend | Backend | REST: игрок и сессия | см. ниже |
| Frontend | Backend | WebSocket: кадры и жест | [websocket.md](websocket.md) |
| Backend | CV | Python-вызов: ключевые точки → жест | см. ниже |
| Backend | PostgreSQL | Запись результатов и чтение рейтинга | [db-schema.md](db-schema.md) |

## REST: Frontend → Backend (главный экран)

### `POST /players`

Вход/первый визит. Идемпотентно по имени: если игрок с таким именем уже есть — возвращает существующего.

```json
// запрос
{ "name": "Петя" }

// ответ 200/201
{ "player_id": "uuid", "name": "Петя", "created_at": "2026-11-05T12:00:00Z" }
```

Фронт сохраняет `player_id` в localStorage и дальше всегда попадает на экран демонстрации без повторного ввода имени.

### `POST /sessions`

Кнопка «Старт».

```json
// запрос
{ "player_id": "uuid" }

// ответ 201
{ "session_id": "uuid", "status": "active", "score": 0, "started_at": "..." }
```

Дальше фронт открывает WebSocket на `session_id` (см. [websocket.md](websocket.md)).

### `POST /sessions/{session_id}/stop`

Кнопка «Стоп». Идемпотентен: повторный вызов возвращает текущее финальное состояние без создания новой сессии (реализация — [db-schema.md](db-schema.md)).

```json
// ответ 200
{ "session_id": "uuid", "status": "stopped", "score": 7, "started_at": "...", "ended_at": "..." }
```

### `GET /ratings`

Экран рейтинга.

```json
// ответ 200
{
  "players": [
    { "player_id": "uuid", "name": "Петя", "total_score": 42, "best_session_score": 12 }
  ]
}
```

Сортировка по `total_score` убывающая, на стороне backend ([db-schema.md](db-schema.md)).

## Backend → CV

Жест «шесть-семь» показывается двумя руками (попеременное движение, как качели), поэтому backend передаёт в CV-модуль последовательность кадров, где в каждом кадре могут быть landmarks обеих рук (0, 1 или 2 руки на кадр — сколько MediaPipe нашло), а не только одной. CV возвращает решение: распознан жест («six_seven») или нет («none»).

Границы ответственности:
- Порог распознавания применяется внутри CV-модуля — CV уже отдаёт финальное решение, backend его не пересчитывает.
- CV не знает про сессии и cooldown — только классифицирует окно кадров.
- Решение «засчитать очко» (cooldown, запись в БД, WS-событие) принимает backend — правило анти-дребезга описано в [websocket.md](websocket.md).
- Backend отвечает за размер скользящего окна кадров, передаваемого в CV.

### Python API

`from cv.gesture_detector import detect_gesture`

`detect_gesture(frames)` возвращает `{"gesture": "six_seven"}` или
`{"gesture": "none"}`. Вход — список сообщений `frame` из websocket.md
с возрастающими `timestamp_ms`. В каждой руке обязательны `handedness`,
`score`, 21 объект `landmarks` с конечными x/y/z; x/y в [0, 1].
Left/Right не должны повторяться в одном кадре. Порог надёжности score — 0.5.
Неверная структура вызывает `ValueError` (backend: `invalid_payload`).
Оценивается последний кадр с историей. Пустое окно возвращает `none`.
Вызовы независимы; backend хранит своё окно на каждую сессию.
Начальный ориентир окна — 2 секунды при 15–20 FPS.

Без дополнительных данных проверяется движение, без ориентации ладоней.
Опциональный `DetectorConfig(palm_check="up")` требует у каждой руки
`world_landmarks` — 21 мировую 3D-точку MediaPipe. Это расширение необходимо
согласовать с источником координат. Если точек нет, строгий режим вернёт `none`.
Подробности — [cv/README.md](../cv/README.md).
