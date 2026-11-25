# Session: 01 — Scaffold & discord-hub Archive Sync

**Date:** 2026-11-25  
**Status:** `completed`

## Original Prompt (DO NOT EDIT — preserved for auditability)

> Build the foundation of `personal-context`:
> 1. Scaffold the Python 3.13+ package (`pyproject.toml` with ruff + pytest dev deps matching the ecosystem standard, `.env.example`, `src/` layout, `tests/`). Keep the working name easy to change (avoid baking `personal-context` into DB schemas or API contracts).
> 2. Implement the local storage layer (Postgres-ready with SQLite local default, Alembic migrations) for synced records, provenance metadata, and per-channel sync cursors.
> 3. Implement the `discord-hub` Archive API sync client consuming `GET /archive/messages` and `GET /archive/events` (ADR 0012) with bearer token auth, resumable pagination, idempotent upserts, edit/delete handling, and strict `🔒` lock removal (locked items must be removed/hidden from local storage).
> 4. Write offline unit/integration tests with mocked HTTP responses proving pagination, idempotency, restart recovery, and `🔒` exclusion.
> 5. Update this session log and `docs/roadmap.md` when complete.

---

## Session Log (Agent-Maintained)

### Status & What Changed
- Completed full scaffold and `discord-hub` Archive API sync foundation:
  - Package & tooling: `pyproject.toml` (Python 3.13+, Hatchling, SQLAlchemy 2.x, Alembic, `httpx`, `pydantic-settings`, `psycopg[binary]`, plus `pytest`, `pytest-asyncio`, `ruff` dev deps), `.env.example`, `.gitignore`.
  - Storage layer: `src/context_substrate/config.py`, `src/context_substrate/db.py`, `src/context_substrate/models.py` (`source_records`, `sync_cursors`), and Alembic migrations (`alembic.ini`, `src/context_substrate/migrations/env.py`, `src/context_substrate/migrations/versions/0001_initial_schema.py`).
  - Sync client: `src/context_substrate/sync/discord_hub.py` (`DiscordHubArchiveClient`, `ArchiveSyncer`, `SyncResult`) consuming `GET /archive/messages` and `GET /archive/events` (ADR 0012).
  - Offline test suite: `tests/test_migrations.py` and `tests/test_sync_discord_hub.py` using `httpx.MockTransport` and temporary SQLite databases.

### Decisions & Why
- **Package name `context_substrate` (`src/context_substrate/`):** Keeps the working name `personal-context` out of Python imports, DB tables (`source_records`, `sync_cursors`), and API contracts so renaming stays cheap.
- **SQLAlchemy 2.x + JSON-serialized `tags_json`/`attachments_json`:** Works identically on SQLite (default for local dev/tests) and Postgres (`postgresql+psycopg://...`) without dialect-specific column hacks in v0.1.
- **Per-page commits & `cursor_before` checkpointing:** Each page of `/archive/messages` and `/archive/events` is committed alongside its `cursor_before` pointer so an interruption mid-pagination resumes cleanly from the exact next page rather than restarting from scratch.
- **Dual-path `🔒` lock removal:** `discord-hub` excludes `private=True` rows from both `/archive/messages` and `/archive/events`. To guarantee locked items never linger locally, `ArchiveSyncer` both (1) deletes records immediately if a `reaction_added` event with `🔒` (normalized for `\ufe0f`) arrives, and (2) reconciles local records against the complete non-private set whenever a top-to-bottom `/archive/messages` pass completes, purging any record no longer exposed upstream (while cleanly re-ingesting it if later unlocked).

### Intentional Weirdness
- **`channel_id = "__all__"` in `sync_cursors`:** When `SYNC_CHANNEL_IDS` is empty and the client calls `/archive/messages` without a `channel_id` filter (syncing all channels granted to its bearer token), the cursor row uses the sentinel `"__all__"` so the unique constraint `(source_system, channel_id, stream)` works cleanly without nullable unique-key differences between SQLite and Postgres.

### Discoveries / Open Questions
- Inspected `discord-hub/src/discord_hub/archive.py` and `api.py` (read-only) to match the exact ADR 0012 wire format: `/archive/messages` returns `text` (not `content`), `deleted_at`, and `next_before` (int or null); `/archive/events` returns `event_type` values `message_edited`, `message_deleted`, `reaction_added`, `reaction_removed` with `emoji` normalized by stripping `\ufe0f`.
- **Known test gaps (critical self-review of Session 01 tests):**
  1. **Mocked HTTP vs. live `discord-hub`:** Tests use `httpx.MockTransport` with hand-written JSON fixtures. If `discord-hub` returns unexpected field types, forum-post/thread shapes (`parent_channel_id` + `thread_title`), or auth errors in production, offline tests won't catch it (deferred to Session 04 live acceptance).
  2. **SQLite only, no Postgres test:** Migrations and queries are only exercised against SQLite; Postgres is stricter about timezone-aware timestamps, types, and constraints.
  3. **No event-pagination / watermark test:** We tested multi-page pagination and restart recovery for `/archive/messages`, but `/archive/events` was only tested on a single page — we didn't directly test multi-page event pagination or stopping at `last_seen_id` on an incremental event sync.
  4. **No thread/forum-post provenance test:** `_upsert_message` derives `thread_id` when `parent_channel_id != channel_id` and falls back to `parent_channel_id` for `source_name`, but none of the 5 tests pass a non-null `parent_channel_id` to verify that path.
  5. **No mid-sync concurrent-write or large-channel test:** We didn't test what happens if a new message arrives *while* a multi-page sync is halfway through, or reconciliation performance on very large channels.

### Verification
- `.venv/Scripts/pytest -v` -> 5 passed (`test_alembic_upgrade_and_downgrade`, `test_pagination_auth_and_idempotency`, `test_restart_recovery_resumes_from_saved_cursor`, `test_edits_deletes_and_lock_removal_via_events`, `test_lock_removal_via_reconciliation_and_unlock_recovery`).
- `.venv/Scripts/ruff check src tests` -> All checks passed.
