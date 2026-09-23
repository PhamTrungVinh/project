"""Standalone local entry point for the booking domain service.

Run with: ``uv run uvicorn booking_service.app:app --port 8003``.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from booking_service.routes import router as booking_router
from utils.exceptions import AppException
from shared_platform.domain_schema import initialize_domain_schema

@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_domain_schema("booking")
    yield

app = FastAPI(title="Booking Service", version="v1", lifespan=lifespan)



@app.exception_handler(AppException)
async def app_exception_handler(_: Request, exc: AppException):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/ready")
def ready():
    return {"status": "ready"}
from database import get_db
from shared_platform.domain_persistence import domain_dependency

app.dependency_overrides[get_db] = domain_dependency("booking")

app.include_router(booking_router)
