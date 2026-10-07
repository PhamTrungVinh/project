# Run the split services locally

For the planned consolidation into two backend processes, see the
[phase 1 compatibility baseline](CONSOLIDATION_PHASE_1.md). The original
deployment configuration is preserved in
[`docker-compose.split-baseline.yml`](../docker-compose.split-baseline.yml).

Each API runs in its own process with a separate SQLite file. Use the same
`JWT_SECRET_KEY` in all processes. The gateway is the only frontend API base.
Keep `.env` available for the existing AI provider keys.

## Docker Compose

Run from the repository root:

```bash
docker compose up --build
```

Compose now starts the multi-agent chat service, business backend, and frontend.
See [phase 4](CONSOLIDATION_PHASE_4.md) for the current deployment and API routing.
The frontend is at `http://localhost:5173`; the API is at
`http://localhost:5173/api`. Only port 5173 is published.
`GROQ_API` and `JWT_SECRET_KEY` must be set in `.env`
or the shell. It runs each owned database's migration before its service
starts. Service data lives under `local_data/<service>/`, which is ignored by
Git. The business backend delivers ticket and booking outboxes to the event
inbox in process.

Compose starts with empty service databases. If you already have split local
databases in the repository root, stop Compose before copying them into their
matching directories:

```bash
mkdir -p local_data/{identity,chat,ticket,booking,memory,event}
cp identity_service.db local_data/identity/
cp chat_service.db local_data/chat/
cp chat_checkpoints.db local_data/chat/
cp ticket_service.db local_data/ticket/
cp booking_service.db local_data/booking/
cp memory_service.db local_data/memory/
cp events.db local_data/event/
```

Copy only files you have, and only into an empty destination. SQLite WAL files
must be checkpointed by stopping their writers before copying. The first
Compose start validates the existing table shape and records the first service
migration without changing data. An incomplete or mixed-service database is
rejected with an error instead of being stamped.

## Separate local processes

The commands below describe the original split layout retained for rollback.
For the consolidated chat process, use the phase 2 guide above.

Run commands from the repository root in separate terminals. Apply migrations
first; standalone APIs no longer create tables on startup:

```bash
for service in identity chat ticket booking memory event; do
  ./.venv/bin/python -m scripts.migrate_service "$service"
done
```

If you have data in `app.db`, stop the old backend and copy it once before
starting these services:

```bash
./.venv/bin/python -m scripts.split_local_databases --source app.db --destination . --checkpoints checkpoints.db
```

The command leaves `app.db` and `checkpoints.db` untouched. It refuses to copy
into any nonempty destination table or existing `chat_checkpoints.db`; it can
also take another destination directory for a dry run. If you have no old
data, skip it and the migrations will create empty owned databases.

```bash
./.venv/bin/uvicorn identity_service.app:app --port 8007
```

```bash
TICKET_DATABASE_URL=sqlite:///./ticket_service.db ./.venv/bin/uvicorn ticket_service.app:app --port 8002
```

```bash
BOOKING_DATABASE_URL=sqlite:///./booking_service.db ./.venv/bin/uvicorn booking_service.app:app --port 8003
```

```bash
MEMORY_DATABASE_URL=sqlite:///./memory_service.db ./.venv/bin/uvicorn memory_service.app:app --port 8004
```

```bash
KNOWLEDGE_SERVICE_TOKEN=local-knowledge-token ./.venv/bin/uvicorn knowledge_api:app --port 8001
```

The knowledge service loads the local RAG index on startup. The first run may
download the reranker model.

```bash
DATABASE_URL=sqlite:///./chat_service.db CHECKPOINT_SQLITE_PATH=chat_checkpoints.db TICKET_ADAPTER=http BOOKING_ADAPTER=http MEMORY_ADAPTER=http KNOWLEDGE_ADAPTER=http TICKET_SERVICE_URL=http://127.0.0.1:8002 BOOKING_SERVICE_URL=http://127.0.0.1:8003 MEMORY_SERVICE_URL=http://127.0.0.1:8004 KNOWLEDGE_SERVICE_URL=http://127.0.0.1:8001 KNOWLEDGE_SERVICE_TOKEN=local-knowledge-token ./.venv/bin/uvicorn chat_orchestrator.app:app --port 8005
```

```bash
GATEWAY_IDENTITY_URL=http://127.0.0.1:8007 GATEWAY_CHAT_URL=http://127.0.0.1:8005 GATEWAY_TICKET_URL=http://127.0.0.1:8002 GATEWAY_BOOKING_URL=http://127.0.0.1:8003 GATEWAY_MEMORY_URL=http://127.0.0.1:8004 ./.venv/bin/uvicorn gateway.app:app --port 8080
```

Point the frontend to the gateway:

```bash
cd frontend
VITE_API_BASE=http://localhost:8080 VITE_CHAT_API_BASE=http://localhost:8080 npm run dev
```

The gateway routes login and user profile to identity, chat and decisions to
the orchestrator, tickets and bookings to their APIs, and memory to its API.
The old `main.py` backend is not needed in this mode. The orchestrator's
database contains conversations and pending actions; the checkpoint file is
separate. Ticket and booking databases contain only their own records and
outboxes. JWT claims carry account identity to the domain APIs.

For local event delivery, use the event receiver and worker in
[Phase 6 local setup](PHASE_6_LOCAL.md), and set
`OUTBOX_TICKET_DATABASE_URL=sqlite:///./ticket_service.db` and
`OUTBOX_BOOKING_DATABASE_URL=sqlite:///./booking_service.db` for the worker.

Each service has its own revision history under `service_migrations/<service>`.
After changing one service's models, generate a revision with
`./.venv/bin/python -m scripts.new_service_revision SERVICE "description"`,
review the generated operations, and run
`./.venv/bin/python -m scripts.migrate_service SERVICE`. The old `alembic/`
history remains for the monolith only.
