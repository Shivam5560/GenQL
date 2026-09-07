"""The lock's whole reason to exist is that a SECOND acquire blocks.

That cannot be asserted from one connection — pg_advisory_lock is re-entrant
within a session, so a same-session second acquire returns immediately and
would prove nothing. Each lock therefore opens its own connection, and the test
uses a real background thread to prove the second one genuinely waits.
"""

from __future__ import annotations

import threading
import time

import pytest
from sqlalchemy import Engine, text

from genql.domain.errors import ThreadLockError
from genql.infrastructure.db.psycopg_dsn import to_libpq_dsn
from genql.infrastructure.query.thread_lock_factory import PostgresThreadLockFactory


@pytest.fixture()
def dsn(paradedb_dsn: str, migrated_engine: Engine) -> str:
    return to_libpq_dsn(paradedb_dsn)


def test_a_lock_can_be_acquired_and_released(dsn: str) -> None:
    with PostgresThreadLockFactory(dsn).for_thread("t-solo"):
        pass


def test_the_same_thread_id_is_reusable_after_release(dsn: str) -> None:
    factory = PostgresThreadLockFactory(dsn)
    with factory.for_thread("t-reuse"):
        pass
    with factory.for_thread("t-reuse"):
        pass


def test_a_second_acquire_on_the_same_thread_id_waits_for_the_first(dsn: str) -> None:
    factory = PostgresThreadLockFactory(dsn)
    order: list[str] = []
    second_acquired = threading.Event()

    def second() -> None:
        with factory.for_thread("t-contended"):
            order.append("second")
            second_acquired.set()

    with factory.for_thread("t-contended"):
        worker = threading.Thread(target=second, daemon=True)
        worker.start()
        # Long enough that a non-blocking implementation would have appended
        # "second" before "first"; short enough to keep the suite quick.
        time.sleep(1.0)
        assert not second_acquired.is_set()
        order.append("first")

    worker.join(timeout=10)
    assert second_acquired.is_set()
    assert order == ["first", "second"]


def test_different_thread_ids_do_not_block_each_other(dsn: str) -> None:
    factory = PostgresThreadLockFactory(dsn)

    with factory.for_thread("t-a"), factory.for_thread("t-b"):
        pass


def test_the_lock_is_released_when_the_body_raises(dsn: str) -> None:
    factory = PostgresThreadLockFactory(dsn)

    with pytest.raises(RuntimeError), factory.for_thread("t-raises"):
        raise RuntimeError("boom")

    # If the first lock leaked, this would hang rather than return.
    with factory.for_thread("t-raises"):
        pass


def test_another_session_cannot_take_the_lock_until_it_is_released(
    dsn: str, migrated_engine: Engine
) -> None:
    """pg_try_advisory_lock is the non-blocking probe: False while held, True
    once released. Asserted from a separate SQLAlchemy connection, because a
    same-session probe would succeed re-entrantly and prove nothing."""
    probe = text("SELECT pg_try_advisory_lock(hashtext('t-cleanup'))")
    unprobe = text("SELECT pg_advisory_unlock(hashtext('t-cleanup'))")

    with (
        PostgresThreadLockFactory(dsn).for_thread("t-cleanup"),
        migrated_engine.connect() as conn,
    ):
        assert conn.execute(probe).scalar_one() is False

    with migrated_engine.connect() as conn:
        assert conn.execute(probe).scalar_one() is True
        conn.execute(unprobe)


def test_an_unreachable_database_is_a_typed_failure() -> None:
    factory = PostgresThreadLockFactory("postgresql://nobody@127.0.0.1:1/none")

    with pytest.raises(ThreadLockError), factory.for_thread("t-unreachable"):
        pass
