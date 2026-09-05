import os
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

LOCAL_DEVELOPMENT_DATABASE_URL = "sqlite:///./app.db"
LOCAL_ENVIRONMENTS = {"development", "dev", "local", "test"}


def get_database_url() -> str:
    """Read the deployment database URL; SQLite is only a local-dev default."""
    configured_url = os.getenv("DATABASE_URL")
    if configured_url:
        return configured_url

    app_environment = os.getenv("APP_ENV", "development").lower()
    if app_environment in LOCAL_ENVIRONMENTS:
        return LOCAL_DEVELOPMENT_DATABASE_URL
    raise RuntimeError(
        "DATABASE_URL must be set when APP_ENV is not a local development environment"
    )


SQLALCHEMY_DATABASE_URL = get_database_url()
_engine_options = {"pool_pre_ping": True}
if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
    _engine_options["connect_args"] = {"check_same_thread": False}

engine = create_engine(SQLALCHEMY_DATABASE_URL, **_engine_options)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def get_db_session():
    """Use outside FastAPI requests, for example from LangGraph tools."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
