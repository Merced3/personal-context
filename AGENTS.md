# AGENTS.md — orientation for AI sessions

You are working on **personal-context** (working name — keep it easy to rename),
the Personal Context Substrate for the Automations ecosystem.

Read `README.md` first, then `docs/roadmap.md`, `docs/api-contract.md`, and any
active doc in `docs/session-prompts/` before making changes.

---

## Living documentation & session logs (always do this)

Documentation is built *as the project evolves*, not as an afterthought.

1. **Know your destination doc:** While working, if you know which Markdown file
   should record your work (e.g., an active file in `docs/session-prompts/`),
   keep it updated as you go.
2. **If you don't know where to log, ask:** If no destination MD file is clear,
   ask the user where to record updates. If the user says "none", skip logging.
3. **Never edit the original prompt:** In `docs/session-prompts/*.md`, the
   session title and prompt form the top half of the file and are preserved
   verbatim for auditability. Only write in the updates section below it.
   Use `docs/session-prompts/_template.md` when creating a new session prompt.
   When a dedicated session actually begins executing a prompt, that session is
   responsible for filling in the current date (`YYYY-MM-DD`) in `**Date:**`
   and updating `**Status:**`.
4. **Update `docs/roadmap.md` when capabilities ship:** When a planned item or
   idea is implemented and verified, check it off in `docs/roadmap.md` and link
   to the session prompt(s) that built it.
5. **Create ADRs only when warranted (`docs/decisions/`):** Don't create an ADR
   folder preemptively. If a durable architectural choice, fork in the road, or
   contract-level trade-off comes up that warrants a permanent record (an
   "ADR-level" decision), create `docs/decisions/` and record it as
   `0001-<slug>.md` (following `discord-hub`'s convention).
6. **Write the *why*, not just the *what*:** Assume the reader does not have
   this session's context. Record:
   - current status and what changed;
   - discoveries, forks in the road, and decisions made;
   - **intentional weirdness** — anything that looks unusual on purpose, and
     *why* it's that way, so future sessions or readers don't mistake it for a
     bug and "fix" it.

---

## Non-negotiable design boundaries

1. **Consumer-agnostic substrate:** This project ingests, indexes, searches,
   and distills personal evidence with provenance. It never owns consumer
   judgment or policy (no Socratic prompts, question queues, weekly review
   templates, opportunity scoring, or pedagogy).
2. **Not the raw source of truth:** `discord-hub` (and future capture layers)
   own the immutable raw archive. Everything here is derived and rebuildable.
3. **Discord-agnostic:** Never import `discord.py`, never hold a Discord token,
   and never query `discord-hub`'s Postgres directly. Consume `discord-hub`'s
   Archive API (ADR 0012) over HTTP.
4. **Respect privacy (`🔒` exclusion):** Locked items excluded by `discord-hub`
   must never remain in local indexes or projections.
5. **Easy to rename:** Keep the working name `personal-context` out of internal
   schemas and API contracts where practical so renaming stays cheap.

---

## Safety & repository boundaries

- Never read or print `.env`, and never commit secrets, tokens, or private
  runtime data.
- Only edit `personal-context` in this session. Treat sibling repos
  (`discord-hub`, `socratic-partner`, etc.) as read-only references.
- Keep default tests offline (mocked HTTP/archive responses) so tests never
  depend on live Discord or production data.
