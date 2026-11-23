# Session: 03 — Rerunnable Projections

**Date:** *(filled in when session starts)*  
**Status:** `not-started`

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
- (not started)

### Decisions & Why
-

### Intentional Weirdness
-

### Discoveries / Open Questions
-

### Verification
-
