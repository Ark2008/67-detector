import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class GestureEvent(Base):
    """Один засчитанный жест: каждое увеличение счёта сессии на 1."""

    __tablename__ = "gesture_events"
    __table_args__ = (Index("gesture_events_session_idx", "session_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"))
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
