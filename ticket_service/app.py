"""Standalone local entry point for the ticket domain service.

Run with: ``uv run uvicorn ticket_service.app:app --port 8002``.
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ticket_service.routes import router as ticket_router
from utils.exceptions import AppException
from shared_platform.request_context import request_context_middleware

app = FastAPI(title="Ticket Service", version="v1")
app.middleware("http")(request_context_middleware)



@app.exception_handler(AppException)
async def app_exception_handler(_: Request, exc: AppException):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/ready")
def ready():
    return {"status": "ready"}
app.include_router(ticket_router)
