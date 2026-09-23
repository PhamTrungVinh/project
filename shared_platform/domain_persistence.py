"""Per-domain persistence configuration for the Phase 4 extraction."""

import os
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import LOCAL_ENVIRONMENTS, get_database_url

DOMAIN_DATABASE_ENV = {
    "ticket": "TICKET_DATABASE_URL",
    "booking": "BOOKING_DATABASE_URL",
    "memory": "MEMORY_DATABASE_URL",
}

LOCAL_DOMAIN_DATABASE_URL = {
    "ticket": "sqlite:///./ticket_service.db",
    "booking": "sqlite:///./booking_service.db",
    "memory": "sqlite:///./memory_service.db",
}


def database_url_for(domain: str) -> str:
    """Require a dedicated URL outside local development."""
    try:
        environment_key = DOMAIN_DATABASE_ENV[domain]
    except KeyError as exc:
        raise ValueError(f"Unsupported domain database: {domain}") from exc

    configured_url = os.getenv(environment_key)
    if configured_url:
        return configured_url

    if os.getenv("APP_ENV", "development").lower() in LOCAL_ENVIRONMENTS:
        return LOCAL_DOMAIN_DATABASE_URL[domain]
    raise RuntimeError(f"{environment_key} is required outside local development")


@lru_cache(maxsize=3)
def session_factory_for(domain: str):
    """Return a domain-owned session factory selected by that domain's URL."""
    database_url = database_url_for(domain)
    options = {"pool_pre_ping": True}
    if database_url.startswith("sqlite"):
        options["connect_args"] = {"check_same_thread": False}
    return sessionmaker(autocommit=False, autoflush=False, bind=create_engine(database_url, **options))


@contextmanager
def domain_session(domain: str):
    session = session_factory_for(domain)()
    try:
        yield session
    finally:
        session.close()


def domain_dependency(domain: str):
    def get_domain_db():
        with domain_session(domain) as session:
            yield session

    return get_domain_db
