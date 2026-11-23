# Roadmap — Personal Context

Tracks what is shipped, what is planned, and future capability ideas
(with the *why* behind each). When an item is implemented and verified, check
it off and link to the session prompt(s) in `docs/session-prompts/` that built
it.

---

## Shipped & Verified

- [x] Initial architecture, ownership boundaries, and v1 API contract (`README.md`, `docs/api-contract.md`, `AGENTS.md`).

---

## Planned — v0.1 Vertical Slice

- [ ] **Scaffold & `discord-hub` archive sync** — Package skeleton, config from `.env`, database schema, resumable incremental sync from `discord-hub` (`GET /archive/messages`, `GET /archive/events`), and `🔒` lock removal.
  - *Why:* Establishes the derived local store without touching Discord directly or coupling to `discord-hub`’s database.
- [ ] **Read & Search HTTP API** — FastAPI service (`GET /health`, `GET /records`, `POST /search`, `POST /sync`) with per-consumer bearer auth and `automation-harness` lifecycle.
  - *Why:* Gives any consumer (`socratic-partner`, `opportunity-runner`, etc.) a clean, source-cited retrieval boundary.
- [ ] **Rerunnable Projections** — `GET /projections/{name}` (`current_mission`, `time_digest`, `open_decisions`, `book_lenses`) with source record citations and full rebuildability.
  - *Why:* Lets consumers pull structured, up-to-date distillations without every consumer re-implementing summarization over raw logs.
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
