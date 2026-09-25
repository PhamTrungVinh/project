"""Create the small, owned schema used by each standalone local service."""

from sqlalchemy import inspect

from database import Base
from shared_platform.domain_persistence import session_factory_for


DOMAIN_TABLES = {
    "ticket": ("tickets", "ticket_audit", "ticket_outbox", "idempotency_records"),
    "booking": ("bookings", "booking_audit", "booking_outbox", "idempotency_records"),
    "memory": ("semantic_memory", "episodic_memory"),
}


def initialize_domain_schema(domain: str) -> None:
    """Bootstrap an empty local database without creating shared-platform tables."""
    try:
        table_names = DOMAIN_TABLES[domain]
    except KeyError as exc:
        raise ValueError(f"Unsupported domain schema: {domain}") from exc

    # Importing registers all mapped tables on the shared SQLAlchemy metadata.
    import models  # noqa: F401

    bind = session_factory_for(domain).kw["bind"]
    Base.metadata.create_all(
        bind=bind,
        tables=[Base.metadata.tables[name] for name in table_names],
    )
    # create_all does not add columns to an existing local SQLite table.
    # Keep previously created standalone domain DBs usable after Phase 6.
    if bind.dialect.name == "sqlite" and domain in {"ticket", "booking"}:
        outbox_table = f"{domain}_outbox"
        existing = {column["name"] for column in inspect(bind).get_columns(outbox_table)}
        with bind.begin() as connection:
            for column in ("correlation_id", "causation_id"):
                if column not in existing:
                    connection.exec_driver_sql(
                        f"ALTER TABLE {outbox_table} ADD COLUMN {column} VARCHAR(128)"
                    )
