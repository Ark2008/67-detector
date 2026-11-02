from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

NICKNAME_MAX_LENGTH = 32


class GameSession(Base):
    """Одна игра: WebSocket-подключение игрока от начала до отключения."""

    __tablename__ = "game_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    nickname: Mapped[str] = mapped_column(String(NICKNAME_MAX_LENGTH))
    score: Mapped[int] = mapped_column(server_default="0")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
