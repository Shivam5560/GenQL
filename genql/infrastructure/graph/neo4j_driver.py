"""Neo4j driver construction.

The driver does not connect until a session runs a query, so building one is
as safe to do eagerly at the composition root as `create_engine_from_dsn` is
for Postgres.
"""

from __future__ import annotations

from neo4j import Driver, GraphDatabase


def create_neo4j_driver(uri: str, user: str, password: str) -> Driver:
    return GraphDatabase.driver(uri, auth=(user, password))
