"""create players, sessions, gesture_events

Схема из docs/db-schema.md.

Revision ID: 0001
Revises:
Create Date: 2026-11-10

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # gen_random_uuid() встроена в PostgreSQL 13+, расширение нужно только для более старых версий.
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    op.create_table(
        "players",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_players")),
    )
    op.create_index("players_name_lower_idx", "players", [sa.text("lower(name)")], unique=True)

    op.create_table(
        "sessions",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("player_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=10), server_default="active", nullable=False),
        sa.Column("score", sa.Integer(), server_default="0", nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "last_activity_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint("status IN ('active', 'stopped', 'timeout')", name=op.f("ck_sessions_status")),
        sa.CheckConstraint("score >= 0", name=op.f("ck_sessions_score")),
        sa.ForeignKeyConstraint(
            ["player_id"], ["players.id"], name=op.f("fk_sessions_player_id_players"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sessions")),
    )
    op.create_index("sessions_player_idx", "sessions", ["player_id"])
    op.create_index("sessions_active_watch_idx", "sessions", ["status", "last_activity_at"])

    op.create_table(
        "gesture_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["sessions.id"],
            name=op.f("fk_gesture_events_session_id_sessions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_gesture_events")),
    )
    op.create_index("gesture_events_session_idx", "gesture_events", ["session_id"])


def downgrade() -> None:
    op.drop_table("gesture_events")
    op.drop_table("sessions")
    op.drop_table("players")
