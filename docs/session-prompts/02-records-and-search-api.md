# Session: 02 — Read & Search HTTP API

**Date:** 2026-11-25  
**Status:** `done`

## Original Prompt (DO NOT EDIT — preserved for auditability)

> Build the consumer-agnostic HTTP API for `personal-context` per `docs/api-contract.md`:
> 1. Implement the FastAPI app with:
>    - `GET /health` (liveness, `last_sync_at`, `record_count`)
>    - `GET /records` (filter by `source`, `since`, `until`, `thread_id`, `limit`, `cursor`)
>    - `POST /search` (hybrid keyword + semantic retrieval with source/time filters and full provenance)
>    - `POST /sync` (operator/internal trigger for immediate incremental sync)
> 2. Add per-consumer bearer token authentication (all endpoints except `/health`).
> 3. Integrate `automation-harness` for runtime lifecycle (single-instance lock, graceful shutdown, scheduled background sync, structured logs, status snapshot).
> 4. Write offline tests covering auth, filtering, pagination, search ranking/provenance, and `🔒` exclusion.
> 5. Update this session log and `docs/roadmap.md` when complete.

---

## Session Log (Agent-Maintained)

### Status & What Changed
- Completed the consumer-agnostic HTTP API and `automation-harness` runtime integration:
  - Added `fastapi>=0.115`, `uvicorn>=0.30`, and `automation-harness>=0.5.0` to `pyproject.toml`.
  - Extended `src/context_substrate/config.py` and `.env.example` with API host/port, per-consumer `CONSUMER_TOKENS`, `SYNC_INTERVAL_SECONDS`, `HARNESS_DATA_DIR`, `HARNESS_DATABASE_URL`, and `SEARCH_SEMANTIC_WEIGHT`.
  - Implemented fail-closed per-consumer bearer token auth in `src/context_substrate/api/auth.py` using `hmac.compare_digest`.
  - Implemented Pydantic request/response schemas matching `docs/api-contract.md` in `src/context_substrate/api/schemas.py`.
  - Implemented FastAPI app factory in `src/context_substrate/api/app.py` with `GET /health`, `GET /records` (filtering by repeatable `source`, `since`, `until`, `thread_id`, `limit`, opaque keyset `cursor`), `POST /search`, and `POST /sync` (serialized with an `asyncio.Lock`).
  - Implemented hybrid keyword + semantic search in `src/context_substrate/search.py` with a pluggable `TextEmbedder` protocol and deterministic offline `HashedNgramEmbedder`.
  - Integrated `automation-harness` in `src/context_substrate/runtime.py` (`build_harness`, `run_service`) and CLI entry point `src/context_substrate/__main__.py`, hosting the scheduled `archive_sync` job and supervised `http_api` uvicorn service.
  - Added offline test suite in `tests/test_api.py` covering auth, filtering, pagination, search ranking/provenance, manual sync + `🔒` exclusion, and `automation-harness` registration.

### Decisions & Why
- **Offline deterministic `HashedNgramEmbedder` behind a `TextEmbedder` protocol:** Keeps hybrid keyword + semantic search working completely offline with zero external API keys or heavy ML dependencies in v0.1, while making it trivial to swap in dense embeddings (e.g. pgvector / OpenAI / local model) later without changing the API contract.
- **Keyset pagination (`created_at DESC, id DESC`) with base64 JSON cursor:** Stable under concurrent sync inserts and portable across both SQLite and Postgres.
- **Fail-closed bearer auth:** If `CONSUMER_TOKENS` is empty, all protected endpoints return `401` rather than silently allowing unauthenticated access.
- **Shared `asyncio.Lock` between `POST /sync` and scheduled `archive_sync` job:** Prevents concurrent sync runs from racing on `sync_cursors` or duplicating upstream calls.

### Intentional Weirdness
- `server.install_signal_handlers = lambda: None` in `src/context_substrate/runtime.py`: Intentionally disables uvicorn's own SIGINT/SIGTERM handlers so `automation-harness` owns process shutdown, sets `ctx.stop_event`, and cleanly flips `server.should_exit = True`.
- `Annotated[..., NoDecode]` on `sync_channel_ids`, `sync_channel_names`, and `consumer_tokens` in `src/context_substrate/config.py`: Prevents `pydantic-settings` from calling `json.loads("")` on empty `.env` values before our custom validators run.
- `Depends(require_consumer)` without `Annotated` in `create_app`: Because `app.py` uses `from __future__ import annotations`, `Annotated[str, Depends(require_consumer)]` would fail to resolve the local closure variable `require_consumer` in module globals.

### Discoveries / Open Questions
- `automation-harness` `status()` returns `{"harness": <name>, "services": {...}, "schedules": [...], ...}` (not `"name"`/`"jobs"`).
- `POST /search` currently loads filtered candidate records in Python and ranks them; when record counts grow large, Postgres full-text search + `pgvector` can replace the candidate scan behind the same API contract.
- **Critical review / known test gaps (to tighten in Session 04 / live acceptance):**
  - *Synthetic search data & embedder limits:* Search tests use 5 clean sentences; the offline `HashedNgramEmbedder` captures word/subword overlap rather than true semantic synonyms (e.g., `"resigning"` vs `"quitting my job"`), which will need real embeddings later.
  - *SQLite vs. Postgres:* Offline tests run on SQLite; Postgres-specific behavior (timezone handling, query performance at scale) is not yet exercised.
  - *Shallow harness test:* `test_build_harness_registers_job_and_service` verifies registration only, not live loop startup, port binding, scheduled execution, or `stop_event` shutdown.
  - *Untested edge cases:* Concurrent `POST /sync` calls (lock serialization), identical `created_at` timestamp tie-breaking in cursor pagination, and upstream `discord-hub` 5xx/timeout error handling.

### Verification
- `pytest -v`: 12 passed (7 new API/harness tests in `tests/test_api.py` + 5 existing migration/sync tests).
- `ruff check .`: All checks passed.
