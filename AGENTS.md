# AGENTS.md

LangGraph multi-agent customer-support assistant (Python 3.13, uv venv). A router sends each query to one of five agents: FAQ (RAG over HR PDF), web search/calculator, ticket, booking, IT support. Includes guardrail, HITL approval, and long-term memory.

## Run

- UI: `streamlit run app.py` (in repo root). CLI REPL: `python main.py` (use the `.venv` Python, 3.13).
- The `project` script in `pyproject.toml` is a decoy — it points to `src/project/__init__.py`, a stub that prints "Hello from project!". Ignore it.
- `requirements.txt` is the real dependency list (installed into `.venv`). `pyproject.toml` deps are stale/incomplete — do not trust or edit them for runtime imports.

## Config / env

- `.env` (gitignored, loaded by `config.py`) requires `GROQ_API` and `OPENROUTER_API_KEY` (`os.environ` hard-fail); `TAVILY_API_KEY` optional; `HITL_ENABLED` (default `true`) toggles HITL; `LANGSMITH_*` enables LangSmith tracing.
- `config.py:14` `PDF_PATH` is hardcoded to a Windows path that does not exist here; the real file is `FSoft_HR.pdf` at repo root. The FAQ agent crashes on first use until `PDF_PATH` is fixed.
- Sentry: none. Observability is `log/agent/agent.log` and `log/db/db.log` (rotating file loggers). Comments/code in several files are Vietnamese — preserve them.

## Graph wiring (graph.py)

Flow: `START → guardrail → context → router → child agent`. Router returns one of `faq|ticket|it_support|booking|web`; child agents loop through their own `*_tools` via `should_continue`.

- `load_memory` / `trim_memory` nodes are registered but **not reachable** — nothing edges into `load_memory`, so `state["retrieved_memory"]` is always empty even though all child agents read it. To activate memory: connect `guardrail → load_memory → trim_memory → context` (or delete the dead nodes).
- `guardrail_decision` (guardrail.py:77) returns `"allowed"` when the input is NOT blocked and `"blocked"` when it IS — inverted from the field name. Don't "fix" the names without fixing the mapping in `graph.py:98`.
- HITL: compiled with `interrupt_before=["ticket_tools","booking_tools"]` only when `HITL_ENABLED`. `hitl.py:SENSITIVE_TOOLS` decides which tools need approval; non-sensitive interrupts auto-resume via `app.py:process_graph_result`. Rejection works by injecting a "rejected" `ToolMessage` through `app.update_state`.
- `context_node` regex-detects an email in the user's message and upserts it to `conversation_context`; tools inject `user_email`/`user_name` via `InjectedState`.

## Data stores

- Two SQLite DBs (gitignored, created on import): `app.db` holds business + memory tables (tickets, bookings, conversation_context, semantic_memory, episodic_memory), schema auto-created by `db.py:init_db()`. `checkpoints.db` is the LangGraph `SqliteSaver` checkpointer keyed by `thread_id`; `memory/working_memory.py:clear_working_memory` deletes from its `checkpoints`/`writes` tables directly.
- RAG (`rag/setup.py:build_rag_resources`) is lazily built and process-cached: hybrid BM25 + FAISS dense + rerank + MMR over `faiss_index/`. CrossEncoder model downloads on first run (needs network).
- No tests, no lint/typecheck, no CI configured.
