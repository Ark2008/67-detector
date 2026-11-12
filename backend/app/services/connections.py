"""Открытые WebSocket-подключения сессий.

Нужны, чтобы REST «Стоп» и фоновая задача таймаутов могли прислать клиенту
`session_state` и закрыть сокет. Реестр живёт в памяти процесса.
"""

import asyncio
import uuid
from contextlib import suppress

from fastapi import WebSocket, WebSocketDisconnect, status

from app.repositories.game import SessionData
from app.schemas.messages import ServerEvent, SessionStateEvent


class Connection:
    """Сокет одной сессии. В него пишут и обработчик кадров, и «Стоп»/таймаут из других задач."""

    def __init__(self, websocket: WebSocket) -> None:
        self._websocket = websocket
        self._lock = asyncio.Lock()
        self.closed = False

    async def send(self, event: ServerEvent) -> None:
        async with self._lock:
            if not self.closed:
                await self._websocket.send_text(event.model_dump_json())

    async def close(
        self, event: ServerEvent | None = None, code: int = status.WS_1000_NORMAL_CLOSURE
    ) -> None:
        """Отправить прощальное событие (если есть) и закрыть сокет. Повторный вызов ничего не делает."""
        async with self._lock:
            if self.closed:
                return
            self.closed = True
            # Клиент мог отключиться раньше — тогда закрывать уже нечего.
            with suppress(RuntimeError, WebSocketDisconnect):
                if event is not None:
                    await self._websocket.send_text(event.model_dump_json())
                await self._websocket.close(code)


class ConnectionRegistry:
    def __init__(self) -> None:
        self._connections: dict[uuid.UUID, Connection] = {}

    def register(self, session_id: uuid.UUID, connection: Connection) -> Connection | None:
        """Запомнить подключение сессии. Вернуть прежнее, если оно было: его нужно закрыть."""
        previous = self._connections.get(session_id)
        self._connections[session_id] = connection
        return previous

    def unregister(self, session_id: uuid.UUID, connection: Connection) -> None:
        # Сессию могло занять новое подключение — чужую запись не трогаем.
        if self._connections.get(session_id) is connection:
            del self._connections[session_id]

    async def close_session(self, session: SessionData) -> None:
        """Сессия завершена: сообщить клиенту итог через `session_state` и закрыть сокет."""
        connection = self._connections.pop(session.id, None)
        if connection is not None:
            await connection.close(session_state_event(session))


def session_state_event(session: SessionData) -> SessionStateEvent:
    return SessionStateEvent(status=session.status, score=session.score, ended_at=session.ended_at)
