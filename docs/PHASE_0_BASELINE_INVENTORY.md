# Phase 0 baseline inventory

This records the current monolith before extraction. It documents observed behavior, not the target service design.

## Runtime, dependencies, and side effects

- `main.py` runs one FastAPI process; Docker starts `uvicorn main:app`.
- Authentication is a one-day HS256 JWT (`sub` is numeric user ID). `get_current_user` validates the token and loads the user. Auth and operational endpoints are public; all business endpoints need `Authorization: Bearer <token>`.
- SQLAlchemy hard-codes `sqlite:///./app.db`; `graph/graph.py` uses local `checkpoints.db` with `SqliteSaver`, keyed by thread ID. RAG uses `FSoft_HR.pdf` and `faiss_index/`.
- External APIs/models: Groq (guardrail/router/agents/RAG), Tavily (web and IT search), Hugging Face embeddings, and CrossEncoder reranking. RAG lazily builds resources and may download models/create FAISS artifacts.
- Side effects are SQLite writes, LangGraph checkpoint writes, external LLM/search calls, model/index creation, and rotating JSON log writes under `log/agent` and `log/db`. There is no broker, outbox, worker, or scheduled job.

## Public API and contracts

| Endpoint | Input/output | Authorization / behavior |
| --- | --- | --- |
| `POST /auth/register` | JSON: email, password, optional full_name -> user | Public; duplicate email is 409. |
| `POST /auth/login` | OAuth form username (email), password -> bearer token | Public; invalid credentials are 401. |
| `GET /users/me` | -> user | JWT. |
| `POST /tickets/`; `GET /tickets/`; `GET /tickets/{code}`; `PATCH /tickets/{code}`; `PATCH /tickets/{code}/status` | Ticket create/update/status schemas -> ticket | JWT; every read/mutation scopes `owner_id`. List accepts `skip>=0`, `limit=1..200`. |
| `POST /bookings/`; `GET /bookings/`; `GET /bookings/{code}`; `PATCH /bookings/{code}`; `POST /bookings/{code}/cancel` | Booking create/update schemas -> booking | JWT; every read/mutation scopes `owner_id`. |
| `POST /chat/` | message, optional thread_id -> answer, route, thread_id | JWT; synchronously invokes LangGraph. |
| `GET /chat/conversations`; `GET /chat/conversations/{thread_id}` | -> conversation(s) | JWT; owner-scoped. |
| `POST /chat/task-outcome` | thread_id, summary, outcome | JWT; stores episodic memory. |
| `POST /chat/memory/fact`; `DELETE /chat/memory` | fact -> status; -> deletion counts | JWT; writes/deletes caller memory. |
| `GET /health`, `/ready`, `/version`, `/metrics` | liveness, database readiness, build version, Prometheus text | Public. |

### Models

- `UserCreate`: `email`, `password`, optional `full_name`; `UserOut`: `id`, `email`, optional `full_name`; `Token`: `access_token`, `token_type` (`bearer`).
- `TicketCreate`: `content`, `description`, optional `customer_name`, `customer_phone`, `email`; `TicketUpdate` makes each of those optional; `TicketStatusUpdate`: `status`; `TicketOut` adds `id`, `ticket_code`, `status`, `created_at`, `updated_at`.
- `BookingCreate`: `reason`, ISO `time`, optional `note`, `customer_name`, `customer_phone`, `email`; `BookingUpdate` makes each optional; `BookingOut` adds `id`, `booking_code`, `status`, `created_at`, `updated_at`.
- `ChatRequest`: `message`, optional `thread_id`; `ChatResponse`: `answer`, optional `route`, `thread_id`; `ConversationOut`: `id`, `thread_id`, optional `email`, `title`, `created_at`, `updated_at`.
- `TaskOutcomeRequest`: `thread_id`, `summary`, `outcome`; `MemoryFactCreate`: `fact`; `MemoryClearResponse`: `facts_deleted`, `episodes_deleted`.

Pydantic validates inputs. Tickets use `Pending|Resolving|Canceled|Finished`; bookings use `Scheduled|Canceled|Finished`. Responses from `AppException` are `{"detail": "..."}`.

## Persistent data

| Store | Content / access |
| --- | --- |
| `app.db` | `users`, `tickets`, `bookings`, `conversations`, `semantic_memory`, `episodic_memory`; tickets/bookings/conversations/memories carry owner FKs. |
| `checkpoints.db` | LangGraph checkpoint and write tables; local to one process/container. |
| `faiss_index/` | Local FAISS vector index and pickle metadata. |

Users store email/password hash/name. Ticket and booking rows hold display codes, owner, business fields, status, timestamps. Conversations map globally unique thread IDs to owners, optional email/title. Semantic/episodic memory records owner-scoped text with JSON embeddings; episodes also hold thread/outcome.

## LangGraph nodes and tool effects

Flow: `START -> guardrail -> context -> router -> child agent`; relevant child agents return through `supervisor`. `blocked` returns a refusal. `confirmed` returns a prior confirmed operation. The guardrail state flag is true for unsafe input; the conditional mapping must stay aligned with that meaning.

| Nodes | Role / tools |
| --- | --- |
| `guardrail`, `blocked`, `context`, `router`, `supervisor`, `confirmed` | Safety classification, refusal, email extraction/conversation update, route/pending-task handling, orchestration, confirmed response. |
| `rag_agent` | PDF hybrid BM25/FAISS retrieval, rerank/MMR, Groq answer. |
| `web_agent`, `web_tools` | `search_with_cache` (Tavily), `calculator_tool` (numexpr), `remember_fact` (embedding + DB write). |
| `ticket_agent`, `ticket_tools`, `ticket_confirm` | Create/track/update/status ticket. Writes require conversational confirmation; creates/updates may record an episode. |
| `booking_agent`, `booking_tools`, `booking_confirm` | Create/track/update/cancel booking. Writes require conversational confirmation; creates/updates/cancels may record an episode. |
| `it_support_agent`, `it_tools` | IT response with Tavily search. |

HITL is checkpointed `unfinished_tasks`: a requested mutation is held, then the next message is classified confirm/cancel/edit and confirmed saved arguments are called directly. It is not an HTTP approval endpoint.

## Baseline observability

Every response now has `X-Request-ID` (caller supplied or generated). Completion/failure logs are JSON at `log/agent/app.log` with request ID, method, path, status when available, and duration. Existing agent/database logs use the same JSON formatter. `/metrics` exports process-local HTTP request count, 5xx count, and duration total; it resets at restart and does not yet measure tool/RAG/HITL SLOs.
