"""Standalone local entry point for the ticket domain service.

Run with: ``uv run uvicorn ticket_service.app:app --port 8002``.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ticket_service.routes import router as ticket_router
from utils.exceptions import AppException
from shared_platform.domain_schema import initialize_domain_schema

@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_domain_schema("ticket")
    yield

app = FastAPI(title="Ticket Service", version="v1", lifespan=lifespan)



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

app.dependency_overrides[get_db] = domain_dependency("ticket")

app.include_router(ticket_router)
