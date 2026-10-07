"""Local standalone entry point: uvicorn chat_orchestrator.app:app --port 8005."""

from contextlib import asynccontextmanager
import asyncio
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from chat_orchestrator.routes import router
from config import validate_startup_configuration
from database import engine
from logger import request_id_context
from services.chat_service import get_app
from services.knowledge_service import get_knowledge_adapter, LocalKnowledgeAdapter
from memory_service.routes import router as memory_router
from shared_platform.domain_persistence import domain_session
from logger import agent_logger
from utils.exceptions import AppException
from shared_platform.api_protection import install_api_protection


@asynccontextmanager
async def lifespan(_: FastAPI):
    validate_startup_configuration()
    get_app()
    adapter = get_knowledge_adapter()
    task = None
    if isinstance(adapter, LocalKnowledgeAdapter):
        adapter.startup_status = "loading"

        async def preload():
            try:
                await asyncio.to_thread(adapter.preload)
            except Exception:
                adapter.startup_status = "unavailable"
                agent_logger.exception("local_rag_preload_failed")
            else:
                adapter.startup_status = "ready"

        task = asyncio.create_task(preload())
    try:
        yield
    finally:
        if task is not None:
            await task


app = FastAPI(title="Multi-agent Service", version="v1", lifespan=lifespan)


@app.middleware("http")
async def correlation_id(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
    request.state.correlation_id = request_id
    token = request_id_context.set(request_id)
    try:
        response = await call_next(request)
    finally:
        request_id_context.reset(token)
    response.headers["X-Request-ID"] = request_id
    return response


@app.exception_handler(AppException)
async def app_exception_handler(_: Request, exc: AppException):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message, "code": "upstream_error", "correlation_id": _.state.correlation_id}, headers=exc.headers)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/ready")
def ready():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        with domain_session("memory") as memory_db:
            memory_db.execute(text("SELECT 1"))
    except Exception:
        return JSONResponse(status_code=503, content={"status": "not_ready"})
    adapter = get_knowledge_adapter()
    return {"status": "ready", "knowledge": getattr(adapter, "startup_status", None) or "remote"}


app.include_router(router)
app.include_router(memory_router)
install_api_protection(app, "chat")
