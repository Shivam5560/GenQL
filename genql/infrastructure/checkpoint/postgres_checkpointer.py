"""Builds LangGraph's PostgresSaver over GenQL's own database.

Three things here are not what they look like, and all three were checked
against the installed package rather than assumed.

PostgresSaver takes a live connection, not a DSN: its signature is
`PostgresSaver(conn, pipe=None, serde=None)` where conn is a psycopg
Connection[DictRow] or a ConnectionPool of them. `from_conn_string` exists but
is a CONTEXT MANAGER, so a container Singleton built from it would hand back a
saver whose connection had already closed.

The pool must produce dict rows. `row_factory=dict_row` is not a preference —
the saver indexes its result rows by column name and raises with the default
tuple factory. `autocommit=True` matches what langgraph's own documentation
requires for the saver's transaction handling.

setup() is called here rather than from cli/main.py. The spec suggested a
startup hook "the same way the engine provider already runs migrations
lazily", but the engine provider runs no migrations, so there is no such
precedent; and a startup hook would open a database connection for `genql
--help`. This function backs a providers.Singleton, so setup() runs exactly
once, lazily, the first time a turn actually needs the graph. It is idempotent,
so re-running it after reset_singletons() is safe.

The tables it creates — checkpoints, checkpoint_blobs, checkpoint_writes,
checkpoint_migrations — are langgraph's to own and evolve across its releases,
which is why migration 0007 deliberately does not declare them.

`serde` is built explicitly rather than left as PostgresSaver's default
JsonPlusSerializer. langgraph's msgpack codec refuses, with a warning today
and a hard error in a future release, to deserialize a type it does not
recognise unless that type's module is named in `allowed_msgpack_modules`.
`AmbiguityAssessment` is the one custom Pydantic type this graph's state
carries into a checkpoint, so it is named here once, at the one place the
saver is constructed, rather than every call site risking the warning.
"""

from __future__ import annotations

from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from psycopg import Connection
from psycopg.rows import DictRow, dict_row
from psycopg_pool import ConnectionPool

from genql.domain.entities.ambiguity_assessment import AmbiguityAssessment


def build_checkpointer(dsn: str, max_size: int) -> PostgresSaver:
    # The annotation is load-bearing, not decoration: ConnectionPool takes its
    # type parameter from `connection_class`, which stays the default, so the
    # row factory passed through `kwargs` is invisible to the type checker and
    # the pool would otherwise infer as Connection[tuple[Any, ...]] — exactly
    # the shape PostgresSaver rejects at runtime.
    pool: ConnectionPool[Connection[DictRow]] = ConnectionPool(
        conninfo=dsn,
        # psycopg_pool defaults min_size to 4 and rejects a max_size below it,
        # so leaving min_size alone would make any max_size under 4 a
        # ValueError. One is also the right floor for a CLI turn: the pool
        # opens a single connection eagerly and grows to max_size only if
        # something concurrent actually needs it.
        min_size=1,
        max_size=max_size,
        kwargs={"autocommit": True, "row_factory": dict_row},
        open=True,
    )
    serde = JsonPlusSerializer(allowed_msgpack_modules=[AmbiguityAssessment])
    saver = PostgresSaver(pool, serde=serde)
    saver.setup()
    return saver
