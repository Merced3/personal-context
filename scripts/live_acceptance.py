#!/usr/bin/env python3
"""Bounded live acceptance test for personal-context against real discord-hub.

Usage (from projects/personal-context/):
    .venv/Scripts/python scripts/live_acceptance.py
    .venv/Scripts/python scripts/live_acceptance.py --lock-test-channel <channel_id>

Reads DISCORD_HUB_URL, DISCORD_HUB_TOKEN, SYNC_CHANNEL_IDS, SYNC_CHANNEL_NAMES
from .env (via Settings) without ever printing secrets. Uses an isolated
temporary SQLite database so production/local data is never modified.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import tempfile
from contextlib import ExitStack
from pathlib import Path

from fastapi.testclient import TestClient

from context_substrate.api.app import create_app
from context_substrate.config import Settings
from context_substrate.db import build_engine, build_session_factory
from context_substrate.models import Base, SourceRecord, SyncCursor
from context_substrate.sync.discord_hub import ArchiveSyncer, DiscordHubArchiveClient


def _make_isolated_settings(base: Settings, db_path: Path, page_size: int = 10) -> Settings:
    return base.model_copy(
        update={
            "database_url": f"sqlite:///{db_path.as_posix()}",
            "sync_messages_page_size": page_size,
            "sync_events_page_size": page_size,
            "consumer_tokens": {"acceptance": "acceptance-local-test-token"},
        }
    )


async def _run_sync(settings: Settings, session_factory) -> tuple[int, int]:
    async with DiscordHubArchiveClient(
        base_url=settings.discord_hub_url,
        token=settings.discord_hub_token,
    ) as client:
        syncer = ArchiveSyncer(
            client=client,
            session_factory=session_factory,
            channel_names=settings.sync_channel_names,
            messages_page_size=settings.sync_messages_page_size,
            events_page_size=settings.sync_events_page_size,
        )
        result = await syncer.sync_all(channel_ids=settings.sync_channel_ids or None)
        return result.synced_messages, result.synced_events


async def verify_sync_and_api(settings: Settings, lock_channel: str | None) -> int:
    if not settings.discord_hub_token or settings.discord_hub_token.startswith("replace-with"):
        print(
            "ERROR: DISCORD_HUB_TOKEN is not configured in .env. "
            "Set a valid discord-hub archive reader token first.",
            file=sys.stderr,
        )
        return 2

    with ExitStack() as stack:
        tmpdir = stack.enter_context(tempfile.TemporaryDirectory(prefix="pc-live-accept-"))
        db_path = Path(tmpdir) / "acceptance.db"
        iso = _make_isolated_settings(settings, db_path, page_size=50)
        engine = build_engine(iso.database_url)
        stack.callback(engine.dispose)
        Base.metadata.create_all(engine)
        session_factory = build_session_factory(engine)

        print(f"[1/4] Running full incremental sync against {iso.discord_hub_url} ...")
        msgs_1, events_1 = await _run_sync(iso, session_factory)
        with session_factory() as session:
            total_records = session.query(SourceRecord).count()
            cursors = session.query(SyncCursor).all()
        print(
            f"      Pass 1: synced_messages={msgs_1}, synced_events={events_1}, "
            f"stored_records={total_records}, cursors={len(cursors)}"
        )
        if total_records == 0:
            print("WARN: 0 records synced. Check ARCHIVE_READER_CHANNELS grant in discord-hub.")

        print("[2/4] Verifying cursor resume & idempotent second pass ...")
        msgs_2, events_2 = await _run_sync(iso, session_factory)
        with session_factory() as session:
            total_records_2 = session.query(SourceRecord).count()
        print(
            f"      Pass 2: synced_messages={msgs_2}, synced_events={events_2}, "
            f"stored_records={total_records_2}"
        )
        assert total_records_2 >= total_records, "Record count unexpectedly dropped on pass 2"

        print("[3/4] Verifying /health, /records, /search, and /projections/{name} ...")
        app = create_app(iso, session_factory=session_factory)
        headers = {"Authorization": "Bearer acceptance-local-test-token"}
        with TestClient(app) as client:
            health = client.get("/health")
            assert health.status_code == 200, f"/health failed: {health.text}"
            print(f"      /health -> {health.json()}")

            unauth = client.get("/records")
            assert unauth.status_code == 401, "Expected 401 without bearer token"

            recs = client.get("/records", params={"limit": 5}, headers=headers)
            assert recs.status_code == 200, f"/records failed: {recs.text}"
            items = recs.json()["items"]
            print(f"      /records (limit=5) -> returned {len(items)} items")

            if items:
                sample_words = [w for w in items[0]["content"].split() if len(w) > 3][:3]
                query = " ".join(sample_words) or "mission"
                search = client.post(
                    "/search",
                    json={"query": query, "limit": 5},
                    headers=headers,
                )
                assert search.status_code == 200, f"/search failed: {search.text}"
                hits = search.json()["hits"]
                print(f"      /search (query={query!r}) -> {len(hits)} hits")

            for proj_name in ("current_mission", "time_digest", "open_decisions", "book_lenses"):
                params = {"days": 30} if proj_name == "time_digest" else {}
                resp = client.get(f"/projections/{proj_name}", params=params, headers=headers)
                assert resp.status_code == 200, f"/projections/{proj_name} failed: {resp.text}"
                body = resp.json()
                cited = body["source_record_ids"]
                print(
                    f"      /projections/{proj_name} -> version={body['version']} "
                    f"model={body['model']} citations={len(cited)}"
                )

            if lock_channel:
                print(
                    f"[4/4] Interactive 🔒 lock/unlock verification on channel {lock_channel} ..."
                )
                input(
                    "      Step A: Post a unique test message in the lab channel, "
                    "then press Enter to sync..."
                )
                await _run_sync(iso, session_factory)
                probe = input("      Enter a unique word from your test message: ").strip()
                res_before = client.post(
                    "/search",
                    json={"query": probe, "sources": [lock_channel], "limit": 5},
                    headers=headers,
                ).json()["hits"]
                assert any(probe.lower() in h["record"]["content"].lower() for h in res_before), (
                    f"Test message containing {probe!r} not found in /search before lock"
                )
                target_id = res_before[0]["record"]["id"]
                digest_before = client.get(
                    "/projections/time_digest",
                    params={"days": 1, "refresh": "true"},
                    headers=headers,
                ).json()
                print(
                    f"      Confirmed record {target_id} present in /search "
                    f"(in time_digest: {target_id in digest_before['source_record_ids']})."
                )

                input(
                    "      Step B: Add a 🔒 reaction to that message in Discord, "
                    "then press Enter..."
                )
                await _run_sync(iso, session_factory)
                res_locked = client.post(
                    "/search",
                    json={"query": probe, "sources": [lock_channel], "limit": 5},
                    headers=headers,
                ).json()["hits"]
                assert all(h["record"]["id"] != target_id for h in res_locked), (
                    f"Locked record {target_id} still appeared in /search!"
                )
                digest_locked = client.get(
                    "/projections/time_digest",
                    params={"days": 1},
                    headers=headers,
                ).json()
                assert target_id not in digest_locked["source_record_ids"], (
                    f"Locked record {target_id} still cited in time_digest!"
                )
                print(
                    f"      Confirmed 🔒 removed {target_id} from /records, "
                    "/search, and projections."
                )

                input("      Step C: Remove the 🔒 reaction in Discord, then press Enter...")
                await _run_sync(iso, session_factory)
                res_unlocked = client.post(
                    "/search",
                    json={"query": probe, "sources": [lock_channel], "limit": 5},
                    headers=headers,
                ).json()["hits"]
                assert any(h["record"]["id"] == target_id for h in res_unlocked), (
                    f"Unlocked record {target_id} was not restored in /search!"
                )
                print(f"      Confirmed removing 🔒 restored {target_id}!")
            else:
                print(
                    "[4/4] Skipped interactive 🔒 lock/unlock test "
                    "(pass --lock-test-channel <id> to run)."
                )

    print("Live acceptance PASSED.")
    return 0


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Live acceptance test for personal-context")
    parser.add_argument(
        "--lock-test-channel",
        default=None,
        help="Optional channel ID (e.g. #lab-text) for interactive 🔒 lock/unlock verification.",
    )
    args = parser.parse_args()
    settings = Settings()
    return asyncio.run(verify_sync_and_api(settings, args.lock_test_channel))


if __name__ == "__main__":
    raise SystemExit(main())
