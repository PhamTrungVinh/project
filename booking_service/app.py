"""Standalone local entry point for the booking domain service.

Run with: ``uv run uvicorn booking_service.app:app --port 8003``.
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from booking_service.routes import router as booking_router
from utils.exceptions import AppException
from shared_platform.request_context import request_context_middleware

app = FastAPI(title="Booking Service", version="v1")
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
app.include_router(booking_router)
