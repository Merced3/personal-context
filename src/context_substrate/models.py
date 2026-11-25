"""SQLAlchemy models for synced source records and resumable sync cursors."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class SourceRecord(Base):
    """A single provenance-preserving record synced from an upstream source archive."""

    __tablename__ = "source_records"

    # Canonical ID, e.g. "discord:<channel_id>:<message_id>"
    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    source_system: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_channel_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    parent_channel_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    source_name: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    source_message_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    thread_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    thread_title: Mapped[str | None] = mapped_column(String(255), nullable=True)

    author_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    author_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    tags_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    attachments_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SyncCursor(Base):
    """Per-channel, per-stream resumable sync checkpoint."""

    __tablename__ = "sync_cursors"
    __table_args__ = (
        UniqueConstraint("source_system", "channel_id", "stream", name="uq_sync_cursor_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_system: Mapped[str] = mapped_column(String(64), nullable=False)
    channel_id: Mapped[str] = mapped_column(String(64), nullable=False)
    # "messages" or "events"
    stream: Mapped[str] = mapped_column(String(32), nullable=False)

    # Non-null while paginating backwards through history; cleared when a pass finishes.
    cursor_before: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Highest upstream ID observed for this channel + stream.
    last_seen_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    completed_initial_backfill: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
