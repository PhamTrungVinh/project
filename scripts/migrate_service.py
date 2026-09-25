"""Upgrade one owned service database without touching other service stores."""

import argparse

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from service_migrations.common import ROOT, SERVICE_TABLES, assert_owned_schema, database_url, owned_metadata


def migrate(service: str, url: str | None = None) -> None:
    if service not in SERVICE_TABLES:
        raise ValueError(f"Unknown service: {service}")
    url = url or database_url(service)
    configuration = Config()
    configuration.set_main_option("script_location", str(ROOT / service))
    configuration.attributes["database_url"] = url
    engine = create_engine(url, pool_pre_ping=True)
    with engine.connect() as connection:
        tables = set(inspect(connection).get_table_names())
        owned = set(owned_metadata(service).tables)
        unexpected = tables - owned - {"alembic_version"}
        if unexpected:
            raise RuntimeError(
                f"{service} database contains tables owned by another service: {sorted(unexpected)}"
            )
        adopt_existing = bool(owned & tables) and "alembic_version" not in tables
        if adopt_existing:
            assert_owned_schema(connection, service)
    engine.dispose()
    if adopt_existing:
        # A database created by the old local bootstrap already has the
        # target schema. Record its starting revision without rewriting rows.
        command.stamp(configuration, "head")
    else:
        command.upgrade(configuration, "head")
    verify_engine = create_engine(url)
    with verify_engine.connect() as connection:
        assert_owned_schema(connection, service)
    verify_engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("service", choices=sorted(SERVICE_TABLES))
    parser.add_argument("--database-url", help="Override this service's database URL")
    args = parser.parse_args()
    migrate(args.service, args.database_url)


if __name__ == "__main__":
    main()
