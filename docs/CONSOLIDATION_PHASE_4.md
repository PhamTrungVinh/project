# Phase 4: three-container deployment

The default Compose configuration now contains:

| Component | Responsibilities | Ports |
| --- | --- | --- |
| `frontend` | SPA and Nginx API routing | Host 5173 to container 80 |
| `chat-orchestrator` | Multi-agent chat, approvals, memory, local RAG | Internal 8005 |
| `business-backend` | Identity, tickets, bookings, durable event inbox and outbox delivery | Internal 8000 |

There is no separate gateway, event receiver, or event worker in this layout.
All seven existing SQLite databases remain separate and at their existing host
paths. Phase 4 consolidates processes, not databases.

## Browser and API routing

The frontend uses relative `/api` URLs on its own origin. Nginx strips `/api`
and sends `/v1/chat`, `/v1/pending-actions`, and `/v1/memory` to chat; business
routes go to the business backend. Backend route paths and response fields
remain unchanged. The public API is now `http://localhost:5173/api`; port 8080
is no longer published.

On a same-origin build, saved local API bases at localhost/127.0.0.1 ports 8000,
8005, and 8080 are removed so old browser settings cannot bypass the new proxy.
Custom remote bases are retained. Vite development uses equivalent proxies to
local backend ports 8000 and 8005. Memory follows the same `/api` base.

Both APIs validate bearer JWTs and positive subjects before protected routes.
Domain ownership checks remain in the existing routes/services. Shared API
middleware enforces body sizes (including requests without Content-Length),
rate limits, CORS, request IDs, and structured HTTP/validation/domain errors.
Nginx forwards Authorization and Idempotency-Key, replaces X-Forwarded-For with
the actual client address, validates request IDs, limits body size, and returns
JSON 503 responses for connection/timeout failures. Backend ports are not
published; Compose trusts forwarded addresses from the internal proxy network.

Configuration defaults:

- `API_MAX_BODY_BYTES`: 1048576; Nginx also enforces 1 MiB. Adjust both together.
- `API_RATE_LIMIT_PER_MINUTE`: 120 per subject (or IP for public login/register),
  **per backend process**. This differs from the previous shared gateway quota.
  The two processes can each accept 120 requests; limits reset on restart.
- `API_CORS_ORIGINS`: localhost and 127.0.0.1 on port 5173.
- Nginx upstream read timeout: 30 seconds; connection timeout: 5 seconds.

## Event delivery

The business backend runs the event migration before startup and mounts
`local_data/event` at `/event-data`. A lifespan task dispatches ticket and
booking outboxes through the shared inbox function every five seconds.

The inbox commits first; the originating outbox is marked published afterward.
A crash between those commits replays the same event ID, which is deduplicated.
Conflicting content for an existing ID still fails. Failed deliveries retain
their error/attempt metadata and remain pending for the next batch. Shutdown
signals the loop and waits for the active batch to finish. Delivery results
and failures are logged.

Use `OUTBOX_WORKER_ENABLED=true` and `OUTBOX_POLL_SECONDS=5` (positive).
The initial deployment runs one Uvicorn process per service; multiple worker
processes need separate concurrency validation. The standalone HTTP event API
and worker are retained for rollback, but the current backend delivers events
in process and does not expose an event-ingestion endpoint to browsers.
`/ready` checks identity, ticket, booking, and event database connectivity.

## Running and rollback

Back up data and images using the phase 1 procedure before switching a running
deployment. Then stop the previous Compose layout and start the new one with
the same project name and volumes:

```bash
docker compose stop
docker compose up --build -d --remove-orphans
```

For local processes, follow phase 3 and additionally configure
`EVENT_DATABASE_URL=sqlite:///./events.db`, run
`./.venv/bin/python -m scripts.migrate_service event`, and start the business
backend. Stop the standalone event worker. Run chat as in phases 2/3 and
`npm run dev` inside `frontend`; the Vite proxy replaces the gateway locally.

The original split Compose snapshot remains available. A full rollback also
requires the recorded source/images and consistent data, as described in
phase 1; the snapshot alone does not restore earlier code.

## Validation boundary

Tests exercise inbox retry/deduplication after replay, both domain outboxes,
background-worker shutdown, JWTs, request size/rate limits, CORS, request IDs,
combined business APIs, and chat/memory composition. Frontend build, Compose
validation, and Nginx syntax validation are separate checks. These do not claim
that live data has been migrated or that the running deployment has switched.
