import os
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from sqlalchemy import text

from database import Base, engine
from logger import app_logger, request_id_context
from utils.exceptions import AppException
from routers import auth, users, tickets, bookings, chat

Base.metadata.create_all(bind=engine)

APP_VERSION = os.getenv("APP_VERSION", "0.1.0")

app = FastAPI(title="FPT Customer Chatbot API", version=APP_VERSION)

_metrics = {"requests_total": 0, "requests_5xx_total": 0, "request_duration_seconds_total": 0.0}

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # restrict to specific domains in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_observability(request: Request, call_next):
    """Attach a request ID, emit a structured completion record, and count requests."""
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
    token = request_id_context.set(request_id)
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        elapsed = time.perf_counter() - started
        _metrics["requests_total"] += 1
        _metrics["requests_5xx_total"] += 1
        _metrics["request_duration_seconds_total"] += elapsed
        app_logger.exception("request_failed method=%s path=%s duration_ms=%.2f", request.method, request.url.path, elapsed * 1000)
        raise
    finally:
        request_id_context.reset(token)

    elapsed = time.perf_counter() - started
    _metrics["requests_total"] += 1
    _metrics["request_duration_seconds_total"] += elapsed
    if response.status_code >= 500:
        _metrics["requests_5xx_total"] += 1
    response.headers["X-Request-ID"] = request_id
    log_token = request_id_context.set(request_id)
    try:
        app_logger.info("request_completed method=%s path=%s status_code=%s duration_ms=%.2f", request.method, request.url.path, response.status_code, elapsed * 1000)
    finally:
        request_id_context.reset(log_token)
    return response


@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.message},
        headers=exc.headers,
    )


@app.get("/health", tags=["health"])
def health_check():
    """Liveness: the web process can serve requests; it does not probe dependencies."""
    return {"status": "ok"}


@app.get("/ready", tags=["health"])
def readiness_check():
    """Readiness: the application's required SQL database is reachable."""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:
        app_logger.exception("readiness_check_failed")
        return JSONResponse(status_code=503, content={"status": "not_ready"})
    return {"status": "ready"}


@app.get("/version", tags=["health"])
def version():
    return {"service": "fpt-customer-chatbot-api", "version": APP_VERSION}


@app.get("/metrics", include_in_schema=False)
def metrics():
    """Prometheus text exposition for the baseline monolith metrics."""
    body = "\n".join((
        "# HELP http_requests_total Number of completed HTTP requests.",
        "# TYPE http_requests_total counter",
        f"http_requests_total {_metrics['requests_total']}",
        "# HELP http_requests_5xx_total Number of completed HTTP requests with 5xx status.",
        "# TYPE http_requests_5xx_total counter",
        f"http_requests_5xx_total {_metrics['requests_5xx_total']}",
        "# HELP http_request_duration_seconds_total Sum of completed HTTP request durations in seconds.",
        "# TYPE http_request_duration_seconds_total counter",
        f"http_request_duration_seconds_total {_metrics['request_duration_seconds_total']}",
        "",
    ))
    return Response(content=body, media_type="text/plain; version=0.0.4; charset=utf-8")


app.include_router(auth.router)
app.include_router(users.router)
app.include_router(tickets.router)
app.include_router(bookings.router)
app.include_router(chat.router)