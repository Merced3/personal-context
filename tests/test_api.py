"""Offline tests for the HTTP API: auth, filtering, pagination, search, sync, 🔒, and harness."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from fastapi.testclient import TestClient

from context_substrate.api.app import create_app
from context_substrate.config import Settings
from context_substrate.db import build_engine, build_session_factory
from context_substrate.models import Base, SourceRecord, SyncCursor
from context_substrate.runtime import build_harness
from context_substrate.sync.discord_hub import ArchiveSyncer, DiscordHubArchiveClient


def _make_test_env(tmp_path: Path, *, consumer_tokens: dict[str, str] | None = None):
    db_path = tmp_path / "test_api.db"
    engine = build_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    session_factory = build_session_factory(engine)
    settings = Settings(
        _env_file=None,
        database_url=f"sqlite:///{db_path}",
        consumer_tokens=(
            consumer_tokens
            if consumer_tokens is not None
            else {"socratic-partner": "tok-socratic", "operator": "tok-operator"}
        ),
        sync_channel_names={
            "100": "my-timeline",
            "200": "decisions",
            "300": "mission",
        },
        harness_data_dir=str(tmp_path / "harness"),
    )
    return settings, session_factory, engine


def _seed_records(session_factory) -> None:
    now = datetime(2026, 11, 20, 18, 0, 0, tzinfo=UTC)
    records = [
        SourceRecord(
            id="discord:100:1",
            source_system="discord-hub",
            source_channel_id="100",
            parent_channel_id=None,
            source_name="my-timeline",
            source_message_id="1",
            thread_id=None,
            thread_title=None,
            author_id="u1",
            author_name="Owner",
            content="Thinking about career direction and evaluating two engineering roles.",
            created_at=datetime(2026, 11, 18, 10, 0, 0, tzinfo=UTC),
            edited_at=None,
            deleted=False,
            tags_json=json.dumps(["career"]),
            attachments_json=json.dumps([]),
            synced_at=now,
        ),
        SourceRecord(
            id="discord:201:2",
            source_system="discord-hub",
            source_channel_id="201",
            parent_channel_id="200",
            source_name="decisions",
            source_message_id="2",
            thread_id="201",
            thread_title="Job search decision Q4",
            author_id="u1",
            author_name="Owner",
            content="Decided to focus on systems engineering roles with strong autonomy.",
            created_at=datetime(2026, 11, 19, 12, 0, 0, tzinfo=UTC),
            edited_at=None,
            deleted=False,
            tags_json=json.dumps(["pending"]),
            attachments_json=json.dumps([]),
            synced_at=now,
        ),
        SourceRecord(
            id="discord:300:3",
            source_system="discord-hub",
            source_channel_id="300",
            parent_channel_id=None,
            source_name="mission",
            source_message_id="3",
            thread_id=None,
            thread_title=None,
            author_id="u1",
            author_name="Owner",
            content="Build durable personal tools that compound curiosity over decades.",
            created_at=datetime(2026, 11, 20, 8, 0, 0, tzinfo=UTC),
            edited_at=None,
            deleted=False,
            tags_json=json.dumps([]),
            attachments_json=json.dumps([]),
            synced_at=now,
        ),
        SourceRecord(
            id="discord:100:4",
            source_system="discord-hub",
            source_channel_id="100",
            parent_channel_id=None,
            source_name="my-timeline",
            source_message_id="4",
            thread_id=None,
            thread_title=None,
            author_id="u1",
            author_name="Owner",
            content="Made sourdough bread and went for a long morning run.",
            created_at=datetime(2026, 11, 20, 15, 0, 0, tzinfo=UTC),
            edited_at=None,
            deleted=False,
            tags_json=json.dumps([]),
            attachments_json=json.dumps([]),
            synced_at=now,
        ),
        SourceRecord(
            id="discord:100:5",
            source_system="discord-hub",
            source_channel_id="100",
            parent_channel_id=None,
            source_name="my-timeline",
            source_message_id="5",
            thread_id=None,
            thread_title=None,
            author_id="u1",
            author_name="Owner",
            content="Deleted draft about career direction.",
            created_at=datetime(2026, 11, 20, 16, 0, 0, tzinfo=UTC),
            edited_at=None,
            deleted=True,
            deleted_at=datetime(2026, 11, 20, 16, 5, 0, tzinfo=UTC),
            tags_json=json.dumps([]),
            attachments_json=json.dumps([]),
            synced_at=now,
        ),
    ]
    with session_factory() as session:
        session.add_all(records)
        session.add(
            SyncCursor(
                source_system="discord-hub",
                channel_id="__all__",
                stream="messages",
                last_synced_at=now,
                completed_initial_backfill=True,
            )
        )
        session.commit()


def test_health_no_auth_required_and_returns_status(tmp_path: Path) -> None:
    settings, session_factory, engine = _make_test_env(tmp_path)
    _seed_records(session_factory)
    app = create_app(settings, session_factory)

    with TestClient(app) as client:
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {
            "status": "ok",
            "last_sync_at": "2026-11-20T18:00:00Z",
            "record_count": 5,
        }
    engine.dispose()


def test_auth_enforced_on_all_protected_endpoints(tmp_path: Path) -> None:
    settings, session_factory, engine = _make_test_env(tmp_path)
    app = create_app(settings, session_factory)

    with TestClient(app) as client:
        # Missing token
        assert client.get("/records").status_code == 401
        assert client.post("/search", json={"query": "career"}).status_code == 401
        assert client.post("/sync").status_code == 401

        # Wrong token
        bad_headers = {"Authorization": "Bearer wrong-token"}
        assert client.get("/records", headers=bad_headers).status_code == 401
        search_bad = client.post("/search", json={"query": "career"}, headers=bad_headers)
        assert search_bad.status_code == 401

        # Valid per-consumer tokens
        socratic_h = {"Authorization": "Bearer tok-socratic"}
        operator_h = {"Authorization": "Bearer tok-operator"}
        assert client.get("/records", headers=socratic_h).status_code == 200
        assert client.get("/records", headers=operator_h).status_code == 200

    # Fail-closed when no consumer tokens are configured
    empty_settings, empty_sf, empty_engine = _make_test_env(tmp_path / "empty", consumer_tokens={})
    empty_app = create_app(empty_settings, empty_sf)
    with TestClient(empty_app) as client:
        any_h = {"Authorization": "Bearer anything"}
        assert client.get("/records", headers=any_h).status_code == 401

    engine.dispose()
    empty_engine.dispose()


def test_records_filtering_and_provenance(tmp_path: Path) -> None:
    settings, session_factory, engine = _make_test_env(tmp_path)
    _seed_records(session_factory)
    app = create_app(settings, session_factory)
    headers = {"Authorization": "Bearer tok-socratic"}

    with TestClient(app) as client:
        # Filter by repeatable source name
        resp = client.get(
            "/records",
            params=[("source", "decisions"), ("source", "mission")],
            headers=headers,
        )
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert [i["id"] for i in items] == ["discord:300:3", "discord:201:2"]

        # Filter by parent channel ID (matches thread child)
        resp = client.get("/records", params={"source": "200"}, headers=headers)
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 1
        rec = items[0]
        assert rec["id"] == "discord:201:2"
        assert rec["source_system"] == "discord-hub"
        assert rec["source_channel_id"] == "201"
        assert rec["source_name"] == "decisions"
        assert rec["thread_id"] == "201"
        assert rec["thread_title"] == "Job search decision Q4"
        assert rec["author_id"] == "u1"
        assert rec["created_at"] == "2026-11-19T12:00:00Z"
        assert rec["tags"] == ["pending"]

        # Filter by thread_id
        resp = client.get("/records", params={"thread_id": "201"}, headers=headers)
        assert [i["id"] for i in resp.json()["items"]] == ["discord:201:2"]

        # Filter by since + until
        resp = client.get(
            "/records",
            params={
                "since": "2026-11-19T00:00:00Z",
                "until": "2026-11-20T10:00:00Z",
            },
            headers=headers,
        )
        assert [i["id"] for i in resp.json()["items"]] == ["discord:300:3", "discord:201:2"]

    engine.dispose()


def test_records_pagination_and_invalid_cursor(tmp_path: Path) -> None:
    settings, session_factory, engine = _make_test_env(tmp_path)
    _seed_records(session_factory)
    app = create_app(settings, session_factory)
    headers = {"Authorization": "Bearer tok-socratic"}

    with TestClient(app) as client:
        collected_ids: list[str] = []
        cursor: str | None = None
        pages = 0
        while True:
            params: dict[str, Any] = {"limit": 2}
            if cursor is not None:
                params["cursor"] = cursor
            resp = client.get("/records", params=params, headers=headers)
            assert resp.status_code == 200
            body = resp.json()
            collected_ids.extend(item["id"] for item in body["items"])
            pages += 1
            cursor = body["next_cursor"]
            if cursor is None:
                break

        assert pages == 3
        assert collected_ids == [
            "discord:100:5",
            "discord:100:4",
            "discord:300:3",
            "discord:201:2",
            "discord:100:1",
        ]

        # Invalid cursor returns 400
        bad_resp = client.get("/records", params={"cursor": "not-valid-base64!!!"}, headers=headers)
        assert bad_resp.status_code == 400

    engine.dispose()


def test_search_hybrid_ranking_filters_and_provenance(tmp_path: Path) -> None:
    settings, session_factory, engine = _make_test_env(tmp_path)
    _seed_records(session_factory)
    app = create_app(settings, session_factory)
    headers = {"Authorization": "Bearer tok-socratic"}

    with TestClient(app) as client:
        resp = client.post(
            "/search",
            json={
                "query": "decisions about job search or career direction",
                "sources": ["my-timeline", "mission", "decisions"],
                "since": "2026-11-01T00:00:00Z",
                "limit": 10,
            },
            headers=headers,
        )
        assert resp.status_code == 200
        hits = resp.json()["hits"]
        assert len(hits) >= 2

        # Top two hits should be the career/job-search records, not sourdough bread
        top_ids = [h["record"]["id"] for h in hits[:2]]
        assert set(top_ids) == {"discord:100:1", "discord:201:2"}
        assert hits[0]["score"] >= hits[1]["score"] > 0.0

        # Deleted record must never appear in search hits
        all_hit_ids = {h["record"]["id"] for h in hits}
        assert "discord:100:5" not in all_hit_ids

        # Source filter narrows hits
        filtered = client.post(
            "/search",
            json={"query": "career direction", "sources": ["mission"], "limit": 10},
            headers=headers,
        )
        assert filtered.status_code == 200
        for hit in filtered.json()["hits"]:
            assert hit["record"]["source_name"] == "mission"

    engine.dispose()


def test_sync_endpoint_and_lock_exclusion_e2e(tmp_path: Path) -> None:
    settings, session_factory, engine = _make_test_env(tmp_path)

    # Stateful mock upstream: first sync returns 2 messages, second sync locks message 20
    sync_round = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/archive/messages":
            if sync_round["n"] == 0:
                items = [
                    {
                        "id": 10,
                        "channel_id": 100,
                        "author": {"id": 1, "display_name": "Owner"},
                        "text": "Public reflection on career growth.",
                        "created_at": "2026-11-20T10:00:00Z",
                    },
                    {
                        "id": 20,
                        "channel_id": 100,
                        "author": {"id": 1, "display_name": "Owner"},
                        "text": "Private secret note about salary negotiation.",
                        "created_at": "2026-11-20T11:00:00Z",
                    },
                ]
            else:
                # Message 20 is now 🔒-locked upstream, so /archive/messages omits it
                items = [
                    {
                        "id": 10,
                        "channel_id": 100,
                        "author": {"id": 1, "display_name": "Owner"},
                        "text": "Public reflection on career growth.",
                        "created_at": "2026-11-20T10:00:00Z",
                    },
                ]
            return httpx.Response(200, json={"items": items, "next_before": None})

        if request.url.path == "/archive/events":
            events = (
                []
                if sync_round["n"] == 0
                else [
                    {
                        "id": 99,
                        "event_type": "reaction_added",
                        "channel_id": 100,
                        "message_id": 20,
                        "emoji": "🔒",
                        "occurred_at": "2026-11-20T12:00:00Z",
                    }
                ]
            )
            return httpx.Response(200, json={"items": events, "next_before": None})

        return httpx.Response(404)

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    archive_client = DiscordHubArchiveClient("http://mock-hub", "tok", http_client=http_client)
    syncer = ArchiveSyncer(
        archive_client,
        session_factory,
        channel_names=settings.sync_channel_names,
    )
    app = create_app(settings, session_factory, syncer=syncer)
    headers = {"Authorization": "Bearer tok-operator"}

    with TestClient(app) as client:
        # First sync: both records present
        r1 = client.post("/sync", headers=headers)
        assert r1.status_code == 200
        assert r1.json() == {"synced_messages": 2, "synced_events": 0}
        assert client.get("/health").json()["record_count"] == 2

        # Second sync: message 20 is 🔒-locked and must be purged from /records and /search
        sync_round["n"] = 1
        r2 = client.post("/sync", headers=headers)
        assert r2.status_code == 200
        assert r2.json() == {"synced_messages": 1, "synced_events": 1}

        assert client.get("/health").json()["record_count"] == 1
        records_resp = client.get("/records", headers=headers).json()["items"]
        assert [r["id"] for r in records_resp] == ["discord:100:10"]

        search_resp = client.post(
            "/search",
            json={"query": "salary negotiation secret"},
            headers=headers,
        ).json()["hits"]
        assert all(h["record"]["id"] != "discord:100:20" for h in search_resp)

    engine.dispose()


def test_build_harness_registers_job_and_service(tmp_path: Path) -> None:
    settings, session_factory, engine = _make_test_env(tmp_path)
    harness = build_harness(settings, session_factory)
    status_snapshot = harness.status()

    assert status_snapshot["harness"] == "context-substrate"
    assert "http_api" in status_snapshot["services"]
    assert "archive_sync" in harness._jobs
    engine.dispose()
