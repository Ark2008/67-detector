"""Фоновая задача: закрывает сессии, зависшие без «Стоп» (docs/db-schema.md)."""

import asyncio
import logging

from app.repositories.game import GameRepository
from app.services.connections import ConnectionRegistry

logger = logging.getLogger(__name__)


async def close_timed_out_sessions(
    repository: GameRepository, registry: ConnectionRegistry, timeout_seconds: float
) -> int:
    """Перевести зависшие сессии в timeout и закрыть их сокеты, если они ещё открыты."""
    sessions = await repository.close_timed_out_sessions(timeout_seconds)
    for session in sessions:
        await registry.close_session(session)
    if sessions:
        logger.info("Закрыто по таймауту сессий: %d", len(sessions))
    return len(sessions)


async def run_timeout_watcher(
    repository: GameRepository,
    registry: ConnectionRegistry,
    timeout_seconds: float,
    check_interval_seconds: float,
) -> None:
    while True:
        await asyncio.sleep(check_interval_seconds)
        try:
            await close_timed_out_sessions(repository, registry, timeout_seconds)
        except Exception:
            # Недоступная БД не должна останавливать задачу: попробуем на следующем круге.
            logger.exception("Не удалось закрыть зависшие сессии")
