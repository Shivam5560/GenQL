"""Binds the process-wide DSN to a per-turn thread_id.

Infrastructure rather than a repository because it opens no connection and runs
no statement — it only decides which lock object to construct, exactly as
QueryExecutorFactoryImpl decides which executor to construct.
"""

from __future__ import annotations

from genql.domain.ports.thread_lock import ThreadLock
from genql.repositories.query.thread_lock_repository import PostgresThreadLock


class PostgresThreadLockFactory:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    def for_thread(self, thread_id: str) -> ThreadLock:
        return PostgresThreadLock(self._dsn, thread_id)
