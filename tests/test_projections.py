"""Offline tests for rerunnable, evidence-backed projections."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import select

from context_substrate.api.app import create_app
from context_substrate.config import Settings
from context_substrate.db import build_engine, build_session_factory
from context_substrate.models import Base, ProjectionRecord, SourceRecord
from context_substrate.projections import ExtractionResult, ProjectionEngine
from context_substrate.sync.discord_hub import ArchiveSyncer, DiscordHubArchiveClient


def _make_env(tmp_path: Path):
    db_path = tmp_path / "test_projections.db"
    engine = build_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    session_factory = build_session_factory(engine)
    settings = Settings(
        _env_file=None,
        database_url=f"sqlite:///{db_path}",
        consumer_tokens={"socratic-partner": "tok-socratic"},
        sync_channel_names={
            "100": "mission",
            "200": "my-timeline",
            "300": "reviews",
            "400": "decisions",
            "500": "books",
            "600": "quotes-i-like",
        },
        harness_data_dir=str(tmp_path / "harness"),
    )
    return settings, session_factory, engine


def _seed_rich_records(session_factory, *, now: datetime) -> None:
    records = [
        # #mission
        SourceRecord(
            id="discord:100:1",
            source_system="discord-hub",
            source_channel_id="100",
            source_name="mission",
            source_message_id="1",
            content="Build durable personal tools that compound curiosity.",
            created_at=now - timedelta(days=40),
            deleted=False,
            tags_json="[]",
            attachments_json="[]",
            synced_at=now,
        ),
        # recent #my-timeline (3 days ago)
        SourceRecord(
            id="discord:200:2",
            source_system="discord-hub",
            source_channel_id="200",
            source_name="my-timeline",
            source_message_id="2",
            content="Shipped the projection engine prototype for personal-context.",
            created_at=now - timedelta(days=3),
            deleted=False,
            tags_json="[]",
            attachments_json="[]",
            synced_at=now,
        ),
        # older #my-timeline (20 days ago)
        SourceRecord(
            id="discord:200:3",
            source_system="discord-hub",
            source_channel_id="200",
            source_name="my-timeline",
            source_message_id="3",
            content="Started exploring archive APIs and provenance schemas.",
            created_at=now - timedelta(days=20),
            deleted=False,
            tags_json="[]",
            attachments_json="[]",
            synced_at=now,
        ),
        # recent 📁reviews (5 days ago)
        SourceRecord(
            id="discord:301:4",
            source_system="discord-hub",
            source_channel_id="301",
            parent_channel_id="300",
            source_name="reviews",
            source_message_id="4",
            thread_id="301",
            thread_title="Weekly Review 2026-W47",
            content="Momentum on tooling is strong; need more quiet reading time.",
            created_at=now - timedelta(days=5),
            deleted=False,
            tags_json="[]",
            attachments_json="[]",
            synced_at=now,
        ),
        # 📁decisions — pending thread
        SourceRecord(
            id="discord:401:5",
            source_system="discord-hub",
            source_channel_id="401",
            parent_channel_id="400",
            source_name="decisions",
            source_message_id="5",
            thread_id="401",
            thread_title="Focus on local-first tooling",
            content=(
                "Committing to local-first personal tools for Q4.\n"
                "Prediction: Daily usage will exceed 3x/week within 30 days.\n"
                "Check-back: 2026-12-20"
            ),
            created_at=now - timedelta(days=2),
            deleted=False,
            tags_json=json.dumps(["pending"]),
            attachments_json="[]",
            synced_at=now,
        ),
        # 📁decisions — resolved (not pending)
        SourceRecord(
            id="discord:402:6",
            source_system="discord-hub",
            source_channel_id="402",
            parent_channel_id="400",
            source_name="decisions",
            source_message_id="6",
            thread_id="402",
            thread_title="Old resolved decision",
            content="Switched editor setup.",
            created_at=now - timedelta(days=15),
            deleted=False,
            tags_json=json.dumps(["resolved"]),
            attachments_json="[]",
            synced_at=now,
        ),
        # 📁books
        SourceRecord(
            id="discord:501:7",
            source_system="discord-hub",
            source_channel_id="501",
            parent_channel_id="500",
            source_name="books",
            source_message_id="7",
            thread_id="501",
            thread_title="Thinking in Systems",
            content="Leverage points in feedback loops beat brute-force effort.",
            created_at=now - timedelta(days=10),
            deleted=False,
            tags_json="[]",
            attachments_json="[]",
            synced_at=now,
        ),
        # #quotes-i-like
        SourceRecord(
            id="discord:600:8",
            source_system="discord-hub",
            source_channel_id="600",
            source_name="quotes-i-like",
            source_message_id="8",
            content="To be interesting, you first have to be interested.",
            created_at=now - timedelta(days=1),
            deleted=False,
            tags_json="[]",
            attachments_json="[]",
            synced_at=now,
        ),
        # Deleted record (must never appear)
        SourceRecord(
            id="discord:100:9",
            source_system="discord-hub",
            source_channel_id="100",
            source_name="mission",
            source_message_id="9",
            content="Deleted mission draft.",
            created_at=now - timedelta(days=1),
            deleted=True,
            deleted_at=now,
            tags_json="[]",
            attachments_json="[]",
            synced_at=now,
        ),
    ]
    with session_factory() as session:
        session.add_all(records)
        session.commit()


class MockLLMExtractor:
    """Mocked LLM extractor that can optionally inject invalid citations to test integrity."""

    def __init__(self, *, inject_invalid_id: str | None = None) -> None:
        self.calls: list[tuple[str, list[str], dict[str, Any]]] = []
        self._inject_invalid_id = inject_invalid_id

    def extract(
        self,
        projection_name: str,
        records: list[SourceRecord],
        *,
        params: dict[str, Any],
    ) -> ExtractionResult:
        rec_ids = [r.id for r in records]
        self.calls.append((projection_name, rec_ids, dict(params)))

        cited = list(rec_ids)
        if self._inject_invalid_id:
            cited.append(self._inject_invalid_id)

        return ExtractionResult(
            model="mock-llm-v1",
            data={
                "summary": f"Distilled {projection_name} from {len(records)} records",
                "claims": [
                    {
                        "text": "Claim backed by evidence",
                        "source_record_ids": cited,
                    }
                ],
            },
            source_record_ids=cited,
        )


def test_all_four_projections_and_auth(tmp_path: Path) -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    settings, session_factory, engine = _make_env(tmp_path)
    _seed_rich_records(session_factory, now=now)
    app = create_app(settings, session_factory)
    headers = {"Authorization": "Bearer tok-socratic"}

    with TestClient(app) as client:
        # Auth required
        assert client.get("/projections/current_mission").status_code == 401
        # Unknown projection -> 404
        assert client.get("/projections/does_not_exist", headers=headers).status_code == 404

        # 1. current_mission
        resp = client.get("/projections/current_mission", headers=headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "current_mission"
        assert body["version"] == "1"
        assert body["model"] == "deterministic-extractor-v1"
        assert body["generated_at"].endswith("Z")
        assert "discord:100:1" in body["source_record_ids"]
        assert "discord:200:2" in body["source_record_ids"]
        assert "discord:301:4" in body["source_record_ids"]
        assert "discord:100:9" not in body["source_record_ids"]  # deleted excluded

        # 2. open_decisions
        resp = client.get("/projections/open_decisions", headers=headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "open_decisions"
        assert body["source_record_ids"] == ["discord:401:5"]
        decisions = body["data"]["decisions"]
        assert len(decisions) == 1
        assert decisions[0]["title"] == "Focus on local-first tooling"
        assert decisions[0]["status"] == "pending"
        assert "3x/week" in decisions[0]["prediction"]
        assert decisions[0]["check_back_date"] == "2026-12-20"

        # 3. book_lenses
        resp = client.get("/projections/book_lenses", headers=headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "book_lenses"
        assert set(body["source_record_ids"]) == {"discord:501:7", "discord:600:8"}
        assert body["data"]["lenses"][0]["title"] == "Thinking in Systems"
        assert len(body["data"]["quotes"]) == 1

        # 4. time_digest (default 7 days)
        resp = client.get("/projections/time_digest", headers=headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "time_digest"
        assert "discord:200:2" in body["source_record_ids"]
        assert "discord:200:3" not in body["source_record_ids"]  # 20 days ago

    engine.dispose()


def test_time_digest_window_parameterization(tmp_path: Path) -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    settings, session_factory, engine = _make_env(tmp_path)
    _seed_rich_records(session_factory, now=now)
    app = create_app(settings, session_factory)
    headers = {"Authorization": "Bearer tok-socratic"}

    with TestClient(app) as client:
        # 7-day window excludes 20-day-old record
        r7 = client.get("/projections/time_digest", params={"days": 7}, headers=headers)
        assert r7.status_code == 200
        assert "discord:200:3" not in r7.json()["source_record_ids"]

        # 30-day window includes 20-day-old record
        r30 = client.get("/projections/time_digest", params={"days": 30}, headers=headers)
        assert r30.status_code == 200
        assert "discord:200:3" in r30.json()["source_record_ids"]

        # Explicit since/until window targeting only the 20-day-old record
        since = (now - timedelta(days=22)).isoformat().replace("+00:00", "Z")
        until = (now - timedelta(days=18)).isoformat().replace("+00:00", "Z")
        r_explicit = client.get(
            "/projections/time_digest",
            params={"since": since, "until": until},
            headers=headers,
        )
        assert r_explicit.status_code == 200
        assert r_explicit.json()["source_record_ids"] == ["discord:200:3"]

        # Invalid parameter combinations -> 400
        assert (
            client.get(
                "/projections/time_digest",
                params={"days": 7, "since": since},
                headers=headers,
            ).status_code
            == 400
        )
        assert (
            client.get(
                "/projections/time_digest",
                params={"since": until, "until": since},
                headers=headers,
            ).status_code
            == 400
        )

    engine.dispose()


def test_mocked_llm_citation_integrity_and_rebuildability(tmp_path: Path) -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    settings, session_factory, engine = _make_env(tmp_path)
    _seed_rich_records(session_factory, now=now)

    # Mock LLM attempts to cite a hallucinated / locked record ID
    mock_llm = MockLLMExtractor(inject_invalid_id="discord:999:LOCKED")
    proj_engine = ProjectionEngine(session_factory, extractor=mock_llm)
    app = create_app(settings, session_factory, projection_engine=proj_engine)
    headers = {"Authorization": "Bearer tok-socratic"}

    with TestClient(app) as client:
        first = client.get("/projections/book_lenses", headers=headers)
        assert first.status_code == 200
        body1 = first.json()
        assert body1["model"] == "mock-llm-v1"
        assert "discord:999:LOCKED" not in body1["source_record_ids"]
        assert "discord:999:LOCKED" not in body1["data"]["claims"][0]["source_record_ids"]
        assert set(body1["source_record_ids"]) == {"discord:501:7", "discord:600:8"}
        assert len(mock_llm.calls) == 1

        # Second call hits cache (no extra LLM call)
        second = client.get("/projections/book_lenses", headers=headers)
        assert second.status_code == 200
        assert len(mock_llm.calls) == 1

        # Wipe projections table completely and verify lossless rebuild from synced records
        deleted_count = proj_engine.clear_all()
        assert deleted_count == 1
        rebuilt = client.get("/projections/book_lenses", headers=headers)
        assert rebuilt.status_code == 200
        assert len(mock_llm.calls) == 2
        assert rebuilt.json()["data"] == body1["data"]
        assert rebuilt.json()["source_record_ids"] == body1["source_record_ids"]

    engine.dispose()


def test_lock_event_invalidates_and_rebuilds_projection(tmp_path: Path) -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    settings, session_factory, engine = _make_env(tmp_path)
    mock_llm = MockLLMExtractor()

    # Phase 1: sync two quotes from discord-hub
    phase = {"step": 1}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/archive/messages":
            if phase["step"] == 1:
                items = [
                    {
                        "id": 801,
                        "channel_id": 600,
                        "author": {"id": 1, "name": "Owner"},
                        "text": "Public quote that stays.",
                        "created_at": now.isoformat(),
                    },
                    {
                        "id": 802,
                        "channel_id": 600,
                        "author": {"id": 1, "name": "Owner"},
                        "text": "Private quote that will be locked.",
                        "created_at": now.isoformat(),
                    },
                ]
            else:
                # Message 802 is now 🔒-locked upstream
                items = [
                    {
                        "id": 801,
                        "channel_id": 600,
                        "author": {"id": 1, "name": "Owner"},
                        "text": "Public quote that stays.",
                        "created_at": now.isoformat(),
                    },
                ]
            return httpx.Response(200, json={"items": items, "next_before": None})

        if request.url.path == "/archive/events":
            if phase["step"] == 1:
                return httpx.Response(200, json={"items": [], "next_before": None})
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": 9001,
                            "event_type": "reaction_added",
                            "channel_id": 600,
                            "message_id": 802,
                            "emoji": "🔒",
                            "occurred_at": now.isoformat(),
                        }
                    ],
                    "next_before": None,
                },
            )
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport)
    hub_client = DiscordHubArchiveClient(
        "http://discord-hub.local",
        "hub-token",
        http_client=http_client,
    )
    syncer = ArchiveSyncer(
        hub_client,
        session_factory,
        channel_names=settings.sync_channel_names,
    )
    app = create_app(
        settings,
        session_factory,
        syncer=syncer,
        projection_extractor=mock_llm,
    )
    headers = {"Authorization": "Bearer tok-socratic"}

    with TestClient(app) as client:
        # Initial sync
        assert client.post("/sync", headers=headers).status_code == 200

        # Build projection — cites both 801 and 802
        p1 = client.get("/projections/book_lenses", headers=headers)
        assert p1.status_code == 200
        assert set(p1.json()["source_record_ids"]) == {"discord:600:801", "discord:600:802"}
        assert len(mock_llm.calls) == 1

        # Phase 2: 802 gets 🔒-locked upstream -> sync invalidates cached projection
        phase["step"] = 2
        assert client.post("/sync", headers=headers).status_code == 200

        with session_factory() as session:
            remaining = session.execute(select(ProjectionRecord)).scalars().all()
            assert remaining == []

        # Next GET /projections/book_lenses rebuilds without the locked record
        p2 = client.get("/projections/book_lenses", headers=headers)
        assert p2.status_code == 200
        assert p2.json()["source_record_ids"] == ["discord:600:801"]
        assert len(mock_llm.calls) == 2

    engine.dispose()
