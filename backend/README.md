# Backend

FastAPI-приложение главного экрана: REST (игрок, сессия, рейтинг), WebSocket с кадрами, правила игры и хранение результатов в PostgreSQL.

Ответственный разработчик: Виталий

Контракты: [REST и CV](../docs/contracts.md), [WebSocket](../docs/websocket.md), [схема БД](../docs/db-schema.md).

- `app/main.py` — сборка приложения (`create_app`), запуск фоновой задачи таймаутов.
- `app/api/` — REST: `POST /players`, `POST /sessions`, `POST /sessions/{id}/stop`, `GET /ratings`, `GET /health`.
- `app/websocket/` — WebSocket `/ws/sessions/{session_id}`.
- `app/schemas/` — формат запросов, ответов и сообщений WebSocket.
- `app/services/game.py` — окно кадров, вызов CV и анти-дребезг (cooldown).
- `app/services/connections.py` — открытые сокеты сессий: через них «Стоп» и таймаут присылают `session_state`.
- `app/services/timeouts.py` — фоновая задача, закрывающая зависшие сессии.
- `app/services/vision/` — контракт CV (`detect_gesture`) и заглушка.
- `app/models/`, `app/repositories/` — модели SQLAlchemy и доступ к PostgreSQL.
- `migrations/` — миграции Alembic.
- `scripts/ws_client.py` — тестовый клиент, проходящий весь сценарий без браузера.
- `tests/` — тесты pytest.

## Запуск

Нужны Python 3.11+ и PostgreSQL 13+ (проще всего — через Docker).

1. В корне репозитория создайте `.env` из `.env.example` и поднимите PostgreSQL:

   ```bash
   cp .env.example .env
   docker compose up -d db
   ```

   Если порт 5432 уже занят локальным PostgreSQL, поставьте в `.env` `POSTGRES_PORT=5433`.

2. В `backend/` установите зависимости и примените миграции:

   ```bash
   python -m venv .venv
   .venv\Scripts\activate          # Windows; Linux/macOS: source .venv/bin/activate
   pip install -r requirements-dev.txt
   alembic upgrade head
   ```

3. Запустите сервер: `uvicorn app.main:app --reload`. Описание REST — на http://localhost:8000/docs.

Сервер нужно запускать одним процессом (без `--workers`): открытые сокеты хранятся в памяти процесса.

## Настройки

Читаются из `.env` в корне репозитория или из переменных окружения, все необязательны.

| Переменная | По умолчанию | Назначение |
| --- | --- | --- |
| `COOLDOWN_MS` | `1500` | Минимальный интервал между засчитанными жестами. |
| `FRAME_WINDOW_SIZE` | `30` | Сколько последних кадров передаётся в CV. |
| `ACTIVITY_TOUCH_INTERVAL_SECONDS` | `2` | Как часто кадры обновляют `last_activity_at` в БД. |
| `SESSION_TIMEOUT_SECONDS` | `30` | Через сколько секунд без активности сессия получает статус `timeout`. |
| `TIMEOUT_CHECK_INTERVAL_SECONDS` | `5` | Как часто фоновая задача ищет зависшие сессии. |
| `CORS_ORIGINS` | `["http://localhost:5173","http://127.0.0.1:5173"]` | Адреса frontend, JSON-список. |

## Проверка без браузера

При запущенном сервере в другом терминале из `backend/`:

```bash
python scripts/ws_client.py --name Vasya
```

Скрипт создаёт игрока и сессию, 5 секунд шлёт в WebSocket кадры, на которых руки «качаются» вверх-вниз, нажимает «Стоп» и печатает рейтинг:

```text
POST /players -> {'player_id': '...', 'name': 'Vasya', 'created_at': '...'}
POST /sessions -> {'session_id': '...', 'status': 'active', 'score': 0, 'started_at': '...'}
<- session_ready: {'type': 'session_ready', 'session_id': '...', 'status': 'active', 'score': 0}
<- gesture_detected: {'type': 'gesture_detected', 'score': 1, 'detected_at': '...', 'cooldown_ms': 1500}
<- gesture_detected: {'type': 'gesture_detected', 'score': 2, 'detected_at': '...', 'cooldown_ms': 1500}
<- gesture_detected: {'type': 'gesture_detected', 'score': 3, 'detected_at': '...', 'cooldown_ms': 1500}
<- session_state: {'type': 'session_state', 'status': 'stopped', 'score': 3, 'ended_at': '...'}
GET /ratings ->
  1. Vasya: всего 3, лучшая сессия 3
```

Жесты засчитываются раз в 1,5 секунды — это работает cooldown.

- `--no-stop` — оборвать сокет без «Стоп»: через ~30 секунд сессия получит статус `timeout`.
- `--print-sample` — напечатать три готовых сообщения `frame` для Postman или websocat: после третьего придёт `gesture_detected`.
- Остальные параметры (`--duration`, `--fps`, `--frequency`, `--url`) — в `python scripts/ws_client.py --help`.

Данные в PostgreSQL (из корня репозитория):

```bash
docker compose exec db psql -U six_seven -d six_seven -c "select id, status, score, started_at, ended_at from sessions order by started_at desc limit 5;"
```

## Тесты

```bash
pytest
ruff check . && ruff format --check .
```

`tests/test_postgres_repository.py` работает с настоящей БД и пропускается, если PostgreSQL не запущен или миграции не применены. Остальным тестам БД не нужна: они используют хранилище в памяти (`tests/fakes.py`).

## Подключение настоящего CV-модуля

Сейчас вместо CV работает заглушка `app/services/vision/stub.py`: она считает жестом «качели» — два взмаха подряд, когда выше оказывается то левая, то правая рука (сравнивается высота запястий).

Настоящий модуль должен дать функцию с той же сигнатурой — `detect_gesture(frames: list[dict]) -> dict`, подробности в [contracts.md](../docs/contracts.md). Чтобы подключить её, замените `default_detect_gesture` в `app/services/vision/__init__.py`. Буфер кадров, cooldown, запись в БД и WebSocket менять не нужно.
