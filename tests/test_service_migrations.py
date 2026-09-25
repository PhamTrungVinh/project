"""Service migration boundaries and adoption of existing local data."""

import sqlite3

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

from database import Base
from identity_service.models import User
from scripts.migrate_service import migrate
from service_migrations.common import SERVICE_TABLES, owned_metadata


@pytest.mark.parametrize("service", sorted(SERVICE_TABLES))
def test_fresh_service_migration_creates_only_owned_tables(tmp_path, service):
    url = f"sqlite:///{tmp_path / (service + '.db')}"
    migrate(service, url)
    migrate(service, url)
    with create_engine(url).connect() as connection:
        tables = set(inspect(connection).get_table_names())
        assert tables == set(owned_metadata(service).tables) | {"alembic_version"}


def test_migration_adopts_existing_service_database_without_changing_rows(tmp_path):
    path = tmp_path / "identity.db"
    url = f"sqlite:///{path}"
    engine = create_engine(url)
    Base.metadata.create_all(engine, tables=[User.__table__])
    with Session(engine) as session:
        session.add(User(email="existing@example.com", hashed_password="hash"))
        session.commit()
    engine.dispose()

    migrate("identity", url)
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT email FROM users").fetchone() == ("existing@example.com",)
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == ("identity_0001",)


def test_migration_rejects_database_shared_with_another_service(tmp_path):
    path = tmp_path / "shared.db"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE unrelated (id INTEGER PRIMARY KEY)")
    with pytest.raises(RuntimeError, match="another service"):
        migrate("ticket", f"sqlite:///{path}")
