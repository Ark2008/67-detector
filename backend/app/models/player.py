import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

PLAYER_NAME_MAX_LENGTH = 50


class Player(Base):
    """Игрок. id хранится в браузере (localStorage), по нему опознаётся повторный визит."""

    __tablename__ = "players"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    name: Mapped[str] = mapped_column(String(PLAYER_NAME_MAX_LENGTH))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# Имя уникально без учёта регистра.
Index("players_name_lower_idx", func.lower(Player.__table__.c.name), unique=True)
