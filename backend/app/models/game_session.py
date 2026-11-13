import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class SessionStatus(StrEnum):
    ACTIVE = "active"
    STOPPED = "stopped"
    TIMEOUT = "timeout"


class GameSession(Base):
    """Сессия демонстрации: от «Старт» до «Стоп» или таймаута. Таблица `sessions`."""

    __tablename__ = "sessions"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'stopped', 'timeout')", name="status"),
        CheckConstraint("score >= 0", name="score"),
        Index("sessions_player_idx", "player_id"),
        # Для фоновой задачи, закрывающей зависшие сессии.
        Index("sessions_active_watch_idx", "status", "last_activity_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    player_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("players.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(10), server_default=SessionStatus.ACTIVE.value)
    score: Mapped[int] = mapped_column(server_default="0")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_activity_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
