"""Metadata and database selection for service-owned Alembic histories."""

import importlib
import os
from pathlib import Path

from alembic import context
from sqlalchemy import MetaData, create_engine, inspect


ROOT = Path(__file__).resolve().parent
SERVICE_TABLES = {
    "identity": (("identity_service.models", "User"),),
    "chat": (("chat_orchestrator.conversation_model", "Conversation"),
             ("chat_orchestrator.pending_action_model", "PendingAction")),
    "ticket": (("ticket_service.models", "Ticket"),
               ("ticket_service.models", "TicketAudit"),
               ("ticket_service.models", "TicketOutbox"),
               ("shared_platform.idempotency_model", "IdempotencyRecord")),
    "booking": (("booking_service.models", "Booking"),
                ("booking_service.models", "BookingAudit"),
                ("booking_service.models", "BookingOutbox"),
                ("shared_platform.idempotency_model", "IdempotencyRecord")),
    "memory": (("memory_service.models", "SemanticMemory"),
               ("memory_service.models", "EpisodicMemory")),
    "event": (("event_service.app", "EventInbox"),),
}
DATABASE_ENV = {
    "identity": "IDENTITY_DATABASE_URL",
    "chat": "CHAT_DATABASE_URL",
    "ticket": "TICKET_DATABASE_URL",
    "booking": "BOOKING_DATABASE_URL",
    "memory": "MEMORY_DATABASE_URL",
    "event": "EVENT_DATABASE_URL",
}
LOCAL_URL = {
    "identity": "sqlite:///./identity_service.db",
    "chat": "sqlite:///./chat_service.db",
    "ticket": "sqlite:///./ticket_service.db",
    "booking": "sqlite:///./booking_service.db",
    "memory": "sqlite:///./memory_service.db",
    "event": "sqlite:///./events.db",
}


def database_url(service: str) -> str:
    if service not in SERVICE_TABLES:
        raise ValueError(f"Unknown service: {service}")
    return os.getenv(DATABASE_ENV[service]) or LOCAL_URL[service]


def owned_metadata(service: str) -> MetaData:
    metadata = MetaData()
    for module_name, class_name in SERVICE_TABLES[service]:
        model = getattr(importlib.import_module(module_name), class_name)
        model.__table__.to_metadata(metadata)
    return metadata


def assert_owned_schema(connection, service: str) -> None:
    """Refuse to adopt an incomplete local database as a migrated service."""
    inspector = inspect(connection)
    tables = set(inspector.get_table_names())
    metadata = owned_metadata(service)
    missing_tables = set(metadata.tables) - tables
    if missing_tables:
        raise RuntimeError(f"{service} schema is missing tables: {sorted(missing_tables)}")
    for name, table in metadata.tables.items():
        existing_columns = {column["name"] for column in inspector.get_columns(name)}
        missing_columns = set(table.columns.keys()) - existing_columns
        existing_indexes = {index["name"] for index in inspector.get_indexes(name)}
        missing_indexes = {index.name for index in table.indexes} - existing_indexes
        if missing_columns or missing_indexes:
            raise RuntimeError(
                f"{service}.{name} needs migration: missing columns={sorted(missing_columns)}, "
                f"indexes={sorted(missing_indexes)}"
            )


def run_env(service: str) -> None:
    configuration = context.config
    url = configuration.attributes.get("database_url") or database_url(service)
    metadata = owned_metadata(service)
    if context.is_offline_mode():
        context.configure(url=url, target_metadata=metadata, literal_binds=True,
                          dialect_opts={"paramstyle": "named"}, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()
        return
    connection = configuration.attributes.get("connection")
    if connection is None:
        engine = create_engine(url, pool_pre_ping=True)
        with engine.connect() as connection:
            context.configure(connection=connection, target_metadata=metadata, compare_type=True)
            with context.begin_transaction():
                context.run_migrations()
        engine.dispose()
    else:
        context.configure(connection=connection, target_metadata=metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()
