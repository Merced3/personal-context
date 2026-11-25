"""Initial schema for source_records and sync_cursors.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-11-25
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial_schema"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "source_records",
        sa.Column("id", sa.String(length=255), nullable=False),
        sa.Column("source_system", sa.String(length=64), nullable=False),
        sa.Column("source_channel_id", sa.String(length=64), nullable=False),
        sa.Column("parent_channel_id", sa.String(length=64), nullable=True),
        sa.Column("source_name", sa.String(length=128), nullable=True),
        sa.Column("source_message_id", sa.String(length=64), nullable=False),
        sa.Column("thread_id", sa.String(length=64), nullable=True),
        sa.Column("thread_title", sa.String(length=255), nullable=True),
        sa.Column("author_id", sa.String(length=64), nullable=True),
        sa.Column("author_name", sa.String(length=255), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("edited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tags_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("attachments_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_source_records_source_system", "source_records", ["source_system"])
    op.create_index("ix_source_records_source_channel_id", "source_records", ["source_channel_id"])
    op.create_index("ix_source_records_parent_channel_id", "source_records", ["parent_channel_id"])
    op.create_index("ix_source_records_source_name", "source_records", ["source_name"])
    op.create_index("ix_source_records_source_message_id", "source_records", ["source_message_id"])
    op.create_index("ix_source_records_thread_id", "source_records", ["thread_id"])
    op.create_index("ix_source_records_created_at", "source_records", ["created_at"])

    op.create_table(
        "sync_cursors",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source_system", sa.String(length=64), nullable=False),
        sa.Column("channel_id", sa.String(length=64), nullable=False),
        sa.Column("stream", sa.String(length=32), nullable=False),
        sa.Column("cursor_before", sa.String(length=64), nullable=True),
        sa.Column("last_seen_id", sa.String(length=64), nullable=True),
        sa.Column(
            "completed_initial_backfill",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_system", "channel_id", "stream", name="uq_sync_cursor_key"),
    )


def downgrade() -> None:
    op.drop_table("sync_cursors")
    op.drop_index("ix_source_records_created_at", table_name="source_records")
    op.drop_index("ix_source_records_thread_id", table_name="source_records")
    op.drop_index("ix_source_records_source_message_id", table_name="source_records")
    op.drop_index("ix_source_records_source_name", table_name="source_records")
    op.drop_index("ix_source_records_parent_channel_id", table_name="source_records")
    op.drop_index("ix_source_records_source_channel_id", table_name="source_records")
    op.drop_index("ix_source_records_source_system", table_name="source_records")
    op.drop_table("source_records")
