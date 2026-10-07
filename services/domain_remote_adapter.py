"""HTTP implementations used when a Phase 4.5 domain flag is enabled."""

from config import BOOKING_SERVICE_URL, MEMORY_SERVICE_URL, TICKET_SERVICE_URL, MEMORY_ADAPTER
from models.user import User
from shared_platform.auth_claims import AuthClaims
from shared_platform.domain_adapter import token_for_claims, token_for_user
from shared_platform.domain_http import request_json


def ticket_request(
    user: User, method: str, path: str, payload: dict | None = None,
    query: dict | None = None, idempotency_key: str | None = None,
) -> dict | list:
    return request_json(
        TICKET_SERVICE_URL, method, path, token_for_user(user), payload, query, idempotency_key
    )


def booking_request(
    user: User, method: str, path: str, payload: dict | None = None,
    query: dict | None = None, idempotency_key: str | None = None,
) -> dict | list:
    return request_json(
        BOOKING_SERVICE_URL, method, path, token_for_user(user), payload, query, idempotency_key
    )


def domain_request_for_claims(
    base_url: str, claims: AuthClaims, method: str, path: str,
    payload: dict | None = None, query: dict | None = None,
    idempotency_key: str | None = None,
) -> dict | list:
    return request_json(base_url, method, path, token_for_claims(claims), payload, query, idempotency_key)


def memory_request(
    user: User, method: str, path: str, payload: dict | None = None,
    query: dict | None = None,
) -> dict | list:
    return request_json(MEMORY_SERVICE_URL, method, path, token_for_user(user), payload, query)


def memory_context(user: User, query: str) -> str:
    """Retrieve privacy-scoped memory context from the extracted memory API."""
    response = memory_request(user, "GET", "/v1/memory/context", query={"query": query})
    return str(response.get("context", ""))
def record_memory_episode(user: User, thread_id: str, summary: str, outcome: str) -> None:
    # Domain tools can remain HTTP clients while memory runs in this process.
    if MEMORY_ADAPTER != "http":
        from services.memory_service import memory_session, remember_episode
        with memory_session() as db:
            remember_episode(db, user.id, thread_id, summary, outcome)
        return
    memory_request(
        user, "POST", "/v1/memory/episodes",
        {"thread_id": thread_id, "summary": summary, "outcome": outcome},
    )
