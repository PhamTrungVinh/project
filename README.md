# Customer support multi-agent application

Five containers run the current application:

- **Frontend**: React and Nginx, serving the UI and `/api` on port 5173.
- **Multi-agent service** (`chat-orchestrator`): LangGraph router/supervisor,
  FAQ/RAG, ticket, booking, and IT-support agents, approvals, memory, checkpoints.
- **Business backend**: authentication, profiles, ticket/booking APIs, audit
  records, and durable event delivery.
- **PostgreSQL**: six service-owned databases and the LangGraph checkpoint store.
- **Redis**: an optional application cache service, available to the
  multi-agent service through `REDIS_URL`. Application caching is not wired yet.

See [the architecture](docs/current_workflow.mmd) and
[consolidation validation and rollback](docs/CONSOLIDATION_PHASE_5.md).

## Run with Docker

Copy `.env.example` to `.env`, set `GROQ_API`, a strong `JWT_SECRET_KEY`, and a
strong URL-safe `POSTGRES_PASSWORD` (letters/numbers), and
provide the HR PDF at `FSoft_HR.pdf`. Existing deployments retain their approved
FAISS index in the `faiss_data` volume. A fresh install needs an approved RAG
artifact/index; without it the FAQ capability reports unavailable while the
other APIs remain usable. Optional search uses `TAVILY_API_KEY`.

```bash
docker compose up --build -d
docker compose ps
```

Open **http://localhost:5173**. The browser API base is `/api`; backend ports are
internal. For an upgrade from the split layout, follow the backup/cutover guide
before using `--remove-orphans`. Never delete data volumes during an upgrade.

Compose applies each owned database's migrations before starting its process.
PostgreSQL persists identity, ticket, booking, event, chat, checkpoints, and
memory in the `postgres17_data` volume. Existing SQLite files under `local_data/`
are no longer mounted by the default deployment; their data is not imported.
RAG/models use the existing named volumes. See [PostgreSQL setup](docs/POSTGRES_SETUP.md).

## Redis

Redis starts with the default Compose stack, or independently with:

```bash
docker compose up -d redis
docker compose exec -T redis redis-cli ping
```

The ping should return `PONG`. Containers connect using `redis://redis:6379/0`;
host processes use `redis://127.0.0.1:6379/0`. Change `REDIS_PORT` in `.env` to
publish a different host port and adjust the host URL accordingly. The published
port binds only to localhost; Redis has no authentication in this development
setup. Use an authenticated Redis URL for a remotely hosted instance.

Redis has a 256 MB memory limit and evicts least recently used keys when full.
Persistence is disabled because this service is intended for disposable caches;
restarts clear cached entries. PostgreSQL remains the durable data store. No
Python Redis client or application cache behavior is introduced by this setup.

## Chat event streaming

The sidebar lists saved conversations using their first-message titles. Selecting
a chat loads its user messages and final assistant replies from its checkpoint,
and subsequent messages continue the same thread. The list refreshes after each
turn, supports loading older chats, and includes a New action. History is served
by `GET /v1/chat/conversations/{thread_id}/messages`, with ownership checked before
reading checkpoints. Chats with missing checkpoints retain their titles and show
a message that their saved transcript is unavailable.

Each sidebar chat has a delete button with confirmation. Deleting the open chat
returns the view to a fresh chat. `DELETE /v1/chat/conversations/{thread_id}`
checks ownership, serializes against active turns and approvals, and removes
the conversation metadata, its checkpoints/writes, and its approval records.
Tickets, bookings, and account memory are independent of chat deletion. If
checkpoint cleanup fails, the chat remains listed so deletion can be retried.

The frontend uses `POST /v1/chat/messages/stream` with the same JSON request and
bearer token as `/v1/chat/messages`. It reads server-sent events through `fetch`
so the token stays in the Authorization header. The existing JSON endpoint
remains available.

The stream sends `start` (thread ID and correlation ID), `delta` (incremental
answer text), and a terminal `result` containing the full `ChatMessageResponse`,
including pending approvals. Failures after headers have been sent produce a
terminal `error` event with a safe message and status; authentication,
validation, and known conversation ownership failures use ordinary HTTP errors.
Keep-alive comments are sent every 10 seconds. Nginx buffering is disabled.
Events follow the [SSE format](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events).

The frontend appends answer chunks to one assistant message as the model generates
them. Routing decisions, tool arguments, and reasoning are excluded. FAQ answers
use the raw provider's streaming API. Static replies, such as approval questions
or fallbacks, are emitted as word chunks. The terminal result reconciles the
message with the final formatted answer and combined results of multi-agent turns.
There are no processing or agent-selection status messages.
Assistant messages render Markdown, including tables and line breaks, throughout
streaming. The final stream result preserves Markdown; the legacy JSON endpoint
continues returning its existing plain-text format.
Disconnecting stops event delivery while an already-running turn finishes and
saves its checkpoints. There is no automatic replay or retry of a chat request.
After code changes, rebuild the chat-orchestrator and frontend containers to
activate the API and UI updates.

## Development and tests

Use Python 3.13 from `.venv`. Local process configuration is documented in
[phase 4](docs/CONSOLIDATION_PHASE_4.md); Vite proxies `/api` to local ports 8000
and 8005. The former gateway and standalone services are compatibility entry
points, not part of the default deployment.

```bash
APP_ENV=test CHECKPOINT_SQLITE_PATH=/tmp/support-test-checkpoints.db ./.venv/bin/python -m pytest -q
npm --prefix frontend run build
node --test frontend/src/sse.test.js frontend/src/components/AssistantMessage.test.js
docker compose config --quiet
```

Tests require the usual provider/JWT environment to import configuration. Most
API tests stub external calls; deployed RAG/provider behavior is validated
separately. The Docker build currently installs from the frozen `uv.lock`.
There is no `requirements.txt` in this checkout; older repository instructions
describing that file and the Streamlit launcher are historical.

## Compatibility

The recorded ten-service configuration is `docker-compose.split-baseline.yml`.
Its matching old source/images are required for a full rollback. Old migration
histories and standalone entry points are retained to preserve that option.
The `docs/PHASE_*` files describe the earlier microservice extraction; the
`docs/CONSOLIDATION_PHASE_*` files describe this consolidation.
