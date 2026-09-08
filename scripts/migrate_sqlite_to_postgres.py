"""Copy app data from SQLite to a migrated PostgreSQL database and validate it.

Run Alembic on the target first, then execute:
uv run python scripts/migrate_sqlite_to_postgres.py --source sqlite:///./app.db --target postgresql+psycopg://...
"""
import argparse
from collections.abc import Iterable

from sqlalchemy import MetaData, create_engine, func, inspect, select, text

TABLES = ("users", "tickets", "bookings", "conversations", "semantic_memory", "episodic_memory")
OWNER_TABLES = ("tickets", "bookings", "conversations", "semantic_memory", "episodic_memory")


def _count(connection, table) -> int:
    return connection.execute(select(func.count()).select_from(table)).scalar_one()


def validate(source, target) -> None:
    source_metadata = MetaData()
    target_metadata = MetaData()
    source_metadata.reflect(bind=source, only=TABLES)
    target_metadata.reflect(bind=target, only=TABLES)
    for name in TABLES:
        source_count = _count(source, source_metadata.tables[name])
        target_count = _count(target, target_metadata.tables[name])
        if source_count != target_count:
            raise RuntimeError(f"Row-count mismatch for {name}: source={source_count}, target={target_count}")

    users = target_metadata.tables["users"]
    invalid_passwords = target.execute(select(func.count()).select_from(users).where((users.c.hashed_password.is_(None)) | (func.length(users.c.hashed_password) == 0))).scalar_one()
    if invalid_passwords:
        raise RuntimeError(f"Invalid password hashes: {invalid_passwords}")
    for name in OWNER_TABLES:
        table = target_metadata.tables[name]
        orphan_count = target.execute(select(func.count()).select_from(table.outerjoin(users, table.c.owner_id == users.c.id)).where(users.c.id.is_(None))).scalar_one()
        if orphan_count:
            raise RuntimeError(f"Foreign-key/ownership validation failed for {name}: {orphan_count} orphan rows")
        missing_timestamps = target.execute(select(func.count()).select_from(table).where(table.c.created_at.is_(None))).scalar_one()
        if missing_timestamps:
            raise RuntimeError(f"Timestamp validation failed for {name}: {missing_timestamps} rows")
    conversations = target_metadata.tables["conversations"]
    duplicate_threads = target.execute(select(func.count()).select_from(select(conversations.c.thread_id).group_by(conversations.c.thread_id).having(func.count() > 1).subquery())).scalar_one()
    if duplicate_threads:
        raise RuntimeError(f"Thread ownership validation failed: {duplicate_threads} duplicate thread IDs")


def copy_rows(source, target) -> None:
    source_metadata = MetaData()
    target_metadata = MetaData()
    source_metadata.reflect(bind=source, only=TABLES)
    target_metadata.reflect(bind=target, only=TABLES)
    for name in TABLES:
        source_table = source_metadata.tables[name]
        target_table = target_metadata.tables[name]
        if _count(target, target_table):
            raise RuntimeError(f"Target table {name} is not empty; refusing to merge data")
        rows = [dict(row) for row in source.execute(select(source_table)).mappings()]
        if rows:
            target.execute(target_table.insert(), rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    if not args.source.startswith("sqlite") or not args.target.startswith("postgresql"):
        raise SystemExit("Source must be SQLite and target must be PostgreSQL")
    source_engine = create_engine(args.source)
    target_engine = create_engine(args.target)
    if not inspect(target_engine).has_table("alembic_version"):
        raise SystemExit("Target must be initialized with `alembic upgrade head` first")
    with source_engine.connect() as source, target_engine.begin() as target:
        if not args.verify_only:
            copy_rows(source, target)
        validate(source, target)
    print("Migration validation passed")


if __name__ == "__main__":
    main()
