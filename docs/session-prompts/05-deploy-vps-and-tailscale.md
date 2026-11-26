# Session: Deploy VPS & Tailscale (`automations-personal-context`)

**Date:** 2026-11-25  
**Status:** `completed`

## Original Prompt (DO NOT EDIT — preserved for auditability)

> Deploy `personal-context` to production on its own `$6` DigitalOcean droplet (`automations-personal-context`) and expose it over Tailscale (`:8010`) so Consumer #1 (`socratic-partner`) can query it 24/7:
> 1. **Managed PostgreSQL:** Provision/seed `personal_context` and `harness_personal_context` databases & roles via `Automations/ops/data-platform/data_platform.py`.
> 2. **Provision & bootstrap droplet:** Provision the `$6` (`s-1vcpu-1gb`) droplet using `Automations/ops/infra/provision.sh personal-context` (preserving existing Managed Postgres trusted sources), bootstrap with `ops/bootstrap.sh --role personal-context`, and configure Docker Compose using `Automations/ops/hosts/personal-context/compose.yml`.
> 3. **Tailscale setup & grants:** Join the droplet to Tailscale as `automations-personal-context` with `tag:personal-context`, update Tailscale grants (`tag:personal-context` → `tag:discord-hub:8100`, `tag:socratic-partner` → `tag:personal-context:8010`, `tag:lab` → `tag:personal-context:22,8010`, `tag:ci` → `tag:personal-context:22`), expose `personal-context` on its Tailscale IP (`:8010`), and close public SSH once Tailscale SSH is verified.
> 4. **Secrets & consumer tokens:** Generate `CONSUMER_TOKENS` (including `socratic-partner` and `operator`), populate `/opt/automations/env/personal-context.env` from `Automations/ops/env/personal-context.env.example`, and complete `ops/setup-server.sh --role personal-context`.
> 5. **Deploy & verify:** Build/deploy the container image, verify `GET http://automations-personal-context:8010/health` over Tailscale, verify initial full sync from `discord-hub` (`GET /records`, `POST /search`, `GET /projections/{name}` with `socratic-partner`'s bearer token, and `401` without auth), and verify reachability from `socratic-partner`.
> 6. Update this session log and `docs/roadmap.md` when complete.

---

## Session Log (Agent-Maintained)

### Status & What Changed
- **Completed.** Provisioned Managed PostgreSQL databases/pools, provisioned and bootstrapped the `$6` (`s-1vcpu-1gb`, `nyc3`) `automations-personal-context` droplet, joined Tailscale with `tag:personal-context` and least-privilege grants, deployed the container over Docker Compose (`:8010`), and verified end-to-end sync + authenticated API + cross-host reachability from `socratic-partner`.
- **Managed PostgreSQL (`automations-data`, `nyc3`):**
  - Created databases, roles, and PgBouncer pools (`transaction` mode, size `1`) for `personal_context` and `harness_personal_context`.
  - Granted database and `public` schema ownership to each role and revoked `CONNECT` from `PUBLIC`.
- **Droplet & Tailscale:**
  - Provisioned `automations-personal-context` (`s-1vcpu-1gb`, `nyc3`, ID `623541631`) via `Automations/ops/infra/provision.sh personal-context` (appended as Managed Postgres trusted source without disturbing existing droplets).
  - Added `personal-context` to the role allowlist in `Automations/ops/bootstrap.sh` and ran `bootstrap.sh --role personal-context` + `setup-server.sh --role personal-context` (closed public SSH after verifying Tailscale).
  - Joined Tailscale as `automations-personal-context` (`100.72.222.48`) with `tag:personal-context` and updated Tailscale grants (`personal-context` → `discord-hub:8100`, `socratic-partner` → `personal-context:8010`, `lab` → `personal-context:22,8010`, `ci` → `personal-context:22`).
- **Secrets & tokens:**
  - Generated `CONSUMER_TOKENS` for `socratic-partner` and `operator` in ignored `Automations/ops/env/personal-context.production.env` and seeded `/opt/automations/env/personal-context.env` + `/opt/automations/env/server.env` (`HEALTHCHECK_ENABLED=1`).
- **Bug fix discovered during deploy:**
  - Fixed `src/context_substrate/migrations/env.py` so `alembic upgrade head` prefers `os.environ["DATABASE_URL"]` over `alembic.ini`'s SQLite fallback URL.

### Decisions & Why
- **Direct container build (`automations-personal-context:local`) for initial bring-up:** `personal-context` is not yet wired into `Automations/.github/workflows/build-images.yml`. Building the image directly from `automation-harness` + `personal-context` unblocked immediate production verification; wiring `build-images.yml` + GHCR + `ACTIVE_HOST_ROLES` is a clean follow-up.
- **Explicit Tailscale IP for `HUB_INTERNAL_URL`:** Inside Docker's bridge network, Tailscale MagicDNS hostnames aren't resolved by default, so `/opt/automations/env/server.env` sets `HUB_INTERNAL_URL=http://100.81.116.58:8100` (`automations-discord-hub`'s Tailscale IP).

### Intentional Weirdness
- `personal-context` currently runs `SERVICE_IMAGE=automations-personal-context:local` until `build-images.yml` is updated to publish GHCR digests for the `personal-context` role.

### Discoveries / Open Questions
- **`alembic.ini` SQLite fallback masked `DATABASE_URL`:** `env.py` checked `config.get_main_option("sqlalchemy.url")` before `Settings().database_url`, causing `alembic upgrade head` to create a local SQLite file inside the container instead of migrating Postgres. Fixed in `src/context_substrate/migrations/env.py` (no existing Postgres databases were affected).
- **`doctl` redacts DB passwords by default:** `doctl databases user get` and `doctl databases connection` require `--show` to retrieve real passwords.
- **Follow-up:** Wire `personal-context` into `Automations/.github/workflows/build-images.yml` for automated GHCR deploys, and wire Consumer #1 (`socratic-partner`) to `http://automations-personal-context:8010` using its provisioned bearer token.

### Verification
- `pytest -q tests/test_migrations.py` → `1 passed` after `env.py` fix.
- Tailscale SSH (`ssh ops@automations-personal-context`) → `ok`; public SSH closed via UFW.
- `GET http://automations-personal-context:8010/health` (from laptop over Tailscale) → `200 OK` (`status: ok`, `record_count: 1076`, `last_sync_at: 2026-11-26T06:04:35.998462Z`).
- `GET http://automations-personal-context:8010/records` without auth → `401`.
- `GET /records?limit=3`, `POST /search`, `GET /projections/current_mission` with `socratic-partner` bearer token → all `200 OK` (`search` returned 3 hits).
- Cross-host check from `automations-socratic-partner`: `curl -fsS http://automations-personal-context:8010/health` → `200 OK` (`record_count: 1076`).
