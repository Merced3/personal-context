# Session: Deploy VPS & Tailscale (`automations-personal-context`)

**Date:** 2026-11-25  
**Status:** `in-progress`

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
- (pending)

### Decisions & Why
- (pending)

### Intentional Weirdness
- (pending)

### Discoveries / Open Questions
- (pending)

### Verification
- (pending)
