# Phase 1 start: database configuration and supported LLM scope

## Database configuration

`database.py` now reads `DATABASE_URL` first. SQLite remains available only when `APP_ENV` is one of `development`, `dev`, `local`, or `test`; its explicit default is `sqlite:///./app.db`. Any other environment without `DATABASE_URL` fails at startup rather than silently writing to local SQLite.

The PostgreSQL Compose configuration already supplies `DATABASE_URL`; non-SQLite engines no longer receive SQLite-only `check_same_thread` options. Connections enable `pool_pre_ping` to detect stale pooled connections.

This starts Phase 1 step 1 only. Alembic, database migration, checkpoint migration, and RAG artifact migration remain pending.

## Supported LLM scope

The LangGraph router and supervisor now allow only `faq`, `ticket`, `booking`, and `it_support`. FAQ means company-policy/knowledge-base requests. General questions, web search, calculators, and personal-memory requests are blocked by the guardrail. Guardrail-allowed standalone pleasantries are handled by the IT-support LLM agent.

`agents/web_agent.py` was removed. The IT-support module remains active and can use its search tool. Generic web-agent source remains removed.


## Completing Phase 1

- Run `uv run alembic upgrade head` before starting the service. The container
  command does this automatically. Existing pre-Alembic databases must first be
  baselined with `uv run alembic stamp head`; this records the revision without
  changing tables or data.
- Use `scripts/migrate_sqlite_to_postgres.py` to copy a SQLite database only into
  an empty PostgreSQL target that has already run `alembic upgrade head`. The
  script verifies row counts, password-hash presence, timestamps, foreign-key
  ownership, and unique conversation thread ownership.
- Outside local development, `DATABASE_URL` must be PostgreSQL and checkpoint
  state uses `CHECKPOINT_DATABASE_URL` (or the PostgreSQL database URL) through
  LangGraph's `PostgresSaver`. Its schema is initialized by `saver.setup()`.
- Outside local development, set a remote `RAG_ARTIFACT_URI` and immutable
  `RAG_ARTIFACT_VERSION`. Publish the PDF/index bundle with
  `scripts/publish_rag_artifacts.py`; serving code lazily caches that exact
  version and never rebuilds an index during a query.
