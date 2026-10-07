# Phase 2: memory and RAG inside the multi-agent service

This records the phase 2 layout. [Phase 3](CONSOLIDATION_PHASE_3.md) now combines
the identity, ticket, and booking APIs; use its URL settings with current Compose.

The default Compose configuration now starts eight containers. The existing
`chat-orchestrator` service/entry point hosts chat, approvals, conversations,
all `/v1/memory` routes, and local RAG. Ticket and booking still use HTTP.
Identity, domain APIs, gateway, and event delivery remain separate for the next
phases. The original ten-container configuration remains in
`docker-compose.split-baseline.yml`.

## Data and routing

- Chat data remains at `local_data/chat/chat_service.db`; checkpoints remain
  at `local_data/chat/chat_checkpoints.db`.
- Memory remains at `local_data/memory/memory_service.db`, mounted at
  `/memory-data` in chat. Both chat and memory migrations run before startup.
- The graph's local memory lookup, fact tool, background episode recording,
  and HTTP domain tools' episode recording select `MEMORY_DATABASE_URL`.
  Legacy monolith callers without that variable retain their original store.
- Memory routes use an explicit domain session dependency; chat routes keep
  their own database dependency. Ownership still comes from authenticated JWTs.
- Gateway memory requests now go to chat on port 8005. Browser API paths and
  bases are unchanged.
- Chat inherits the existing PDF, `faiss_data`, and `hf_cache` mounts. No index
  or database is copied or rebuilt by this change.

## RAG startup

Local RAG preload runs in a background thread managed by the application's
lifespan. Chat can accept requests while it loads. FAQ requests return the
existing unavailable message until loading succeeds. Failed preload is logged
and stays unavailable until service restart; repair the artifact/model access
before restarting. Query requests do not retry expensive startup work.

`/health` reports process liveness. `/ready` checks chat and memory database
connectivity and reports `knowledge` as `loading`, `ready`, or `unavailable`
(`remote` with the original HTTP adapter). RAG failure does not make the whole
chat API unready. Connectivity checks do not validate migration completeness.
Shutdown waits for an in-progress preload; downloading models may delay it.

## Running

For Compose, preserve the project name and existing volumes. Stop the old
layout before starting the new one, following the phase 1 backup prerequisites:

```bash
docker compose stop
docker compose up --build -d --remove-orphans
```

These commands are deployment instructions; implementing this phase does not
automatically run them or migrate existing data.

For a standalone local chat process, keep identity, ticket, booking and gateway
running as described in `LOCAL_SERVICE_SPLIT.md`. Configure the chat shell:

```bash
export DATABASE_URL=sqlite:///./chat_service.db
export CHAT_DATABASE_URL=sqlite:///./chat_service.db
export CHECKPOINT_SQLITE_PATH=chat_checkpoints.db
export MEMORY_DATABASE_URL=sqlite:///./memory_service.db
export MEMORY_ADAPTER=local KNOWLEDGE_ADAPTER=local
export TICKET_ADAPTER=http BOOKING_ADAPTER=http
export TICKET_SERVICE_URL=http://127.0.0.1:8002
export BOOKING_SERVICE_URL=http://127.0.0.1:8003
export PDF_PATH=./FSoft_HR.pdf FAISS_INDEX_PATH=./faiss_index
./.venv/bin/python -m scripts.migrate_service chat
./.venv/bin/python -m scripts.migrate_service memory
./.venv/bin/uvicorn chat_orchestrator.app:app --port 8005
```

Set `GATEWAY_MEMORY_URL=http://127.0.0.1:8005` in the gateway process.
Use one worker for this initial SQLite deployment. Existing provider/JWT
environment settings still apply.

## Validation

`tests/test_consolidated_ai.py` checks memory ownership using separate temporary
stores, authenticated API isolation/deletion, graph retrieval, background and
domain-tool episode writes, and degraded startup without model downloads.
These tests stub embeddings; real model loading and a deployed Docker smoke
test are separate operational checks. No database schema changes are needed.
