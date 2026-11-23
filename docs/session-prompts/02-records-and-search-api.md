# Session: 02 — Read & Search HTTP API

**Date:** *(filled in when session starts)*  
**Status:** `not-started`

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
- (not started)

### Decisions & Why
-

### Intentional Weirdness
-

### Discoveries / Open Questions
-

### Verification
-
