# Backend

FastAPI-приложение для HTTP, WebSocket, правил игры и доступа к результатам. Сейчас доступен только `GET /health`.

Ответственный разработчик: Виталий

- `app/api/` — HTTP endpoints.
- `app/websocket/` — WebSocket endpoint и обработчики.
- `app/services/` — игровая логика и вызов CV.
- `app/models/` — модели данных.
- `app/repositories/` — доступ к PostgreSQL.
- `tests/` — тесты pytest.

Запуск из `backend/`: `pip install -r requirements.txt`, затем `uvicorn app.main:app --reload`.

