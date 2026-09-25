"""Serialize chat turns sharing a checkpoint thread across requests and replicas."""

import hashlib
from contextlib import contextmanager
from threading import Lock

from database import engine


_local_locks = [Lock() for _ in range(256)]


def _lock_key(owner_id: int, thread_id: str) -> int:
    raw = f"{owner_id}:{thread_id}".encode("utf-8")
    return int.from_bytes(hashlib.blake2b(raw, digest_size=8).digest(), "big", signed=True)


@contextmanager
def thread_turn_lock(owner_id: int, thread_id: str):
    key = _lock_key(owner_id, thread_id)
    if engine.dialect.name == "postgresql":
        from sqlalchemy import text

        with engine.connect() as connection, connection.begin():
            connection.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})
            yield
    else:
        with _local_locks[key % len(_local_locks)]:
            yield
