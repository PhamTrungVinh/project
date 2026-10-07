"""Standalone entry point retained for the split deployment."""
from fastapi import FastAPI
from memory_service.routes import router
from shared_platform.request_context import request_context_middleware

app = FastAPI(title="Memory Service", version="v1")
app.middleware("http")(request_context_middleware)
app.include_router(router)

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/ready")
def ready():
    return {"status": "ready"}
