# Roadmap — Personal Context

Tracks what is shipped, what is planned, and future capability ideas
(with the *why* behind each). When an item is implemented and verified, check
it off and link to the session prompt(s) in `docs/session-prompts/` that built
it.

---

## Shipped & Verified

- [x] Initial architecture, ownership boundaries, and v1 API contract (`README.md`, `docs/api-contract.md`, `AGENTS.md`).
- [x] **Scaffold & `discord-hub` archive sync** (`docs/session-prompts/01-scaffold-and-sync.md`) — Package skeleton, config from `.env`, database schema + Alembic migrations, resumable incremental sync from `discord-hub` (`GET /archive/messages`, `GET /archive/events`), and strict `🔒` lock removal.
- [x] **Read & Search HTTP API** (`docs/session-prompts/02-records-and-search-api.md`) — FastAPI service (`GET /health`, `GET /records`, `POST /search`, `POST /sync`) with per-consumer bearer auth, hybrid keyword + semantic retrieval, and `automation-harness` lifecycle.
- [x] **Rerunnable Projections** (`docs/session-prompts/03-projections.md`) — `GET /projections/{name}` (`current_mission`, `time_digest`, `open_decisions`, `book_lenses`) with source record citations, strict citation integrity, `🔒` lock invalidation/rebuild, and full rebuildability from synced records.
- [x] **Live Acceptance & Deployment** (`docs/session-prompts/04-live-sync-and-deploy.md`) — Provisioned `personal-context` archive reader token in `discord-hub`, verified live incremental sync + cursor resume + `🔒` lock/unlock exclusion + cited projections against real archive data, wired production deployment (`Dockerfile`, `ops/hosts/personal-context/compose.yml`, `ops/infra/inventory.sh`, `ops/server/healthcheck.sh`, `ops/data-platform/data_platform.py`), and registered in `ops/PROJECTS.md`.

---

## Planned — Production Rollout & Consumer #1

- [x] **Provision Postgres & Deploy Droplet** (`docs/session-prompts/05-deploy-vps-and-tailscale.md`) — Provisioned `personal_context` + `harness_personal_context` in Managed PostgreSQL (`automations-data`, `nyc3`), deployed the `$6` `automations-personal-context` droplet over Tailscale (`:8010`) with `tag:personal-context` grants and `socratic-partner` bearer token, synced `1,076` records from `discord-hub`, and verified cross-host reachability from `socratic-partner`.

---

## Ideas / Future Capabilities (not yet scheduled)

Add ideas here *with the why* whenever they come up. Nothing here is a
commitment until promoted to Planned.

- [ ] **Additional capture sources beyond Discord** (e.g., `teaching-agent` knowledge evidence, voice transcripts, external notes).
  - *Why:* Keeps the substrate truly tool-agnostic if capture expands beyond Discord.
- [ ] **Consumer #2 (`opportunity-runner`) integration**
  - *Why:* Second real consumer to pressure-test the API contract and confirm zero overfitting to `socratic-partner`.
