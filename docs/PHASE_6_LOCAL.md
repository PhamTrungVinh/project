# Phase 6 local gateway

For the fully separated local setup with identity, chat, ticket, booking, and
memory databases, follow [Run the split services locally](LOCAL_SERVICE_SPLIT.md).
The commands below describe the earlier compatibility setup with the backend.

The gateway is the frontend's public entry point. It validates the login JWT,
limits request size and local request rate, and forwards a correlation ID. The
backend and orchestrator still validate the bearer token and authorize their own
resources. Ticket and booking changes create outbox rows in their business
transactions. A worker sends versioned events to a durable inbox.

Apply the latest app database migration before starting the services:

```bash
./.venv/bin/alembic upgrade head
```

Start the backend and orchestrator as described in [Phase 5 local setup](PHASE_5_LOCAL.md).
Then run the gateway from the repository root:

```bash
./.venv/bin/uvicorn gateway.app:app --port 8080
```

Start the frontend with both API bases set to the gateway:

```bash
cd frontend
VITE_API_BASE=http://localhost:8080 VITE_CHAT_API_BASE=http://localhost:8080 npm run dev
```

The gateway sends `/auth`, `/users`, `/tickets`, `/bookings`, and compatibility
`/chat` requests to the backend on port 8000. Set `GATEWAY_TICKET_URL` and
`GATEWAY_BOOKING_URL` to ports 8002 and 8003 if running the extracted domain
services. It sends `/v1/chat/messages` and
`/v1/pending-actions/{id}/decision` to the orchestrator on port 8005. `/health`
checks the gateway process. Set `GATEWAY_BACKEND_URL`, `GATEWAY_CHAT_URL`,
`GATEWAY_CORS_ORIGINS`, `GATEWAY_MAX_BODY_BYTES`,
`GATEWAY_RATE_LIMIT_PER_MINUTE`, or `GATEWAY_UPSTREAM_TIMEOUT_SECONDS` to change
the local defaults.

Existing standalone ticket and booking SQLite databases receive the new outbox
correlation columns when those services start. The `alembic upgrade head`
command above upgrades the shared local `app.db`.

If the frontend previously stored API bases in browser local storage, clear
`fpt_api_base` and `fpt_chat_api_base` so the Vite settings take effect.

Start the local event receiver and outbox worker in separate terminals with
the same service token. The receiver stores received event IDs in `events.db`.

```bash
./.venv/bin/python -m scripts.migrate_service event
EVENT_SERVICE_TOKEN=local-event-token ./.venv/bin/uvicorn event_service.app:app --port 8006
```

```bash
EVENT_SERVICE_TOKEN=local-event-token ./.venv/bin/python -m scripts.run_outbox_worker
```

Use `--once` for one batch. The worker prints published, failed, pending, and
oldest-pending counts for ticket and booking events. It retries failed rows on
the next poll, and the receiver returns `duplicate` for an event already stored.
For separately stored ticket and booking outboxes, set
`OUTBOX_TICKET_DATABASE_URL` and `OUTBOX_BOOKING_DATABASE_URL`.

The receiver's `/metrics` endpoint reports the number of distinct events.
The `X-Internal-Service-Token` header is required to post or inspect events.
