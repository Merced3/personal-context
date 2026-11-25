"""discord-hub Archive API (ADR 0012) sync client and local storage upserter."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from context_substrate.models import SourceRecord, SyncCursor

SOURCE_SYSTEM = "discord-hub"
LOCK_EMOJI = "🔒"


@dataclass(frozen=True, slots=True)
class SyncResult:
    synced_messages: int = 0
    synced_events: int = 0
    removed_locked: int = 0


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
    raise ValueError(f"Unsupported datetime value: {value!r}")


def _extract_author(author: Any) -> tuple[str | None, str | None]:
    if author is None:
        return None, None
    if isinstance(author, dict):
        author_id = author.get("id")
        author_name = (
            author.get("display_name")
            or author.get("global_name")
            or author.get("name")
            or author.get("username")
        )
        return (
            str(author_id) if author_id is not None else None,
            str(author_name) if author_name is not None else None,
        )
    return str(author), None


def _is_lock_emoji(emoji: Any) -> bool:
    if not isinstance(emoji, str):
        return False
    return emoji.replace("\ufe0f", "") == LOCK_EMOJI


def _max_numeric_id(a: str | None, b: str | None) -> str | None:
    if a is None:
        return b
    if b is None:
        return a
    return str(max(int(a), int(b)))


def canonical_record_id(channel_id: str | int, message_id: str | int) -> str:
    return f"discord:{channel_id}:{message_id}"


class DiscordHubArchiveClient:
    """HTTP client for discord-hub's authenticated /archive endpoints (ADR 0012)."""

    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        http_client: httpx.AsyncClient | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._owns_client = http_client is None
        self._client = http_client or httpx.AsyncClient(
            base_url=self._base_url,
            timeout=timeout,
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> DiscordHubArchiveClient:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.aclose()

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Accept": "application/json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    async def get_messages(
        self,
        *,
        channel_id: int | None = None,
        limit: int = 50,
        before: int | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": limit}
        if channel_id is not None:
            params["channel_id"] = channel_id
        if before is not None:
            params["before"] = before
        response = await self._client.get(
            f"{self._base_url}/archive/messages",
            params=params,
            headers=self._headers(),
        )
        response.raise_for_status()
        return response.json()

    async def get_events(
        self,
        *,
        channel_id: int | None = None,
        limit: int = 100,
        before: int | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": limit}
        if channel_id is not None:
            params["channel_id"] = channel_id
        if before is not None:
            params["before"] = before
        response = await self._client.get(
            f"{self._base_url}/archive/events",
            params=params,
            headers=self._headers(),
        )
        response.raise_for_status()
        return response.json()


class ArchiveSyncer:
    """Resumable, idempotent syncer from discord-hub Archive API to local storage."""

    def __init__(
        self,
        client: DiscordHubArchiveClient,
        session_factory: sessionmaker[Session],
        *,
        channel_names: dict[str, str] | None = None,
        messages_page_size: int = 50,
        events_page_size: int = 100,
    ) -> None:
        self._client = client
        self._session_factory = session_factory
        self._channel_names = channel_names or {}
        self._messages_page_size = messages_page_size
        self._events_page_size = events_page_size

    async def sync_all(self, channel_ids: list[int] | None = None) -> SyncResult:
        """Sync messages and events for the given channels (or all granted channels if empty)."""
        targets: list[int | None] = list(channel_ids) if channel_ids else [None]
        total_messages = 0
        total_events = 0
        total_removed = 0
        for ch_id in targets:
            msg_count, msg_removed = await self.sync_messages(channel_id=ch_id)
            evt_count, evt_removed = await self.sync_events(channel_id=ch_id)
            total_messages += msg_count
            total_events += evt_count
            total_removed += msg_removed + evt_removed
        return SyncResult(
            synced_messages=total_messages,
            synced_events=total_events,
            removed_locked=total_removed,
        )

    async def sync_messages(self, *, channel_id: int | None = None) -> tuple[int, int]:
        """Paginate /archive/messages, upsert records, checkpoint per page, and reconcile locks."""
        channel_key = str(channel_id) if channel_id is not None else "__all__"

        with self._session_factory() as session:
            cursor = self._get_or_create_cursor(session, channel_key, "messages")
            before: int | None = int(cursor.cursor_before) if cursor.cursor_before else None
            started_from_top = before is None

        synced_count = 0
        seen_record_ids: set[str] = set()

        while True:
            page = await self._client.get_messages(
                channel_id=channel_id,
                limit=self._messages_page_size,
                before=before,
            )
            items: list[dict[str, Any]] = page.get("items") or []
            next_before = page.get("next_before")

            now = _now_utc()
            with self._session_factory() as session:
                cursor = self._get_or_create_cursor(session, channel_key, "messages")
                for item in items:
                    record_id = self._upsert_message(session, item, now)
                    seen_record_ids.add(record_id)
                    synced_count += 1
                    cursor.last_seen_id = _max_numeric_id(cursor.last_seen_id, str(item["id"]))

                cursor.cursor_before = str(next_before) if next_before is not None else None
                if next_before is None:
                    cursor.completed_initial_backfill = True
                    cursor.last_synced_at = now
                session.commit()

            if next_before is None:
                break
            before = int(next_before)

        removed_count = 0
        if started_from_top:
            removed_count = self._reconcile_missing_records(
                channel_id=channel_id,
                seen_record_ids=seen_record_ids,
            )

        return synced_count, removed_count

    async def sync_events(self, *, channel_id: int | None = None) -> tuple[int, int]:
        """Paginate /archive/events, apply edits/deletes/🔒 locks, and checkpoint per page."""
        channel_key = str(channel_id) if channel_id is not None else "__all__"

        with self._session_factory() as session:
            cursor = self._get_or_create_cursor(session, channel_key, "events")
            before: int | None = int(cursor.cursor_before) if cursor.cursor_before else None
            stop_at_id: int | None = (
                int(cursor.last_seen_id)
                if (before is None and cursor.completed_initial_backfill and cursor.last_seen_id)
                else None
            )

        synced_count = 0
        removed_count = 0

        while True:
            page = await self._client.get_events(
                channel_id=channel_id,
                limit=self._events_page_size,
                before=before,
            )
            items: list[dict[str, Any]] = page.get("items") or []
            next_before = page.get("next_before")

            reached_watermark = False
            filtered_items: list[dict[str, Any]] = []
            for item in items:
                if stop_at_id is not None and int(item["id"]) <= stop_at_id:
                    reached_watermark = True
                    continue
                filtered_items.append(item)

            now = _now_utc()
            with self._session_factory() as session:
                cursor = self._get_or_create_cursor(session, channel_key, "events")
                for event in filtered_items:
                    removed_count += self._apply_event(session, event, now)
                    synced_count += 1
                    cursor.last_seen_id = _max_numeric_id(cursor.last_seen_id, str(event["id"]))

                if next_before is None or reached_watermark:
                    cursor.cursor_before = None
                    cursor.completed_initial_backfill = True
                    cursor.last_synced_at = now
                else:
                    cursor.cursor_before = str(next_before)
                session.commit()

            if next_before is None or reached_watermark:
                break
            before = int(next_before)

        return synced_count, removed_count

    def _get_or_create_cursor(
        self, session: Session, channel_key: str, stream: str
    ) -> SyncCursor:
        stmt = select(SyncCursor).where(
            SyncCursor.source_system == SOURCE_SYSTEM,
            SyncCursor.channel_id == channel_key,
            SyncCursor.stream == stream,
        )
        cursor = session.execute(stmt).scalar_one_or_none()
        if cursor is None:
            cursor = SyncCursor(
                source_system=SOURCE_SYSTEM,
                channel_id=channel_key,
                stream=stream,
            )
            session.add(cursor)
            session.flush()
        return cursor

    def _upsert_message(
        self, session: Session, item: dict[str, Any], synced_at: datetime
    ) -> str:
        channel_id = str(item["channel_id"])
        message_id = str(item["id"])
        parent_channel_id = (
            str(item["parent_channel_id"]) if item.get("parent_channel_id") is not None else None
        )
        record_id = canonical_record_id(channel_id, message_id)

        author_id, author_name = _extract_author(item.get("author"))
        created_at = _parse_dt(item.get("created_at")) or synced_at
        edited_at = _parse_dt(item.get("edited_at"))
        deleted_at = _parse_dt(item.get("deleted_at"))
        deleted = bool(item.get("deleted", False)) or deleted_at is not None

        source_name = (
            self._channel_names.get(channel_id)
            or (self._channel_names.get(parent_channel_id) if parent_channel_id else None)
        )
        thread_id = channel_id if (parent_channel_id and parent_channel_id != channel_id) else None
        content = item.get("text") if item.get("text") is not None else item.get("content", "")
        attachments = item.get("attachments") or []
        tags = item.get("tags") or []

        existing = session.get(SourceRecord, record_id)
        if existing is None:
            existing = SourceRecord(
                id=record_id,
                source_system=SOURCE_SYSTEM,
                source_channel_id=channel_id,
                parent_channel_id=parent_channel_id,
                source_name=source_name,
                source_message_id=message_id,
                thread_id=thread_id,
                thread_title=item.get("thread_title"),
                author_id=author_id,
                author_name=author_name,
                content=str(content),
                created_at=created_at,
                edited_at=edited_at,
                deleted=deleted,
                deleted_at=deleted_at,
                tags_json=json.dumps(tags),
                attachments_json=json.dumps(attachments),
                synced_at=synced_at,
            )
            session.add(existing)
        else:
            existing.parent_channel_id = parent_channel_id
            if source_name is not None:
                existing.source_name = source_name
            existing.thread_id = thread_id
            if item.get("thread_title") is not None:
                existing.thread_title = item.get("thread_title")
            existing.author_id = author_id
            existing.author_name = author_name
            existing.content = str(content)
            existing.created_at = created_at
            existing.edited_at = edited_at
            existing.deleted = deleted
            existing.deleted_at = deleted_at
            existing.tags_json = json.dumps(tags)
            existing.attachments_json = json.dumps(attachments)
            existing.synced_at = synced_at

        return record_id

    def _apply_event(
        self, session: Session, event: dict[str, Any], synced_at: datetime
    ) -> int:
        event_type = str(event.get("event_type", ""))
        message_id = event.get("message_id")
        if message_id is None:
            return 0

        channel_id = event.get("channel_id")
        record = self._find_record(
            session, str(message_id), str(channel_id) if channel_id else None
        )

        if event_type == "reaction_added" and _is_lock_emoji(event.get("emoji")):
            if record is not None:
                session.delete(record)
                return 1
            return 0

        if record is None:
            return 0

        occurred_at = _parse_dt(event.get("occurred_at")) or synced_at
        payload = event.get("payload") or {}

        if event_type == "message_edited":
            new_text = (
                payload.get("after_text")
                if "after_text" in payload
                else payload.get("text", payload.get("content"))
            )
            if new_text is not None:
                record.content = str(new_text)
            record.edited_at = occurred_at
            record.synced_at = synced_at
        elif event_type == "message_deleted":
            record.deleted = True
            record.deleted_at = occurred_at
            record.synced_at = synced_at

        return 0

    def _find_record(
        self, session: Session, message_id: str, channel_id: str | None
    ) -> SourceRecord | None:
        if channel_id is not None:
            direct = session.get(SourceRecord, canonical_record_id(channel_id, message_id))
            if direct is not None:
                return direct
        stmt = select(SourceRecord).where(
            SourceRecord.source_system == SOURCE_SYSTEM,
            SourceRecord.source_message_id == message_id,
        )
        return session.execute(stmt).scalar_one_or_none()

    def _reconcile_missing_records(
        self, *, channel_id: int | None, seen_record_ids: set[str]
    ) -> int:
        """Remove local records no longer exposed by /archive/messages (e.g. newly 🔒-locked)."""
        with self._session_factory() as session:
            stmt = select(SourceRecord.id).where(SourceRecord.source_system == SOURCE_SYSTEM)
            if channel_id is not None:
                stmt = stmt.where(SourceRecord.source_channel_id == str(channel_id))
            local_ids = set(session.execute(stmt).scalars().all())
            stale_ids = local_ids - seen_record_ids
            if not stale_ids:
                return 0
            session.execute(delete(SourceRecord).where(SourceRecord.id.in_(stale_ids)))
            session.commit()
            return len(stale_ids)
