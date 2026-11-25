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

---

## Planned — v0.1 Vertical Slice

- [ ] **Live Acceptance & Deployment** — Verify real sync + `🔒` exclusion against `discord-hub` (using `Automations/ops/LAB.md`), deploy alongside the other services, and register in `ops/PROJECTS.md`.
  - *Why:* Proves the substrate works end-to-end on real data before wiring Consumer #1 (`socratic-partner`).

---

## Ideas / Future Capabilities (not yet scheduled)

Add ideas here *with the why* whenever they come up. Nothing here is a
commitment until promoted to Planned.

- [ ] **Additional capture sources beyond Discord** (e.g., `teaching-agent` knowledge evidence, voice transcripts, external notes).
  - *Why:* Keeps the substrate truly tool-agnostic if capture expands beyond Discord.
- [ ] **Consumer #2 (`opportunity-runner`) integration**
  - *Why:* Second real consumer to pressure-test the API contract and confirm zero overfitting to `socratic-partner`.
