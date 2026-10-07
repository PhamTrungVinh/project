# Phase 5: validation and cutover

Date: 2026-09-30. Baseline source revision:
`bfc9702fef3d41ffbd7295130c9fb0d8572c24eb`.

## Validation evidence

- Full local regression suite: **148 passed**, four existing dependency
  deprecation warnings. Tests used a temporary checkpoint database.
- Both backend and frontend images built successfully. The frozen `uv.lock`
  installed the required runtime imports; `requirements.txt` is absent from
  this checkout. No dependency manifest changes were needed.
- The new images started against copies of all existing SQLite databases.
  Startup migrations succeeded; business and chat readiness passed.
- Through the real Nginx proxy: registration/login/profile, ticket creation,
  idempotent replay and conflict, ticket status update, booking/cancellation,
  real embedding memory save/retrieval, chat and conversation listing passed.
- A seeded pending action in the copied chat store exercised the real approval
  endpoint, ticket HTTP tool execution, and repeat-decision replay.
- Restarting both backends preserved records, conversations, memory, and the
  approval result. Both outboxes drained successfully.
- RAG reported `knowledge: ready`. A real FAQ request returned HTTP 200 with
  an answer rather than the unavailable fallback.
- Rollback was rehearsed against the copied stores after the new stack wrote
  records: the pinned old services could read identity/domain records, list
  conversations, retrieve memory, and replay the completed approval. The old
  UI served successfully.

Staging writes were confined to copied databases under the ignored backup
directory. Live acceptance uses read-only checks to avoid adding test accounts
or business records to the user's databases.

## Recovery artifacts

Artifacts are stored under `backups/consolidation-20260930/`, excluded from
Git and Docker builds. Resolved Compose files contain secrets and are owner-only;
do not publish them. The directory records the source revision and provides
`rollback-compose.json` with absolute original data mounts and pinned images.

- Backend image: `fpt-support-local:pre-consolidation-20260930`.
- Frontend image: `project-frontend:pre-consolidation-20260930`.

Docker could not recover the stopped old frontend's missing image layers, so
the rollback frontend was rebuilt from the recorded baseline source with its
original localhost:8080 API settings. It passed the rollback rehearsal. The
backend rollback image is the original image used by the running split stack.
Keep these tags and the backup directory; image pruning can invalidate recovery.

## Rollback procedure

Stop writers before switching layouts. Do not use `down -v`.

```bash
docker compose -p project stop
docker compose -p project -f backups/consolidation-20260930/rollback-compose.json up -d --no-build --remove-orphans
```

Schemas remain compatible, so the rehearsal reused data without restoring an
older snapshot. If restoration is necessary, stop all services first, preserve
the post-cutover data separately, then restore the stopped-writer snapshot.
Restoring older data discards intervening writes; do not do it automatically.

## Cleanup decisions

The default Compose and Docker entry point select the consolidated architecture.
README, environment example, and the current Mermaid diagram describe it.
Legacy `main.py`, standalone apps, gateway, worker CLI, and old migration
histories are retained for rollback and existing compatibility tests. They are
not required processes in the current deployment. Older Draw.io diagrams and
`PHASE_*` documents describe the earlier extraction, not the current topology.

This is a local SQLite deployment with one process per backend. Per-backend
rate quotas, cached model startup, and the RAG degraded mode remain as described
in phase 4; this validation does not certify a scaled production deployment.

## Live cutover

**Complete on 2026-09-30.** The `project` Compose deployment now runs only
`business-backend`, `chat-orchestrator`, and `frontend`. Both backend health
checks passed; chat readiness reported `knowledge: ready`. Obsolete containers
were removed while existing bind-mounted databases and named volumes were
retained. Temporary validation/rollback stacks were removed.

Before startup, all seven SQLite stores were copied with their writers stopped
to `backups/consolidation-20260930/data-snapshot/`. Each passed SQLite
`quick_check`. The RAG index was archived as `faiss-data.tar`; the HR PDF and
private environment configuration were also preserved.

After cutover, all **22 tables across seven databases** passed integrity checks
and exactly matched the backup's row counts and content digests. The manifest
is `database-manifest.json` inside the ignored backup directory.

Live read-only checks passed for the frontend, referenced static assets,
business readiness, unauthenticated access rejection, and authenticated
profile/ticket/booking/conversation/memory routes through Nginx. These checks
used an existing identity and created no test accounts or business records.
Write flows, approval replay, restart recovery, event delivery, FAQ, and
rollback were validated on copied data as described above.

The application is available at **http://localhost:5173**, with the API at
`/api`. Phase 5 and the five-phase consolidation are complete. Source changes
remain in the working tree; no Git commit was created.
