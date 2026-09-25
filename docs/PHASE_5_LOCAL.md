# Phase 5 local chat orchestrator

Run these commands from the repository root. The backend and orchestrator use
the same local `app.db` and `checkpoints.db` so existing accounts and conversations
remain available while `/chat/` is kept for compatibility.

```bash
./.venv/bin/alembic upgrade head
./.venv/bin/uvicorn main:app --port 8000
```

In another terminal:

```bash
./.venv/bin/uvicorn chat_orchestrator.app:app --port 8005
```

Start the frontend from `frontend/` with the chat base URL pointing to the
orchestrator. Other API calls still use the backend on port 8000.

```bash
VITE_CHAT_API_BASE=http://localhost:8005 npm run dev
```

The frontend sends chat turns to `POST /v1/chat/messages` and uses
`POST /v1/pending-actions/{id}/decision` for the approval buttons. A decision
body contains only `{"decision":"approve"}` or `{"decision":"reject"}`.
Identity comes from the login JWT. The response contains the thread ID,
correlation ID, answer, route, and current pending actions.

To use the old conversational confirmation flow, reply in the chat input.
`/chat/` remains available on the backend for older clients.

Run the local checks with:

```bash
APP_ENV=test ./.venv/bin/python -m pytest -q
cd frontend && npm run build
```
