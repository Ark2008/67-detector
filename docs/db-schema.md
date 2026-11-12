# Схема БД (PostgreSQL)

Покрывает главный экран: вход игрока, сессия демонстрации, засчитанные жесты. Рейтинг строится агрегацией по `sessions`, отдельной таблицы для него не нужно.

Схема создаётся миграцией Alembic `backend/migrations/versions/0001_create_main_screen_schema.py` (`alembic upgrade head` из `backend/`), модели — в `backend/app/models/`.

## ER-схема

```text
players (1) ──< sessions (N) ──< gesture_events (N)
```

- Один игрок — много сессий (повторные визиты, несколько «Старт/Стоп»).
- Одна сессия — много событий жеста (каждое увеличение счётчика на 1).

## players

| Поле | Тип | Ограничения | Назначение |
| --- | --- | --- | --- |
| id | UUID | PK, default `gen_random_uuid()` | id хранится в браузере (localStorage), по нему опознаётся повторный визит |
| name | VARCHAR(50) | NOT NULL, UNIQUE (по `lower(name)`) | имя из формы входа |
| created_at | TIMESTAMPTZ | NOT NULL, default `now()` | — |

Уникальность имени без учёта регистра — через индекс `CREATE UNIQUE INDEX ON players (lower(name));`.

## sessions

| Поле | Тип | Ограничения | Назначение |
| --- | --- | --- | --- |
| id | UUID | PK, default `gen_random_uuid()` | |
| player_id | UUID | NOT NULL, FK → players(id) ON DELETE CASCADE | |
| status | VARCHAR(10) | NOT NULL, default `'active'`, CHECK IN (`active`, `stopped`, `timeout`) | жизненный цикл сессии |
| score | INT | NOT NULL, default `0`, CHECK (`score >= 0`) | счётчик засчитанных жестов |
| started_at | TIMESTAMPTZ | NOT NULL, default `now()` | момент нажатия «Старт» |
| ended_at | TIMESTAMPTZ | NULL | момент «Стоп» или срабатывания таймаута |
| last_activity_at | TIMESTAMPTZ | NOT NULL, default `now()` | обновляется на жест и на кадры (не чаще раза в ~2 с, см. [websocket.md](websocket.md)), нужен для watcher'а таймаутов |

Индексы: `(player_id)`, `(status, last_activity_at)` — для фоновой задачи, закрывающей зависшие сессии.

**Идемпотентность «Стоп»**: эндпоинт делает `UPDATE sessions SET status='stopped', ended_at=now() WHERE id=$1 AND status='active'`. Если `status` уже не `active`, строка не меняется — повторный клик возвращает текущее (уже сохранённое) состояние без создания дубликата.

**Таймаут без «Стоп»**: фоновая задача периодически переводит в `timeout` сессии со `status='active'` и `last_activity_at` старше N секунд (например, 30), выставляя `ended_at = last_activity_at` (не `now()`, чтобы не исказить последний засчитанный счёт/время).

## gesture_events

| Поле | Тип | Ограничения | Назначение |
| --- | --- | --- | --- |
| id | BIGSERIAL | PK | |
| session_id | UUID | NOT NULL, FK → sessions(id) ON DELETE CASCADE | |
| detected_at | TIMESTAMPTZ | NOT NULL, default `now()` | момент засчитанного жеста |

## Запрос для рейтинга

```sql
SELECT
  p.id,
  p.name,
  COALESCE(SUM(s.score), 0)      AS total_score,
  COALESCE(MAX(s.score), 0)      AS best_session_score
FROM players p
LEFT JOIN sessions s
  ON s.player_id = p.id AND s.status IN ('stopped', 'timeout')
GROUP BY p.id, p.name
ORDER BY total_score DESC, best_session_score DESC, p.name;
```

Активные (`status = 'active'`) сессии в рейтинг не входят — только завершённые.

## DDL

```sql
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE players (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name       VARCHAR(50) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX players_name_lower_idx ON players (lower(name));

CREATE TABLE sessions (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    player_id         UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    status            VARCHAR(10) NOT NULL DEFAULT 'active'
                        CHECK (status IN ('active', 'stopped', 'timeout')),
    score             INT NOT NULL DEFAULT 0 CHECK (score >= 0),
    started_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at          TIMESTAMPTZ,
    last_activity_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX sessions_player_idx ON sessions (player_id);
CREATE INDEX sessions_active_watch_idx ON sessions (status, last_activity_at);

CREATE TABLE gesture_events (
    id           BIGSERIAL PRIMARY KEY,
    session_id   UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    detected_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX gesture_events_session_idx ON gesture_events (session_id);
```

В миграции ограничения названы по общему правилу проекта (`pk_players`, `fk_sessions_player_id_players`, `ck_sessions_status`, `ck_sessions_score` и т. д.), а не именами PostgreSQL по умолчанию; имена индексов — как в DDL выше. `gen_random_uuid()` встроена в PostgreSQL 13+, `pgcrypto` подключается только ради совместимости со старыми версиями.
