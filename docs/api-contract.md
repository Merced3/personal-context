# Personal Context — v1 API Contract (Draft)

Local/Tailscale HTTP API (JSON). All endpoints except `GET /health` require a per-consumer bearer token.

Timestamps are always ISO-8601 UTC (`Z`). Consumers own timezone conversion (e.g., `America/Chicago` for `socratic-partner`’s Sunday 12:00 PM weekly review).

---

## `GET /health`

Liveness + sync status for `automation-harness` and ops health checks.

```json
{
  "status": "ok",
  "last_sync_at": "2026-11-20T18:00:00Z",
  "record_count": 1042
}
```

---

## `GET /records`

Query synced source records with provenance.

**Query params:**
- `source` (optional, repeatable) — source key or channel ID (e.g. `my-timeline`, `mission`, `decisions`, `books`)
- `since` (optional) — ISO-8601 UTC lower bound
- `until` (optional) — ISO-8601 UTC upper bound
- `thread_id` (optional) — filter to a specific thread / forum post
- `limit` (optional, default 50, max 200)
- `cursor` (optional) — opaque pagination cursor

**Response:**
```json
{
  "items": [
    {
      "id": "discord:1411955142529384530:1234567890",
      "source_system": "discord-hub",
      "source_channel_id": "1411955142529384530",
      "source_name": "my-timeline",
      "thread_id": null,
      "thread_title": null,
      "author_id": "111111",
      "content": "...",
      "created_at": "2026-11-19T04:12:00Z",
      "edited_at": null,
      "deleted": false,
      "tags": [],
      "attachments": []
    }
  ],
  "next_cursor": null
}
```

---

## `POST /search`

Hybrid semantic + keyword retrieval across synced records, returning ranked hits with exact provenance.

**Request:**
```json
{
  "query": "decisions about job search or career direction",
  "sources": ["my-timeline", "mission", "decisions"],
  "since": "2026-09-01T00:00:00Z",
  "limit": 15
}
```

**Response:**
```json
{
  "hits": [
    {
      "score": 0.87,
      "record": { "...same shape as GET /records item..." }
    }
  ]
}
```

---

## `GET /projections/{name}`

Returns a **rerunnable, evidence-backed distillation** built over raw records. Every claim or item includes `source_record_ids` so consumers (and the user) can verify where it came from.

Initial planned projections (consumer-agnostic):
- `current_mission` — distilled active goals/direction from `#mission`, cross-checked against recent `#my-timeline` / `📁reviews` for current momentum or drift. (Older timeline entries back to day 1 remain fully accessible via `/records` and `/search`; this projection just focuses on *current* direction.)
- `time_digest` — rolling summary of lived activity over a caller-specified window (`?days=7` or `?since=...&until=...`), so any consumer can request the timeframe it cares about (7 days for a weekly review, 30 days for opportunity evaluation, etc.) without overfitting to one cadence.
- `open_decisions` — currently `pending` posts from `📁decisions` with their stated predictions and check-back dates.
- `book_lenses` — distilled mental models from `📁books` and `#quotes-i-like`.

**Response:**
```json
{
  "name": "recent_digest",
  "version": "1",
  "generated_at": "2026-11-20T18:00:00Z",
  "model": "...",
  "data": {},
  "source_record_ids": ["discord:..."]
}
```

---

## `POST /sync`

Operator/internal trigger to run an immediate incremental sync from `discord-hub`’s Archive API (in addition to background scheduled syncing). Returns `{ "synced_messages": 12, "synced_events": 19 }`.
