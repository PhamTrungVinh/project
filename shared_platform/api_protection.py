"""Request protections for APIs served directly behind Nginx."""
import os
import time
import uuid
from collections import defaultdict, deque

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException

from shared_platform.request_context import REQUEST_ID_PATTERN
from utils.security import decode_access_token


def install_api_protection(app, service):
    hits = defaultdict(deque)
    max_body = int(os.getenv("API_MAX_BODY_BYTES", "1048576"))
    rate = int(os.getenv("API_RATE_LIMIT_PER_MINUTE", "120"))
    if max_body < 1 or rate < 1:
        raise RuntimeError("API request limits must be positive")

    def error(request, status, detail, code="upstream_error", headers=None):
        return JSONResponse(status_code=status, content={"detail": detail, "code": code,
            "correlation_id": request.state.correlation_id}, headers=headers)

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        return error(request, exc.status_code, exc.detail, headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        from fastapi.encoders import jsonable_encoder
        return error(request, 422, jsonable_encoder(exc.errors()))

    @app.middleware("http")
    async def protect(request: Request, call_next):
        supplied = request.headers.get("X-Request-ID", "")
        request.state.correlation_id = supplied if REQUEST_ID_PATTERN.fullmatch(supplied) else uuid.uuid4().hex
        path = request.url.path
        public = path in {"/auth/login", "/auth/register"} and request.method == "POST" and service == "business"
        operational = path in {"/health", "/ready"}
        allowed = (path.startswith(("/auth/", "/users/", "/tickets", "/bookings")) if service == "business"
                   else path.startswith(("/v1/chat/", "/v1/pending-actions/", "/v1/memory")))

        async def handle():
            if operational:
                return await call_next(request)
            if not allowed:
                return error(request, 404, "Route not found", "route_not_found")
            claims = None
            if not public:
                authorization = request.headers.get("Authorization", "")
                claims = decode_access_token(authorization[7:]) if authorization.startswith("Bearer ") else None
                try:
                    valid = claims is not None and int(claims["sub"]) > 0
                except (KeyError, TypeError, ValueError):
                    valid = False
                if not valid:
                    return error(request, 401, "Invalid or expired token", "unauthorized")
            key = f"subject:{claims['sub']}" if claims else f"ip:{request.client.host if request.client else 'unknown'}"
            now = time.monotonic()
            # Drop inactive identities rather than accumulating keys forever.
            for old in list(hits):
                if not hits[old] or hits[old][-1] <= now - 60:
                    del hits[old]
            bucket = hits[key]
            while bucket and bucket[0] <= now - 60:
                bucket.popleft()
            if len(bucket) >= rate:
                return error(request, 429, "Too many requests", "rate_limited", {"Retry-After": "60"})
            bucket.append(now)
            length = request.headers.get("Content-Length")
            if length is not None:
                try:
                    size = int(length)
                    if size < 0:
                        raise ValueError
                except ValueError:
                    return error(request, 400, "Invalid Content-Length", "invalid_content_length")
                if size > max_body:
                    return error(request, 413, "Request body is too large", "request_too_large")
            body = bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > max_body:
                    return error(request, 413, "Request body is too large", "request_too_large")
            request._body = bytes(body)
            return await call_next(request)

        response = await handle()
        response.headers["X-Request-ID"] = request.state.correlation_id
        return response

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[origin.strip() for origin in os.getenv(
            "API_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
        ).split(",") if origin.strip()],
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )
