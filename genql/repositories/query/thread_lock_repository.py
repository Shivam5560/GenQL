"""One thread, one in-flight turn, enforced by a session-scoped Postgres
advisory lock.

This lives in repositories, not infrastructure, because it issues SQL — the
standing rule is that SQL appears only here. The spec's §4 places it in
infrastructure/db/; the factory that BUILDS it does, which is the same split
QueryExecutorFactoryImpl and ReadOnlyQueryExecutorRepository already use.

A dedicated psycopg connection, not the SQLAlchemy engine's pool:
pg_advisory_lock is session-scoped, so the lock lives exactly as long as the
connection that took it. Borrowing a pooled connection would release the lock
whenever the pool recycled it, and sharing the checkpointer's pool would
deadlock — the checkpointer needs a connection to write the very checkpoint the
lock is protecting.

The connection's lifetime IS the lock's lifetime, which is also the crash-safety
story: a process that dies holding the lock drops its connection, and Postgres
releases the lock itself. There is no stale-lock cleanup path to get wrong.
"""

from __future__ import annotations

from types import TracebackType

import psycopg

from genql.domain.errors import ThreadLockError

_ACQUIRE = "SELECT pg_advisory_lock(hashtext(%s))"
_RELEASE = "SELECT pg_advisory_unlock(hashtext(%s))"


class PostgresThreadLock:
    def __init__(self, dsn: str, thread_id: str) -> None:
        self._dsn = dsn
        self._thread_id = thread_id
        self._conn: psycopg.Connection[tuple[object, ...]] | None = None

    def __enter__(self) -> None:
        try:
            conn = psycopg.connect(self._dsn, autocommit=True)
        except psycopg.Error as exc:
            raise ThreadLockError(
                f"could not connect to take the lock for thread {self._thread_id!r}: {exc}"
            ) from exc
        try:
            conn.execute(_ACQUIRE, (self._thread_id,))
        except psycopg.Error as exc:
            conn.close()
            raise ThreadLockError(f"could not lock thread {self._thread_id!r}: {exc}") from exc
        self._conn = conn

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        conn, self._conn = self._conn, None
        if conn is None:
            return
        try:
            conn.execute(_RELEASE, (self._thread_id,))
        except psycopg.Error:
            # Closing the connection releases the lock regardless, so a failed
            # explicit unlock is not worth masking the body's own exception.
            pass
        finally:
            conn.close()
