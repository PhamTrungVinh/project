# Phase 1 start: database configuration and supported LLM scope

## Database configuration

`database.py` now reads `DATABASE_URL` first. SQLite remains available only when `APP_ENV` is one of `development`, `dev`, `local`, or `test`; its explicit default is `sqlite:///./app.db`. Any other environment without `DATABASE_URL` fails at startup rather than silently writing to local SQLite.

The PostgreSQL Compose configuration already supplies `DATABASE_URL`; non-SQLite engines no longer receive SQLite-only `check_same_thread` options. Connections enable `pool_pre_ping` to detect stale pooled connections.

This starts Phase 1 step 1 only. Alembic, database migration, checkpoint migration, and RAG artifact migration remain pending.

## Supported LLM scope

The LangGraph router and supervisor now allow only `faq`, `ticket`, `booking`, and `it_support`. FAQ means company-policy/knowledge-base requests. General questions, web search, calculators, and personal-memory requests are blocked by the guardrail. Guardrail-allowed standalone pleasantries are handled by the IT-support LLM agent.

`agents/web_agent.py` was removed. The IT-support module remains active and can use its search tool. Generic web-agent source remains removed.
