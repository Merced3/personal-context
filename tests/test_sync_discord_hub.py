"""Offline unit/integration tests for discord-hub Archive API sync."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlalchemy import select

from context_substrate.db import build_engine, build_session_factory
from context_substrate.models import Base, SourceRecord, SyncCursor
from context_substrate.sync.discord_hub import (
    ArchiveSyncer,
    DiscordHubArchiveClient,
    canonical_record_id,
)


def _make_db(tmp_path: Path):
    engine = build_engine(f"sqlite:///{(tmp_path / 'sync.db').as_posix()}")
    Base.metadata.create_all(engine)
    return engine, build_session_factory(engine)


def _msg(
    msg_id: int,
    channel_id: int = 1001,
    text: str = "hello",
    *,
    edited_at: str | None = None,
    deleted_at: str | None = None,
) -> dict[str, Any]:
    return {
        "id": str(msg_id),
        "channel_id": str(channel_id),
        "parent_channel_id": None,
        "author": {"id": "42", "name": "owner"},
        "text": text,
        "created_at": "2026-11-20T12:00:00Z",
        "edited_at": edited_at,
        "deleted_at": deleted_at,
        "attachments": [],
    }


async def test_pagination_auth_and_idempotency(tmp_path: Path) -> None:
    engine, session_factory = _make_db(tmp_path)
    seen_auth_headers: list[str | None] = []

    pages = {
        None: {
            "items": [_msg(300, text="third"), _msg(200, text="second")],
            "next_before": 200,
        },
        "200": {
            "items": [_msg(100, text="first")],
            "next_before": None,
        },
    }

    def handler(request: httpx.Request) -> httpx.Response:
        seen_auth_headers.append(request.headers.get("Authorization"))
        if request.url.path == "/archive/messages":
            before = request.url.params.get("before")
            return httpx.Response(200, json=pages[before])
        if request.url.path == "/archive/events":
            return httpx.Response(200, json={"items": [], "next_before": None})
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = DiscordHubArchiveClient(
            "http://hub.local", "secret-token", http_client=http_client
        )
        syncer = ArchiveSyncer(
            client,
            session_factory,
            channel_names={"1001": "my-timeline"},
            messages_page_size=2,
        )

        first = await syncer.sync_all(channel_ids=[1001])
        assert first.synced_messages == 3
        assert first.removed_locked == 0

        # Re-running sync on identical data must be idempotent.
        second = await syncer.sync_all(channel_ids=[1001])
        assert second.synced_messages == 3
        assert second.removed_locked == 0

    assert seen_auth_headers
    assert all(h == "Bearer secret-token" for h in seen_auth_headers)

    with session_factory() as session:
        records = session.execute(
            select(SourceRecord).order_by(SourceRecord.source_message_id)
        ).scalars().all()
        assert [r.source_message_id for r in records] == ["100", "200", "300"]
        assert all(r.source_name == "my-timeline" for r in records)
        cursor = session.execute(
            select(SyncCursor).where(SyncCursor.stream == "messages")
        ).scalar_one()
        assert cursor.cursor_before is None
        assert cursor.last_seen_id == "300"
        assert cursor.completed_initial_backfill is True

    engine.dispose()


async def test_restart_recovery_resumes_from_saved_cursor(tmp_path: Path) -> None:
    engine, session_factory = _make_db(tmp_path)
    requested_befores: list[str | None] = []
    fail_once = {"should_fail": True}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path != "/archive/messages":
            return httpx.Response(200, json={"items": [], "next_before": None})
        before = request.url.params.get("before")
        requested_befores.append(before)
        if before is None:
            return httpx.Response(
                200,
                json={"items": [_msg(300), _msg(200)], "next_before": 200},
            )
        if before == "200" and fail_once["should_fail"]:
            fail_once["should_fail"] = False
            return httpx.Response(503, json={"detail": "temporary outage"})
        if before == "200":
            return httpx.Response(
                200,
                json={"items": [_msg(100)], "next_before": None},
            )
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = DiscordHubArchiveClient("http://hub.local", "tok", http_client=http_client)
        syncer = ArchiveSyncer(client, session_factory, messages_page_size=2)

        with pytest.raises(httpx.HTTPStatusError):
            await syncer.sync_messages(channel_id=1001)

        # Page 1 and its checkpoint cursor must be durably persisted.
        with session_factory() as session:
            cursor = session.execute(
                select(SyncCursor).where(SyncCursor.stream == "messages")
            ).scalar_one()
            assert cursor.cursor_before == "200"
            assert cursor.completed_initial_backfill is False

        # Restarting resumes directly from before=200 without re-fetching page 1.
        synced, removed = await syncer.sync_messages(channel_id=1001)
        assert synced == 1
        assert removed == 0

    assert requested_befores == [None, "200", "200"]

    with session_factory() as session:
        ids = set(session.execute(select(SourceRecord.source_message_id)).scalars().all())
        assert ids == {"100", "200", "300"}
        cursor = session.execute(
            select(SyncCursor).where(SyncCursor.stream == "messages")
        ).scalar_one()
        assert cursor.cursor_before is None
        assert cursor.completed_initial_backfill is True

    engine.dispose()


async def test_edits_deletes_and_lock_removal_via_events(tmp_path: Path) -> None:
    engine, session_factory = _make_db(tmp_path)

    messages_payload = {
        "items": [
            _msg(300, text="keep me"),
            _msg(200, text="edit me"),
            _msg(100, text="lock me"),
        ],
        "next_before": None,
    }
    events_payload = {
        "items": [
            {
                "id": "10",
                "event_type": "message_edited",
                "channel_id": "1001",
                "message_id": "200",
                "actor_id": "42",
                "emoji": None,
                "payload": {"after_text": "edited text"},
                "occurred_at": "2026-11-20T12:05:00Z",
            },
            {
                "id": "11",
                "event_type": "message_deleted",
                "channel_id": "1001",
                "message_id": "300",
                "actor_id": "42",
                "emoji": None,
                "payload": {},
                "occurred_at": "2026-11-20T12:06:00Z",
            },
            {
                "id": "12",
                "event_type": "reaction_added",
                "channel_id": "1001",
                "message_id": "100",
                "actor_id": "42",
                "emoji": "🔒\ufe0f",
                "payload": {},
                "occurred_at": "2026-11-20T12:07:00Z",
            },
        ],
        "next_before": None,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/archive/messages":
            return httpx.Response(200, json=messages_payload)
        if request.url.path == "/archive/events":
            return httpx.Response(200, json=events_payload)
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = DiscordHubArchiveClient("http://hub.local", "tok", http_client=http_client)
        syncer = ArchiveSyncer(client, session_factory)
        result = await syncer.sync_all(channel_ids=[1001])

    assert result.synced_messages == 3
    assert result.synced_events == 3
    assert result.removed_locked == 1

    with session_factory() as session:
        # Locked message 100 must be completely gone from local storage.
        assert session.get(SourceRecord, canonical_record_id(1001, 100)) is None

        edited = session.get(SourceRecord, canonical_record_id(1001, 200))
        assert edited is not None
        assert edited.content == "edited text"
        assert edited.edited_at is not None

        deleted = session.get(SourceRecord, canonical_record_id(1001, 300))
        assert deleted is not None
        assert deleted.deleted is True
        assert deleted.deleted_at is not None

    engine.dispose()


async def test_lock_removal_via_reconciliation_and_unlock_recovery(tmp_path: Path) -> None:
    """When discord-hub hides a 🔒-locked message from /archive/messages,
    reconciliation removes it."""
    engine, session_factory = _make_db(tmp_path)
    state = {"messages": [_msg(200, text="public"), _msg(100, text="soon locked")]}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/archive/messages":
            return httpx.Response(200, json={"items": state["messages"], "next_before": None})
        return httpx.Response(200, json={"items": [], "next_before": None})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = DiscordHubArchiveClient("http://hub.local", "tok", http_client=http_client)
        syncer = ArchiveSyncer(client, session_factory)

        # Initial sync ingests both messages.
        await syncer.sync_all(channel_ids=[1001])
        with session_factory() as session:
            assert session.get(SourceRecord, canonical_record_id(1001, 100)) is not None

        # Message 100 is now 🔒-locked upstream, so discord-hub omits it from /archive/messages.
        state["messages"] = [_msg(200, text="public")]
        res_locked = await syncer.sync_all(channel_ids=[1001])
        assert res_locked.removed_locked == 1
        with session_factory() as session:
            assert session.get(SourceRecord, canonical_record_id(1001, 100)) is None
            assert session.get(SourceRecord, canonical_record_id(1001, 200)) is not None

        # Later unlocked upstream -> reappears and is re-synced cleanly.
        state["messages"] = [_msg(200, text="public"), _msg(100, text="unlocked again")]
        await syncer.sync_all(channel_ids=[1001])
        with session_factory() as session:
            restored = session.get(SourceRecord, canonical_record_id(1001, 100))
            assert restored is not None
            assert restored.content == "unlocked again"

    engine.dispose()
