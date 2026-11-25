# Session: 03 — Rerunnable Projections

**Date:** 2026-11-25  
**Status:** `completed`

## Original Prompt (DO NOT EDIT — preserved for auditability)

> Implement rerunnable, evidence-backed projections behind `GET /projections/{name}` per `docs/api-contract.md`:
> 1. Build the projection storage and generation framework: every projection stores `name`, `version`, `generated_at`, `model`, `data`, and `source_record_ids`, and can be regenerated from scratch from synced records without data loss.
> 2. Implement the initial consumer-agnostic projections:
>    - `current_mission` (`#mission` cross-checked against recent `#my-timeline` / `📁reviews`)
>    - `time_digest` (caller-specified window via `?days=N` or `?since=...&until=...`)
>    - `open_decisions` (`pending` posts from `📁decisions` with predictions and check-back dates)
>    - `book_lenses` (mental models from `📁books` and `#quotes-i-like`)
> 3. Ensure `🔒` locked records are never included in projections and trigger invalidation/rebuild if previously cited.
> 4. Write offline tests with mocked LLM/extractor responses proving citation integrity, rebuildability, and window parameterization.
> 5. Update this session log and `docs/roadmap.md` when complete.

---

## Session Log (Agent-Maintained)

### Status & What Changed
- **Completed.** Implemented the rerunnable, evidence-backed projection framework and all four initial consumer-agnostic projections behind `GET /projections/{name}`:
  - Added `ProjectionRecord` model in `src/context_substrate/models.py` and Alembic migration `src/context_substrate/migrations/versions/0002_projections.py` storing `name`, `cache_key`, `version`, `generated_at`, `model`, `data_json`, and `source_record_ids_json`.
  - Created `src/context_substrate/projections.py` with `ProjectionEngine`, `ProjectionExtractor` protocol, `DeterministicProjectionExtractor` (built-in offline-capable default), citation sanitization (`_sanitize_citations`), and `invalidate_projections_citing`.
  - Implemented the four consumer-agnostic projections: `current_mission`, `time_digest` (parameterized via `?days=N` or `?since=...&until=...`), `open_decisions` (`pending`-tagged `decisions` posts with prediction & check-back extraction), and `book_lenses` (`books` + `quotes-i-like`).
  - Wired `🔒` lock invalidation into `src/context_substrate/sync/discord_hub.py` (`_apply_event` on `reaction_added` with `🔒` and `_reconcile_missing_records`), plus lazy self-healing citation validation on read in `ProjectionEngine`.
  - Added `ProjectionResponse` in `src/context_substrate/api/schemas.py` and `GET /projections/{name}` (with per-consumer bearer auth, `?days`, `?since`, `?until`, `?refresh`) in `src/context_substrate/api/app.py`.
  - Added offline test suite in `tests/test_projections.py` covering all four projections, auth/404/400 handling, window parameterization, mocked LLM citation integrity, full rebuildability from scratch, and `🔒` lock invalidation/rebuild.

### Decisions & Why
- **Composite `(name, cache_key)` uniqueness:** Parameterized projections like `time_digest` (`?days=7` vs `?days=30` vs `?since=...&until=...`) need distinct cache slots without changing the API's `name` field. Storing a canonical `cache_key` alongside `name` prevents cache thrashing across consumers with different windows.
- **Two-layer `🔒` invalidation:** `ArchiveSyncer` eagerly deletes any cached projection citing a newly locked/removed record during sync, and `ProjectionEngine` also validates on read that all cited `source_record_ids` still exist and are not `deleted=True`. This ensures locked or deleted records can never linger in cached projections even if records change outside the normal sync path.
- **Strict citation sanitization in the engine (not just the extractor):** `_sanitize_citations` strips any ID not present in the projection's allowed input record set from both top-level `source_record_ids` and nested `source_record_ids` inside `data`, and computes the top-level list as the deduplicated union. This guarantees citation integrity even when a plugged-in LLM hallucinates or attempts to cite an excluded/locked ID.
- **Pluggable `ProjectionExtractor` protocol with deterministic default:** Keeps offline tests fast and zero-dependency while allowing future sessions to plug in an LLM-backed extractor without changing storage, caching, or API contracts.

### Intentional Weirdness
- `time_digest` rejects combining `days` with `since`/`until` (`400 Bad Request`) rather than silently prioritizing one, so callers get explicit feedback on ambiguous window specs.

### Discoveries / Open Questions
- An LLM-backed `ProjectionExtractor` implementation (e.g. OpenAI/Anthropic) can be plugged into `create_app(..., projection_extractor=...)` later without any schema or API changes.
- **Known test coverage gaps (worth hardening before/during Session 04):**
  - Multi-message forum threads in `open_decisions` and `book_lenses` (e.g., `pending` tag on starter message, `Prediction:` / `Check-back:` in a follow-up reply) are not yet directly tested.
  - `?refresh=true` force-rebuild and the lazy `_citations_are_valid` self-healing path (when a cited record is deleted/marked `deleted=True` outside of `ArchiveSyncer`) exist in `ProjectionEngine` but are not yet exercised by dedicated tests.
  - Selective invalidation (proving that locking a record in one source leaves unrelated cached projections intact) is not explicitly asserted.
  - Tests run on SQLite; timezone-aware `DateTime(timezone=True)` and JSON behavior against Postgres will be validated in Session 04 live acceptance.

### Verification
- `.venv/Scripts/pytest -q`: **16 passed** (including `tests/test_projections.py`, `tests/test_api.py`, `tests/test_sync_discord_hub.py`, and `tests/test_migrations.py` covering `0002_projections` upgrade/downgrade).
- `.venv/Scripts/ruff check src tests`: **All checks passed!**
