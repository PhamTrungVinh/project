# Phase 3: one business backend

This records phase 3. [Phase 4](CONSOLIDATION_PHASE_4.md) supersedes its gateway
and standalone event-process instructions in the current deployment.

The default Compose stack now has six services: `business-backend`,
`chat-orchestrator`, `event-service`, `event-worker`, `gateway`, and `frontend`.
The business API runs at `business_backend.app:app` on internal port 8000.
It combines authentication, user profiles, tickets, and bookings. Event
processing and gateway replacement remain for phase 4.

## API and persistence

All existing `/auth`, `/users`, `/tickets`, and `/bookings` contracts are reused.
The gateway sends these routes to `http://business-backend:8000`; the chat
service sends ticket and booking HTTP tool requests there too. Public gateway
and frontend ports remain 8080 and 5173.

The backend retains three separate stores and migration histories:

| Environment variable | Container path | Existing host directory |
| --- | --- | --- |
| `IDENTITY_DATABASE_URL` | `/identity-data/identity_service.db` | `local_data/identity` |
| `TICKET_DATABASE_URL` | `/ticket-data/ticket_service.db` | `local_data/ticket` |
| `BOOKING_DATABASE_URL` | `/booking-data/booking_service.db` | `local_data/booking` |

Ticket and booking routes have explicit domain session dependencies. The
combined app overrides the legacy `get_db` dependency only for identity routes,
including the nested authentication dependency used by `/users/me`. No chat
or memory routes are included in this app.

The three existing migrations run before Uvicorn starts. No tables, IDs, or
data are moved. The event worker continues reading the same ticket and booking
outboxes and now waits for the business backend health check. JWT authorization,
ownership checks, idempotency, audit/outbox transactions, and request IDs remain
in their existing implementations.

`/health` checks process liveness. `/ready` checks connectivity to all three
stores and returns 503 with the failing domain when a store is unavailable.
As before, connectivity alone does not establish schema completeness.

## Local process setup

Use the existing provider/JWT environment. Configure the business backend:

```bash
export IDENTITY_DATABASE_URL=sqlite:///./identity_service.db
export TICKET_DATABASE_URL=sqlite:///./ticket_service.db
export BOOKING_DATABASE_URL=sqlite:///./booking_service.db
./.venv/bin/python -m scripts.migrate_service identity
./.venv/bin/python -m scripts.migrate_service ticket
./.venv/bin/python -m scripts.migrate_service booking
./.venv/bin/uvicorn business_backend.app:app --port 8000
```

For chat, follow phase 2 but set both `TICKET_SERVICE_URL` and
`BOOKING_SERVICE_URL` to `http://127.0.0.1:8000`.

For the gateway, set `GATEWAY_BACKEND_URL`, `GATEWAY_IDENTITY_URL`,
`GATEWAY_TICKET_URL`, and `GATEWAY_BOOKING_URL` to `http://127.0.0.1:8000`.
Keep `GATEWAY_CHAT_URL` and `GATEWAY_MEMORY_URL` at `http://127.0.0.1:8005`.
Event receiver/worker configuration remains unchanged.

## Cutover and rollback

Use the phase 1 backup and rollback procedure before a runtime cutover. Stop
the previous layout before `docker compose up --build -d --remove-orphans`,
retaining the Compose project name, bind-mounted databases, and named volumes.
Implementation does not restart services or migrate live data automatically.

Standalone identity/ticket/booking entry points remain available for the
original split baseline. They reuse the same domain logic and database files;
do not run both layouts against those files concurrently.

## Validation

`tests/test_business_backend.py` exercises registration, login, profile access,
ticket/booking creation, JWT contact fields, two-user isolation, idempotent
replay/conflict, status changes, cancellation, UTC timestamps, audit/outbox
counts, correlation IDs, and readiness failure through the combined app.
Each domain uses a physically separate temporary SQLite file containing only
its owned tables. Existing API, split-store, migration, and gateway tests
provide regression coverage. A deployed Docker smoke test remains separate.
