"""Validated local gateway for frontend routes.

Run with: ``./.venv/bin/uvicorn gateway.app:app --port 8080``.
"""

import os
import re
import time
import uuid
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from jose import JWTError, jwt


load_dotenv()

BACKEND_URL = os.getenv("GATEWAY_BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")
CHAT_URL = os.getenv("GATEWAY_CHAT_URL", "http://127.0.0.1:8005").rstrip("/")
TICKET_URL = os.getenv("GATEWAY_TICKET_URL", BACKEND_URL).rstrip("/")
BOOKING_URL = os.getenv("GATEWAY_BOOKING_URL", BACKEND_URL).rstrip("/")
IDENTITY_URL = os.getenv("GATEWAY_IDENTITY_URL", BACKEND_URL).rstrip("/")
MEMORY_URL = os.getenv("GATEWAY_MEMORY_URL", BACKEND_URL).rstrip("/")
MAX_BODY_BYTES = int(os.getenv("GATEWAY_MAX_BODY_BYTES", str(1024 * 1024)))
RATE_LIMIT_PER_MINUTE = int(os.getenv("GATEWAY_RATE_LIMIT_PER_MINUTE", "120"))
UPSTREAM_TIMEOUT_SECONDS = float(os.getenv("GATEWAY_UPSTREAM_TIMEOUT_SECONDS", "30"))

_request_times: dict[str, deque[float]] = defaultdict(deque)
REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")


def _target(path: str, method: str) -> tuple[str, bool] | None:
    parts = path.strip("/").split("/")
    if any(part in {".", ".."} or "\\" in part for part in parts):
        return None
    if parts == ["auth", "login"] and method == "POST":
        return IDENTITY_URL, True
    if parts == ["auth", "register"] and method == "POST":
        return IDENTITY_URL, True
    if parts == ["v1", "chat", "messages"] and method == "POST":
        return CHAT_URL, False
    if (len(parts) == 4 and parts[:2] == ["v1", "pending-actions"]
            and parts[3] == "decision" and method == "POST"):
        return CHAT_URL, False
    if parts[0] == "tickets":
        return TICKET_URL, False
    if parts[0] == "bookings":
        return BOOKING_URL, False
    if parts[0] == "users":
        return IDENTITY_URL, False
    if parts[:2] == ["v1", "memory"]:
        return MEMORY_URL, False
    if parts == ["v1", "chat", "conversations"]:
        return CHAT_URL, False
    return None


def _claims(token: str) -> dict | None:
    secret = os.getenv("JWT_SECRET_KEY")
    if not secret:
        raise RuntimeError("JWT_SECRET_KEY is required for the gateway")
    try:
        claims = jwt.decode(token, secret, algorithms=["HS256"])
        subject = int(claims["sub"])
        if subject <= 0:
            return None
        return claims
    except (JWTError, KeyError, TypeError, ValueError):
        return None


def _allow_request(key: str) -> bool:
    now = time.monotonic()
    hits = _request_times[key]
    while hits and hits[0] <= now - 60:
        hits.popleft()
    if len(hits) >= RATE_LIMIT_PER_MINUTE:
        return False
    hits.append(now)
    return True


def _error(status: int, code: str, message: str, correlation_id: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"detail": message, "code": code, "correlation_id": correlation_id},
    )


@asynccontextmanager
async def lifespan(_: FastAPI):
    if MAX_BODY_BYTES < 1 or RATE_LIMIT_PER_MINUTE < 1 or UPSTREAM_TIMEOUT_SECONDS <= 0:
        raise RuntimeError("Gateway limits and timeout must be positive")
    if not os.getenv("JWT_SECRET_KEY"):
        raise RuntimeError("JWT_SECRET_KEY is required for the gateway")
    for name, url in (("GATEWAY_BACKEND_URL", BACKEND_URL), ("GATEWAY_CHAT_URL", CHAT_URL),
                      ("GATEWAY_TICKET_URL", TICKET_URL), ("GATEWAY_BOOKING_URL", BOOKING_URL),
                      ("GATEWAY_IDENTITY_URL", IDENTITY_URL), ("GATEWAY_MEMORY_URL", MEMORY_URL)):
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise RuntimeError(f"{name} must be an HTTP URL")
    yield


app = FastAPI(title="Customer Support Gateway", version="v1", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[item.strip() for item in os.getenv(
        "GATEWAY_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(",") if item.strip()],
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Request-ID"],
    expose_headers=["X-Request-ID"],
)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    supplied = request.headers.get("X-Request-ID", "")
    request_id = supplied if REQUEST_ID_PATTERN.fullmatch(supplied) else uuid.uuid4().hex
    request.state.correlation_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


@app.get("/health")
def health():
    return {"status": "ok"}


async def _send_upstream(url: str, method: str, headers: dict[str, str], body: bytes) -> httpx.Response:
    async with httpx.AsyncClient(timeout=UPSTREAM_TIMEOUT_SECONDS, follow_redirects=False) as client:
        return await client.request(method, url, headers=headers, content=body)


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def proxy(path: str, request: Request):
    correlation_id = request.state.correlation_id
    destination = _target(path, request.method)
    if destination is None:
        return _error(404, "route_not_found", "Route not found", correlation_id)
    base_url, public = destination

    authorization = request.headers.get("Authorization", "")
    claims = None
    if not public:
        if not authorization.startswith("Bearer "):
            return _error(401, "unauthorized", "Bearer token required", correlation_id)
        claims = _claims(authorization[7:])
        if claims is None:
            return _error(401, "unauthorized", "Invalid or expired token", correlation_id)

    key = f"subject:{claims['sub']}" if claims else f"ip:{request.client.host if request.client else 'unknown'}"
    if not _allow_request(key):
        response = _error(429, "rate_limited", "Too many requests", correlation_id)
        response.headers["Retry-After"] = "60"
        return response

    content_length = request.headers.get("Content-Length")
    if content_length:
        try:
            if int(content_length) > MAX_BODY_BYTES:
                return _error(413, "request_too_large", "Request body is too large", correlation_id)
        except ValueError:
            return _error(400, "invalid_content_length", "Invalid Content-Length", correlation_id)
    body = await request.body()
    if len(body) > MAX_BODY_BYTES:
        return _error(413, "request_too_large", "Request body is too large", correlation_id)

    headers = {"X-Request-ID": correlation_id}
    if authorization:
        headers["Authorization"] = authorization
    for name in ("Content-Type", "Accept", "Idempotency-Key"):
        value = request.headers.get(name)
        if value:
            headers[name] = value
    url = f"{base_url}/{path}"
    if request.url.query:
        url += f"?{request.url.query}"
    try:
        upstream = await _send_upstream(url, request.method, headers, body)
    except (httpx.TimeoutException, httpx.RequestError):
        return _error(503, "upstream_unavailable", "Upstream service is unavailable", correlation_id)
    response_headers = {}
    for name in ("content-type", "location", "retry-after", "www-authenticate"):
        value = upstream.headers.get(name)
        if value:
            response_headers[name] = value
    if upstream.status_code >= 400:
        try:
            payload = upstream.json()
        except ValueError:
            payload = {}
        detail = payload.get("detail", "Upstream request failed") if isinstance(payload, dict) else "Upstream request failed"
        response_headers.pop("content-type", None)
        return JSONResponse(
            status_code=upstream.status_code,
            content={"detail": detail, "code": payload.get("code", "upstream_error") if isinstance(payload, dict) else "upstream_error",
                     "correlation_id": correlation_id},
            headers=response_headers,
        )
    return Response(content=upstream.content, status_code=upstream.status_code, headers=response_headers)
