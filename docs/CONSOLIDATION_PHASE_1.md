# Consolidation phase 1: compatibility baseline

Recorded 2026-09-29 against commit `bfc9702fef3d41ffbd7295130c9fb0d8572c24eb`.
The working tree was clean before these documentation and snapshot additions.

This is a source-inspection baseline, not a report that the deployed stack or
tests passed. No application code, databases, migrations, or running services
were changed in this phase. Runtime acceptance remains a gate for later phases.

## Target and sequence

The target is three deployed components: frontend, multi-agent service, and
business backend. The multi-agent service owns graph execution, approvals,
conversations, checkpoints, memory, and RAG. The business backend owns identity,
tickets, bookings, audit, and event delivery. Agents call the business backend
over authenticated HTTP. Keep existing database files and migration histories
through consolidation; merging databases is a separate project.

1. Phase 1 (this document): record contracts, ownership, acceptance scenarios,
   and preserve the split deployment configuration.
2. Phase 2: incorporate memory and local RAG into the chat orchestrator.
3. Phase 3: combine identity, ticket, and booking APIs into the business backend.
4. Phase 4: incorporate events and replace gateway routing/protections.
5. Phase 5: validate the composed apps, switch the default deployment, and
   retire obsolete entry points after rollback has been demonstrated.

## Current deployment

Source: [Compose](../docker-compose.yml),
[local deployment guide](LOCAL_SERVICE_SPLIT.md).

| Compose service | Entry point | Container port | Target component |
| --- | --- | --- | --- |
| identity-service | `identity_service.app:app` | 8007 | Business backend |
| ticket-service | `ticket_service.app:app` | 8002 | Business backend |
| booking-service | `booking_service.app:app` | 8003 | Business backend |
| memory-service | `memory_service.app:app` | 8004 | Multi-agent service |
| knowledge-rag | `knowledge_api:app` | 8001 | Multi-agent service |
| chat-orchestrator | `chat_orchestrator.app:app` | 8005 | Multi-agent service |
| event-service | `event_service.app:app` | 8006 | Business backend |
| event-worker | `scripts.run_outbox_worker` | None | Business backend background lifecycle |
| gateway | `gateway.app:app` | 8080 | Nginx routing and backend middleware |
| frontend | Frontend image / Nginx | 80 | Frontend |

Only gateway 8080 and frontend 5173 (mapped to container 80) are published.
The frontend currently uses `http://localhost:8080` for both API bases.
Nginx currently only serves the SPA; it does not yet proxy API requests.

The graph has four specialist nodes: `rag_agent`, `ticket_agent`,
`booking_agent`, and `it_support_agent`, plus router/supervisor and tool and
confirmation nodes. Search/calculator code exists, but there is no separate
web agent node. Preserve actual graph behavior rather than adding a fifth
agent as part of deployment consolidation.

## Public API compatibility

Sources: [frontend client](../frontend/src/api.js),
[chat routes](../chat_orchestrator/routes.py), [schemas](../schemas/chat.py),
[ticket routes](../ticket_service/routes.py),
[booking routes](../booking_service/routes.py), and
[gateway route map](../gateway/app.py).

All routes below require a bearer token except register/login. Preserve paths,
methods, trailing-slash behavior, JSON field names, status codes, and error
`detail` values. Normal successes below default to HTTP 200 unless specified.
The decision endpoint is an API contract even when a client uses typed chat
confirmation instead of calling it directly.

| Method and path | Request | Success response | Current owner |
| --- | --- | --- | --- |
| POST `/auth/register` | JSON `email`, `password`, optional `full_name` | User | Identity |
| POST `/auth/login` | Form-encoded `username` (email), `password` | `access_token`, `token_type` | Identity |
| GET `/users/me` | None | User | Identity |
| GET `/tickets/` | `skip=0`, `limit=50` | List of Ticket | Ticket |
| POST `/tickets/` | TicketCreate | Ticket | Ticket |
| GET `/tickets/{ticket_code}` | None | Ticket | Ticket |
| PATCH `/tickets/{ticket_code}` | TicketUpdate | Ticket | Ticket |
| PATCH `/tickets/{ticket_code}/status` | `status` | Ticket | Ticket |
| GET `/bookings/` | `skip=0`, `limit=50` | List of Booking | Booking |
| POST `/bookings/` | BookingCreate | Booking | Booking |
| GET `/bookings/{booking_code}` | None | Booking | Booking |
| PATCH `/bookings/{booking_code}` | BookingUpdate | Booking | Booking |
| POST `/bookings/{booking_code}/cancel` | None | Booking | Booking |
| GET `/v1/chat/conversations` | `skip=0`, `limit=50` | List of Conversation | Chat |
| POST `/v1/chat/messages` | `message`, optional `thread_id` | ChatMessage | Chat |
| POST `/v1/pending-actions/{action_id}/decision` | `decision`: `approve` or `reject`; extra fields forbidden | Decision | Chat |
| POST `/v1/memory/facts` | `fact` | 201, `status: success` | Memory |
| DELETE `/v1/memory` | None | `facts_deleted`, `episodes_deleted` | Memory |
| POST `/v1/memory/episodes` | `thread_id`, `summary`, `outcome` | 201, `status: success` | Memory |
| GET `/v1/memory/context` | `query` | `context` | Memory |

List pagination requires `skip >= 0` and `1 <= limit <= 200`.
Ticket/booking mutations accept optional `Idempotency-Key` headers.

### Schema details

- User: `id`, `email`, nullable `full_name`.
- TicketCreate: required `content`, `description`; optional `customer_name`,
  `customer_phone`, `email`. TicketUpdate makes these fields optional.
- Ticket: `id`, `ticket_code`, the five content/contact fields, `status`,
  `created_at`, nullable `updated_at`. Status values: `Pending`, `Resolving`,
  `Canceled`, `Finished`.
- BookingCreate: required `reason`, `time`; optional `note`, `customer_name`,
  `customer_phone`, `email`. BookingUpdate makes these fields optional.
- Booking: `id`, `booking_code`, those six fields, `status`, `created_at`,
  nullable `updated_at`. `time` serializes as an explicit UTC ISO timestamp.
  Status values: `Scheduled`, `Canceled`, `Finished`.
- Conversation: `id`, `thread_id`, nullable `email`, nullable `title`,
  `created_at`, nullable `updated_at`.
- ChatMessage: `answer`, nullable `route`, `thread_id`, `pending_actions`,
  `correlation_id`. Message input must be nonempty; a supplied thread ID is
  1–255 characters. Omission creates a new `session-...` thread.
- Pending action summary: `id`, `agent`, `question`, `expires_at`.
- Decision: `id`, `status`, `thread_id`, nullable `result`, `answer`, `route`,
  `pending_actions`, `correlation_id`.

Contact information supplied by a client must not override the authenticated
ownership rules. Keep user IDs, ticket/booking codes, thread IDs, pending-action
IDs, and stable idempotency keys unchanged across the cutover.

### Client routing and edge behavior

`fpt_api_base` and `fpt_chat_api_base` localStorage values override build-time
`VITE_API_BASE` and `VITE_CHAT_API_BASE`. Chat send/list calls use the chat base;
memory calls currently use the general base. Migration must handle both stored
overrides and the new memory destination.

The gateway validates JWTs, rejects unsupported paths/methods, rate-limits by
subject or IP, enforces body size, forwards `Authorization`, `Idempotency-Key`
and `X-Request-ID`, and normalizes upstream errors. Defaults are 120 requests
per minute, 1 MiB request bodies, and 30-second upstream timeout. Preserve
equivalent protections before removing the gateway. Test 401, 404, 409, 413,
422, 429, and upstream-unavailable responses where applicable; do not assume
all backend and gateway error envelopes are identical.

## Internal contracts

- Knowledge: `POST /v1/query`, authenticated by `X-Internal-Service-Token`.
  Input has `query`, `requester`, `correlation_id`, optional
  `approved_index_version`. Output retains `status` (`ok`, `unavailable`,
  `degraded`), answer, passages, citations, retrieval/index versions and reason.
  Preserve this interface at the Python adapter boundary when HTTP is removed.
- Events: `POST /v1/events` accepts the validated `EventEnvelope`; GET
  `/v1/events/{event_id}` retrieves an envelope. Both require the internal token.
  Equal event ID/content replays return `duplicate`; conflicting content is 409.
- Worker: reads both domain outboxes and delivers to the event receiver. There
  is no separate worker database. Keep retries, delivery metadata, and durable
  inbox deduplication when moving delivery inside the backend.

## Data ownership

Sources: [migration registry](../service_migrations/common.py), domain models,
and Compose mounts. These are configured stores, not a live schema audit.

| Host path under `local_data/` | Owned application tables/state | Future owner |
| --- | --- | --- |
| `identity/identity_service.db` | `users` | Business backend |
| `ticket/ticket_service.db` | `tickets`, `ticket_audit`, `ticket_outbox`, idempotency records | Business backend |
| `booking/booking_service.db` | `bookings`, `booking_audit`, `booking_outbox`, idempotency records | Business backend |
| `event/events.db` | `event_inbox` | Business backend |
| `chat/chat_service.db` | `conversations`, `pending_actions` | Multi-agent service |
| `chat/chat_checkpoints.db` | LangGraph saver state | Multi-agent service |
| `memory/memory_service.db` | `semantic_memory`, `episodic_memory` | Multi-agent service |

Six application stores have independent `service_migrations/<domain>` histories.
Checkpoints use LangGraph's saver schema separately. The FAISS index lives in
the `faiss_data` named volume; `hf_cache` holds downloaded models. The HR PDF
is mounted read-only from the repository.

Root-level split databases belong to the alternative local-process layout;
`app.db` and `checkpoints.db` belong to the earlier combined layout. Do not
silently select them when deploying the consolidated services.

## Configuration to preserve or rewire

| Area | Baseline configuration |
| --- | --- |
| Shared | `APP_ENV=development`, required `GROQ_API` and `JWT_SECRET_KEY`; optional `OPENROUTER_API_KEY`, `TAVILY_API_KEY` |
| Chat persistence | Both `DATABASE_URL` and `CHAT_DATABASE_URL` point to the chat store; `CHECKPOINT_SQLITE_PATH` selects the saver file |
| Domain persistence | `IDENTITY_DATABASE_URL`, `TICKET_DATABASE_URL`, `BOOKING_DATABASE_URL`, `MEMORY_DATABASE_URL`, `EVENT_DATABASE_URL` |
| Chat adapters | `TICKET_ADAPTER`, `BOOKING_ADAPTER`, `MEMORY_ADAPTER`, `KNOWLEDGE_ADAPTER` are all `http` in Compose |
| Remote destinations | Matching `*_SERVICE_URL` values; knowledge/event internal tokens must match callers and receivers |
| Approvals | `HITL_ENABLED` defaults to true |
| RAG | `PDF_PATH`, `FAISS_INDEX_PATH`, optional `RAG_ARTIFACT_URI`, `RAG_ARTIFACT_VERSION`; retain index/cache mounts |
| Worker | `OUTBOX_TICKET_DATABASE_URL`, `OUTBOX_BOOKING_DATABASE_URL`, `EVENT_SERVICE_URL`, `EVENT_SERVICE_TOKEN` |
| Gateway/frontend | Gateway destination URLs and limits; both Vite API bases and saved browser overrides |

Outside local environments, startup validation requires PostgreSQL and remote
versioned RAG artifacts. This phase makes no production configuration changes.
Never store resolved environment values or secrets in the baseline artifact.

## Acceptance scenarios and existing coverage

These are required preservation criteria. Coverage listed below was inspected,
not executed in this phase; presence of a test is not proof of a passing stack.

| Scenario | Required result | Existing test files under `tests/` |
| --- | --- | --- |
| Register/login/profile | Existing formats; invalid credentials rejected | `test_api_auth.py`, `test_api_users.py`, `test_security.py` |
| Two users access domain records | A user cannot read/change another user's records | `test_api_tickets.py`, `test_api_bookings.py` |
| Ticket lifecycle | Allowed transitions; atomic audit/outbox writes | `test_ticket_phase4.py` |
| Booking lifecycle | UTC output, availability checks, cancellation, audit/outbox writes | `test_booking_phase4.py`, `test_api_bookings.py` |
| Repeated mutation | Same key/payload replays; changed payload conflicts; no duplicate event | `test_phase2_durability.py`, `test_ticket_phase4.py` |
| Approve/reject/expire | Approve executes once; reject/expire does not execute; owner-scoped decisions | `test_phase5_orchestrator.py`, `test_phase2_durability.py` |
| Typed confirmation | Resolves the saved pending action correctly | `test_confirmation.py` |
| Restart during a multi-agent task | Original request and completed results survive; remaining work continues | `test_phase5_continuation.py`, `test_multi_request_continuation.py` |
| Thread isolation and concurrency | Another owner cannot reuse a thread; same-thread turns serialize | `test_phase5_orchestrator.py`, `test_phase5_continuation.py` |
| Guardrail | Blocked requests cannot reach sensitive tools; live task details remain usable | `test_guardrail.py`, `test_routing_scope.py` |
| Memory | Owner-scoped retrieval/deletion, expiry filtering, optional failure handling | `test_crud.py`, `test_fast_paths.py` |
| FAQ failure | Wrong index or retrieval outage produces the defined unavailable behavior | `test_knowledge_contract.py` |
| Delivery outage and recovery | Outboxes remain durable; retry succeeds; duplicate IDs deduplicate | `test_phase6_events.py`, `test_ticket_phase4.py` |
| Boundary protections | Auth, limits, request IDs, routing and error normalization survive | `test_phase6_gateway.py` |
| Storage ownership | Migrations select only owned tables; HTTP tools do not open chat DB | `test_service_migrations.py`, `test_local_service_split.py`, `test_phase45_graph_adapters.py` |

### Gaps and implementation constraints

- `tests/conftest.py` imports `main.app`; many API tests exercise the combined
  application with an in-memory database. Later phases need composition tests
  for each new entry point with distinct stores and an HTTP boundary, plus a
  deployed frontend smoke test. Existing tests alone are insufficient.
- Current standalone apps override the same `database.get_db` dependency at
  application scope. Combining routers and applying one global override would
  send unrelated routes to the wrong database. Introduce explicit domain
  dependencies, including nested authentication dependencies.
- SQLAlchemy models share metadata. Preserve migration-owned table selection;
  do not use global `Base.metadata.create_all()` to initialize each store.
- The local memory adapter and memory routes must be checked separately: moving
  the API into chat does not by itself ensure graph memory uses the memory DB.
- SQLite decision/thread locks are process-local. The initial consolidated
  deployment should use one process per backend; multiple workers require
  separate concurrency and outbox coordination validation.
- Knowledge currently preloads resources in its own process. Define degraded
  startup/readiness behavior before moving that loading into chat.
- The Dockerfile installs from `pyproject.toml`/`uv.lock` although repository
  guidance identifies `requirements.txt` as runtime authoritative. A later
  clean image build must resolve this discrepancy rather than assuming the
  current local environment proves image completeness.
- Older AGENTS.md descriptions (five agents, two databases, no tests) do not
  describe the current extracted code. This baseline follows source files.

## Rollback baseline

The root-level [docker-compose.split-baseline.yml](../docker-compose.split-baseline.yml)
is an exact copy of the pre-consolidation Compose file. It is a standalone
alternative, not an override to layer over the new Compose configuration.

SHA-256: `b43ddb6eee79567e9b8f6dfb0d6cf088008dab7ded47e366878064d91a0c09b6`.

Before a later runtime cutover, record the actual Compose project name, save
the current backend/frontend image IDs under immutable tags or image archives,
and make a stopped-writer backup of all seven databases and the RAG volume.
Include SQLite WAL/SHM companions when present; do not copy a live `.db` alone.
Store secret configuration separately and securely. No image/data backup or
runtime rollback rehearsal has been performed in this documentation phase.

Rollback procedure for a later phase:

1. Stop the consolidated deployment and all background writers. Do not remove
   volumes. Do not run both layouts against the same files concurrently.
2. Select the recorded source revision and pinned baseline images. The Compose
   copy alone cannot restore old code: its build contexts still use local files
   and the backend image tag is mutable.
3. Reuse the existing data only if schemas stayed compatible. Otherwise restore
   the consistent pre-cutover backup, explicitly accounting for writes made
   since cutover. Do not automatically overwrite newer data.
4. From the repository root, run the baseline with the original project name:

   ```bash
   docker compose -p <original-project-name> -f docker-compose.split-baseline.yml up -d --no-build
   ```

   Restore/tag the saved images first. The original project name also selects
   the original named RAG/cache volumes. Do not use `down -v`.
5. Check login, an existing conversation, one pending decision, owned ticket
   and booking reads, memory, FAQ, and event delivery before reopening traffic.

## Phase 1 completion

- [x] Current deployment, API/schema contracts, and data ownership recorded.
- [x] Required behavior mapped to existing coverage and identified gaps.
- [x] Existing Compose layout preserved as a separate rollback artifact.
- [x] Cutover/rollback prerequisites and source revision recorded.
- [ ] Runtime acceptance and rollback rehearsal: scheduled for implementation
  phases; not claimed as completed by this source baseline.
