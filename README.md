# Personal Context

![Personal Context — raw inputs flowing through a shared context prism to downstream tools](assets/cover.jpeg)

**Status:** initial architecture & contract (v0.1 design). No deployment yet.

**Working name:** `personal-context`. Keep the display name out of internal identifiers, database schemas, and API contracts so it can be renamed freely later without breaking consumers.

Read with [`Automations/OVERVIEW.md`](../../OVERVIEW.md), [`Automations/PRINCIPLES.md`](../../PRINCIPLES.md), and [`documented-self-thesis.md`](../discord-hub/docs/self-documentation-thesis/documented-self-thesis.md).

---

## Purpose

`personal-context` is the **Personal Context Substrate** for the Automations ecosystem.

It reads raw personal source records through permissioned APIs (starting with `discord-hub`’s Documented Self Archive API, ADR 0012), maintains a searchable, provenance-preserving index in its own database, and exposes **rerunnable, evidence-backed projections** to downstream applications.

```text
discord-hub (Source Archive API, ADR 0012)
        |
        v
personal-context (this project)
  - incremental sync + local index
  - semantic/keyword retrieval with provenance
  - rerunnable, cited projections (rebuildable from raw records)
        |
        +---> socratic-partner (Judgment: 📁decisions, 📁reviews, #reflection)
        +---> opportunity-runner (future: opportunity evaluation)
        +---> teaching-agent (future: learning context)
        +---> personal-website / future tools
```

---

## Ownership boundaries

### Owns
- Incremental ingestion from permissioned source APIs (starting with `discord-hub` `GET /archive/messages` and `GET /archive/events`).
- Preserving full provenance on every record (`source_system`, `channel_id`, `thread_id`, `message_id`, `author`, `timestamp_utc`).
- Respecting upstream privacy boundaries (`🔒` lock exclusions from `discord-hub` are propagated on sync — locked items are removed/hidden from indexes and projections).
- Retrieval (time-range queries, source-filtered queries, keyword + semantic search) returning source-cited records.
- Rerunnable, versioned **projections** (distillations over raw records) where every claim links back to source record IDs and can be regenerated from scratch as models improve.

### Refuses to own
- **Raw source of truth:** `discord-hub` (and future capture layers) own the immutable raw archive. If `personal-context`’s database is wiped, it can be rebuilt from upstream archives.
- **Consumer judgment or policy:** No Socratic prompts, no question queues, no weekly review templates, no decision-detection rules, no opportunity scoring, no pedagogy. Keeping these out prevents any single consumer’s use case from tainting the substrate or skewing it toward one project over others. Each consuming project owns its own judgment and uses `personal-context` strictly for the underlying data and distillations it needs.
- **Persona / "AI clone" imitation (current boundary):** Today, this is an evidence-backed context substrate rather than a static personality profile. This is a working boundary, not a permanent rule—if future needs justify it, it can evolve.
- **Direct Discord access:** Never imports `discord.py`, never holds a Discord token, never queries `discord-hub`’s Postgres directly.

---

## Source provenance (no hardcoded hierarchy)

The owner uses a private Discord server as a structured digital journal—logging raw thoughts, goals, books, ideas, beliefs, and decisions across dedicated channels (`#...`) and forums (`📁...`). Rather than compressing all of that into a single static "avatar" profile (which risks overfitting to one use case and losing traceability), this project pulls and indexes the data on demand so downstream tools can query the exact evidence they need.

The philosophy underneath is simple: *to be interesting, you first have to be interested.* The owner documents a wide range of curiosities, experiments, and lived experiences *before* the outcomes are known, which is why the archive spans so many distinct channels and forums.

Different sources carry different kinds of signal (`#mission`, `#my-timeline`, `#quotes-i-like`, `📁books`, `📁ideas`, `📁beliefs`, `📁decisions`, `📁questions`, `📁reviews`).

`personal-context` preserves each record’s exact source identity and metadata rather than flattening everything into one undifferentiated blob or hardcoding a single importance ranking. <u>Each consuming application decides how to weight sources for its own purpose.</u>

---

## First vertical slice (v0.1)

1. Sync client for `discord-hub`’s authenticated Archive API (`GET /archive/messages`, `GET /archive/events`) with resumable cursor checkpoints.
2. Own Postgres storage (via `automation-harness` / Alembic) for synced records + search index.
3. Read-only HTTP API (`docs/api-contract.md`): `/health`, `/records`, `/search`, `/projections/{name}`.
4. Wire **Consumer #1 (`socratic-partner`)** to power:
   - `📁decisions`: detecting unspoken decisions in `#my-timeline` (proposing drafts for confirmation) and bumping `pending` decisions at check-back dates.
   - `📁reviews`: weekly review pre-draft on **Sundays at 12:00 PM `America/Chicago`**, pulling that week’s timeline, moved decisions, shifting beliefs, and open questions.
   - Grounded `#reflection` sessions that synthesize real history and offer concrete options, not just abstract questions.
