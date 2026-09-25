import sqlite3

import pytest
from sqlalchemy import inspect

from shared_platform.domain_persistence import session_factory_for
from shared_platform.domain_schema import initialize_domain_schema


@pytest.mark.parametrize("domain", ["ticket", "booking"])
def test_existing_local_outbox_gets_phase6_columns(domain, tmp_path, monkeypatch):
    database_path = tmp_path / f"{domain}.db"
    outbox_table = f"{domain}_outbox"
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            f"CREATE TABLE {outbox_table} ("
            "id VARCHAR(36) PRIMARY KEY, "
            f"{domain}_id INTEGER NOT NULL, "
            "event_type VARCHAR(100) NOT NULL, payload_json TEXT NOT NULL, "
            "occurred_at DATETIME NOT NULL, published_at DATETIME, "
            "delivery_attempts INTEGER NOT NULL DEFAULT 0, last_error TEXT)"
        )
    monkeypatch.setenv(f"{domain.upper()}_DATABASE_URL", f"sqlite:///{database_path}")
    session_factory_for.cache_clear()
    try:
        initialize_domain_schema(domain)
        bind = session_factory_for(domain).kw["bind"]
        columns = {column["name"] for column in inspect(bind).get_columns(outbox_table)}
        assert {"correlation_id", "causation_id"} <= columns
        # Repeating startup must leave the schema usable.
        initialize_domain_schema(domain)
    finally:
        session_factory_for.cache_clear()
