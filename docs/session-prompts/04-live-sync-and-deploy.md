# Session: 04 — Live Acceptance & Deployment

**Date:** 2026-11-25  
**Status:** `completed`

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
- **Completed.** Verified `personal-context` end-to-end against live `discord-hub` archive data (including `🔒` privacy lock exclusion & unlock restoration after fixing an upstream `discord-hub` bug discovered during testing) and wired production deployment infrastructure.
- **Live acceptance harness:** Added `scripts/live_acceptance.py` (isolated temp SQLite DB, tests full incremental sync, cursor resume/idempotency, `/health`, `/records`, `/search`, all 4 `/projections/{name}`, and optional interactive `🔒` lock/unlock). Fixed Windows `cp1252` stdout encoding for emoji output.
- **Deployment wiring & docs:**
  - Added `projects/personal-context/Dockerfile`.
  - Added `Automations/ops/hosts/personal-context/compose.yml` (port `8010`, `700m`, Tailscale + localhost binding, `alembic upgrade head` on startup, `/health` healthcheck).
  - Added `Automations/ops/env/personal-context.env.example`.
  - Registered `personal-context` in `Automations/ops/infra/inventory.sh` (`s-1vcpu-1gb`, port `8010`, `700m`, `24` health attempts) and `Automations/ops/server/healthcheck.sh` (`personal-context-to-hub` Tailscale check).
  - Added `personal_context` and `harness_personal_context` to `OPTIONAL_DATABASE_NAMES` in `Automations/ops/data-platform/data_platform.py` so Postgres provisioning, healthchecks, and nightly R2 backups work automatically once seeded.
  - Updated `projects/personal-context/README.md` ("Why this exists") and `Automations/ops/PROJECTS.md` to clearly explain the human motivation behind `personal-context`.
- **Token provisioning:** Provisioned dedicated `personal-context` bearer token in `discord-hub` (`HUB_PROJECT_TOKENS` + `ARCHIVE_READER_CHANNELS` covering the 9 personal/Judgment channels & forums) and configured `projects/personal-context/.env`.

### Decisions & Why
- **Do NOT add `#lab-text` to `discord-hub`’s `ARCHIVE_CHANNEL_IDS` (testing without polluting production DB):**
  - *What started it:* Planning the live `🔒` lock/unlock acceptance test raised the question of whether to add `#lab-text` to `ARCHIVE_CHANNEL_IDS` so test messages wouldn’t touch real personal channels.
  - *Options considered:*
    1. Add `#lab-text` to `ARCHIVE_CHANNEL_IDS` temporarily (or permanently and ignore it in `personal-context`) — rejected because test messages would still accumulate as noise in `discord-hub`’s production archive table.
    2. Build a scheduled cleanup stored procedure or a rolling 1% storage ceiling in Postgres for `#lab-text` — rejected as unnecessary engineering complexity for a tiny test need.
    3. Provision a separate paid live/test database — rejected as not worth the ongoing cost.
    4. **Chosen (Option B):** Keep `ARCHIVE_CHANNEL_IDS` strictly to the 9 real personal/Judgment channels, and test `🔒` lock/unlock losslessly by toggling `🔒` on a single real message (add `🔒` → verify removed → remove `🔒` → verify restored). Zero noise in production DB, zero extra infra, tests the exact real-world path.
- **Keep `dev-agent` channel setup separate from Session 04:** `personal-context` is a headless HTTP substrate and does not need a Discord channel to run; a `#dev-personal-context` channel can be added later once CI/GHCR builds are wired.

### Intentional Weirdness
- `personal_context` and `harness_personal_context` are placed in `OPTIONAL_DATABASE_NAMES` (not `DATABASE_NAMES`) in `ops/data-platform/data_platform.py` so existing production healthchecks and backups do not fail before the new databases are provisioned and seeded in `data-platform.env`.

### Discoveries / Open Questions
- **CRITICAL UPSTREAM BUG FOUND IN `discord-hub` (`🔒` privacy lock broken in production):**
  - During live `🔒` lock acceptance on `#my-timeline` (channel `1411955142529384530`, message `1575286288737636524`), adding and removing `:lock:` (`🔒`) failed in `discord-hub` with:
    `psycopg.errors.NotNullViolation: null value in column "scope_channel_id" of relation "archive_events" violates not-null constraint`
  - Root cause: `discord-hub/src/discord_hub/bot.py` (`_route_reaction_marker`, around line 804) creates `ArchiveEvent(event_type=f"reaction_{action}", channel_id=event.channel_id, ...)` without passing `scope_channel_id=channel_id`. Because `archive_events.scope_channel_id` is `NOT NULL` in Postgres, every `🔒` reaction add/remove fails to insert and never updates `archive_messages.private`.
  - **Resolved:** Fixed `scope_channel_id=channel_id` in `discord-hub` and redeployed; re-verified `🔒` lock/unlock end-to-end below.

### Verification
- Offline suite: `ruff check src tests scripts` passed; `pytest -q` → **16 passed**.
- Live `discord-hub` acceptance (`scripts/live_acceptance.py` against `http://automations-discord-hub:8100`):
  - Pass 1 (full incremental sync): `1,075` messages synced, `31,700` events synced, `1,075` records stored, `2` cursors saved.
  - Pass 2 (cursor resume & idempotency): `1,075` messages, `0` new events, `1,075` records stored.
  - `GET /health` → `200 OK` (`status: ok`, `record_count: 1075`).
  - `GET /records` → `401` without bearer token, `200` with bearer token.
  - `POST /search` → `200 OK` with ranked hits & provenance.
  - `GET /projections/{name}` → `current_mission` (`217` citations), `time_digest` 30d (`194` citations), `open_decisions` (`0` citations), `book_lenses` (`6` citations).
- Live `🔒` lock/unlock acceptance (on `#my-timeline` message `1575286288737636524` after `discord-hub` fix):
  - With `🔒` added: `stored_records=1075`, `present=False`, `in_records=False`, `in_digest=False`.
  - With `🔒` removed: `stored_records=1076`, `present=True`, `in_records=True`, `in_digest=True`.
