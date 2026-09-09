"""The one container every unit test in this package builds.

It lives here rather than in a single test module because the wiring is now
asserted from two files: the discovery/graph surface in
test_composition_root.py, and Phase 7's providers in test_optimizer_container.py.
"""

from __future__ import annotations

import pytest

from genql.composition_root import Container


@pytest.fixture()
def container(monkeypatch: pytest.MonkeyPatch) -> Container:
    # Engines are constructed lazily by SQLAlchemy (no connection attempt at
    # create_engine() time), so a syntactically valid but unreachable DSN is
    # enough to build the container without touching a real database.
    monkeypatch.setenv("GENQL_WAREHOUSE_DSN", "postgresql+psycopg://x:x@localhost/x")
    monkeypatch.setenv("GENQL_SEMANTIC_DSN", "postgresql+psycopg://x:x@localhost/x")
    monkeypatch.setenv("GENQL_NEO4J_URI", "bolt://localhost:7687")
    monkeypatch.setenv("GENQL_NEO4J_USER", "neo4j")
    monkeypatch.setenv("GENQL_NEO4J_PASSWORD", "x")
    monkeypatch.setenv("GENQL_OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("GENQL_READONLY_DB_PASSWORD", "test-readonly-password")
    Container().reset_singletons()
    return Container()
