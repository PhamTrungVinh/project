"""Copy an existing monolith SQLite database into locally owned service stores.

Destinations must be empty. The source is never changed.
"""

import argparse
import sqlite3
from pathlib import Path

from sqlalchemy import create_engine

from database import Base
import models  # noqa: F401 - register mapped tables


TABLES = {
    "identity_service.db": ("users",),
    "chat_service.db": ("conversations", "pending_actions"),
    "ticket_service.db": ("tickets", "ticket_audit", "ticket_outbox", "idempotency_records"),
    "booking_service.db": ("bookings", "booking_audit", "booking_outbox", "idempotency_records"),
    "memory_service.db": ("semantic_memory", "episodic_memory"),
}


def _tables(connection: sqlite3.Connection) -> set[str]:
    return {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def split(source: Path, destination: Path, checkpoints: Path | None = None) -> dict[str, int]:
    if not source.is_file():
        raise FileNotFoundError(source)
    destination.mkdir(parents=True, exist_ok=True)
    destinations = {name: destination / name for name in TABLES}
    for name, path in destinations.items():
        if path.resolve() == source.resolve():
            raise ValueError(f"Destination overlaps source: {name}")
    checkpoint_target = destination / "chat_checkpoints.db"
    if checkpoints and checkpoints.is_file() and checkpoints.resolve() == checkpoint_target.resolve():
        raise ValueError("Checkpoint destination overlaps source")
    if checkpoints and checkpoints.is_file() and checkpoint_target.exists():
        raise ValueError(f"Checkpoint destination already exists: {checkpoint_target}")

    # Check every destination before writing any rows.
    for name, path in destinations.items():
        if path.exists():
            with sqlite3.connect(path) as db:
                existing = _tables(db)
                for table in TABLES[name]:
                    if table in existing and db.execute(f'SELECT 1 FROM "{table}" LIMIT 1').fetchone():
                        raise ValueError(f"Destination table is not empty: {path}:{table}")

    counts: dict[str, int] = {}
    with sqlite3.connect(f"file:{source.resolve()}?mode=ro", uri=True) as old:
        source_tables = _tables(old)
        for name, path in destinations.items():
            engine = create_engine(f"sqlite:///{path}")
            Base.metadata.create_all(engine, tables=[Base.metadata.tables[table] for table in TABLES[name]])
            engine.dispose()
            with sqlite3.connect(path) as new:
                for table in TABLES[name]:
                    if table not in source_tables:
                        continue
                    old_columns = [row[1] for row in old.execute(f'PRAGMA table_info("{table}")')]
                    new_columns = {row[1] for row in new.execute(f'PRAGMA table_info("{table}")')}
                    columns = [column for column in old_columns if column in new_columns]
                    if not columns:
                        continue
                    quoted = ", ".join(f'"{column}"' for column in columns)
                    query = f'SELECT {quoted} FROM "{table}"'
                    if table == "idempotency_records":
                        prefix = "ticket." if name.startswith("ticket") else "booking."
                        query += " WHERE operation LIKE ?"
                        rows = old.execute(query, (prefix + "%",)).fetchall()
                    else:
                        rows = old.execute(query).fetchall()
                    placeholders = ", ".join("?" for _ in columns)
                    new.executemany(f'INSERT INTO "{table}" ({quoted}) VALUES ({placeholders})', rows)
                    counts[f"{name}:{table}"] = len(rows)
                new.commit()

    if checkpoints and checkpoints.is_file():
        with sqlite3.connect(f"file:{checkpoints.resolve()}?mode=ro", uri=True) as old, sqlite3.connect(checkpoint_target) as new:
            old.backup(new)
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("app.db"))
    parser.add_argument("--destination", type=Path, default=Path("."))
    parser.add_argument("--checkpoints", type=Path, default=Path("checkpoints.db"))
    args = parser.parse_args()
    for table, count in split(args.source, args.destination, args.checkpoints).items():
        print(f"{table}: {count}")


if __name__ == "__main__":
    main()
