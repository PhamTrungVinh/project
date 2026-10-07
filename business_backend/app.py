"""Run with uvicorn business_backend.app:app --port 8000."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from database import get_db
from routers.auth import router as auth_router
from routers.users import router as users_router
from ticket_service.routes import router as ticket_router
from booking_service.routes import router as booking_router
from shared_platform.domain_persistence import domain_dependency, domain_session
from shared_platform.request_context import request_context_middleware
from utils.exceptions import AppException
from business_backend.events import event_lifespan
from shared_platform.api_protection import install_api_protection

app = FastAPI(title="Business Backend", version="v1", lifespan=event_lifespan)
app.middleware("http")(request_context_middleware)
install_api_protection(app, "business")

# Only identity routes (including get_current_user) depend on get_db here.
# Ticket and booking routers use their own explicit domain dependencies.
app.dependency_overrides[get_db] = domain_dependency("identity")
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(ticket_router)
app.include_router(booking_router)


@app.exception_handler(AppException)
async def app_exception_handler(_: Request, exc: AppException):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message, "code": "upstream_error", "correlation_id": _.state.correlation_id}, headers=exc.headers)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/ready")
def ready():
    for domain in ("identity", "ticket", "booking", "event"):
        try:
            with domain_session(domain) as db:
                db.execute(text("SELECT 1"))
        except Exception:
            return JSONResponse(status_code=503, content={"status": "not_ready", "database": domain})
    return {"status": "ready"}
