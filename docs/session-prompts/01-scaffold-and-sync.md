# Session: 01 — Scaffold & discord-hub Archive Sync

**Date:** *(filled in when session starts)*  
**Status:** `not-started`

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
- (not started)

### Decisions & Why
-

### Intentional Weirdness
-

### Discoveries / Open Questions
-

### Verification
-
