# Session: 04 — Live Acceptance & Deployment

**Date:** *(filled in when session starts)*  
**Status:** `not-started`

## Original Prompt (DO NOT EDIT — preserved for auditability)

> Verify `personal-context` end-to-end against real `discord-hub` archive data and prepare production deployment:
> 1. Provision a dedicated `ARCHIVE_READER_CHANNELS` bearer token in `discord-hub` for `personal-context` covering the 9 personal/Judgment channels & forums.
> 2. Run a bounded live acceptance test (following `Automations/ops/LAB.md` for any test messages/locks):
>    - Verify full incremental sync + cursor resume against `discord-hub`’s real archive.
>    - Verify `🔒` lock addition removes a record from `/records`, `/search`, and projections, and removing `🔒` restores it.
>    - Verify `/projections/{name}` outputs real, accurately cited distillations.
> 3. Prepare deployment wiring (Dockerfile / `ops/compose.yml` entry, Postgres DB provisioning, healthcheck, backups) and add `personal-context` to `Automations/ops/PROJECTS.md`.
> 4. Update this session log and `docs/roadmap.md` when complete.

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
