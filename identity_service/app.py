"""Standalone identity API with its own local database."""

import os
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import get_db
from routers.auth import router as auth_router
from routers.users import router as users_router
from shared_platform.request_context import request_context_middleware
from utils.exceptions import AppException


url = os.getenv("IDENTITY_DATABASE_URL", "sqlite:///./identity_service.db")
engine = create_engine(url, pool_pre_ping=True, connect_args={"check_same_thread": False} if url.startswith("sqlite") else {})
Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def identity_db():
    with Session() as db:
        yield db


app = FastAPI(title="Identity Service", version="v1")
app.middleware("http")(request_context_middleware)
app.dependency_overrides[get_db] = identity_db
app.include_router(auth_router)
app.include_router(users_router)


@app.exception_handler(AppException)
async def app_exception_handler(_: Request, exc: AppException):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/ready")
def ready():
    return {"status": "ready"}
