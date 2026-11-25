"""Pydantic request/response schemas matching docs/api-contract.md."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from context_substrate.models import SourceRecord


def format_utc(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    utc_dt = dt.astimezone(UTC) if dt.tzinfo is not None else dt.replace(tzinfo=UTC)
    return utc_dt.isoformat().replace("+00:00", "Z")


class HealthResponse(BaseModel):
    status: str = "ok"
    last_sync_at: str | None = None
    record_count: int = 0


class RecordItem(BaseModel):
    id: str
    source_system: str
    source_channel_id: str
    source_name: str | None = None
    thread_id: str | None = None
    thread_title: str | None = None
    author_id: str | None = None
    content: str
    created_at: str
    edited_at: str | None = None
    deleted: bool = False
    tags: list[Any] = Field(default_factory=list)
    attachments: list[Any] = Field(default_factory=list)

    @classmethod
    def from_orm_record(cls, record: SourceRecord) -> RecordItem:
        return cls(
            id=record.id,
            source_system=record.source_system,
            source_channel_id=record.source_channel_id,
            source_name=record.source_name,
            thread_id=record.thread_id,
            thread_title=record.thread_title,
            author_id=record.author_id,
            content=record.content,
            created_at=format_utc(record.created_at) or "",
            edited_at=format_utc(record.edited_at),
            deleted=record.deleted,
            tags=json.loads(record.tags_json) if record.tags_json else [],
            attachments=json.loads(record.attachments_json) if record.attachments_json else [],
        )


class RecordsResponse(BaseModel):
    items: list[RecordItem]
    next_cursor: str | None = None


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    sources: list[str] | None = None
    since: datetime | None = None
    until: datetime | None = None
    limit: int = Field(default=15, ge=1, le=200)


class SearchHit(BaseModel):
    score: float
    record: RecordItem


class SearchResponse(BaseModel):
    hits: list[SearchHit]


class SyncResponse(BaseModel):
    synced_messages: int
    synced_events: int
