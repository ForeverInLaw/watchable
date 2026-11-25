"""notification events and deliveries

Revision ID: 0001
Revises:
Create Date: 2026-11-25 14:16:31.567676

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
    op.create_table(
        "notification_events",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("android_device_id", sa.Text(), nullable=False),
        sa.Column("source_package", sa.Text(), nullable=False),
        sa.Column("source_app", sa.Text(), nullable=True),
        sa.Column("notification_key", sa.Text(), nullable=False),
        sa.Column("group_key", sa.Text(), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("body_full", sa.Text(), nullable=True),
        sa.Column("category", sa.Text(), nullable=True),
        sa.Column("posted_at", sa.Text(), nullable=False),
        sa.Column("replyable", sa.Integer(), server_default="0", nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("notification_events", schema=None) as batch_op:
        batch_op.create_index(
            "ix_notification_events_android_device_id_created_at",
            ["android_device_id", "created_at"],
            unique=False,
        )

    op.create_table(
        "deliveries",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("event_id", sa.Text(), nullable=False),
        sa.Column("watch_device_id", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("apns_id", sa.Text(), nullable=True),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("next_attempt_at", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["notification_events.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id", "watch_device_id"),
    )
    with op.batch_alter_table("deliveries", schema=None) as batch_op:
        batch_op.create_index(
            "ix_deliveries_status_next_attempt_at", ["status", "next_attempt_at"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("deliveries", schema=None) as batch_op:
        batch_op.drop_index("ix_deliveries_status_next_attempt_at")

    op.drop_table("deliveries")
    with op.batch_alter_table("notification_events", schema=None) as batch_op:
        batch_op.drop_index("ix_notification_events_android_device_id_created_at")

    op.drop_table("notification_events")
