"""Every `:name` in a `text()` statement must become a real bind parameter.

`:domain_id::bigint` does not: SQLAlchemy stops at the first `:`, treats the
rest as a PostgreSQL cast it does not own, and emits the marker verbatim, so
Postgres receives literal `:domain_id::bigint` and rejects the statement. The
working form is `CAST(:domain_id AS bigint)`. These statements are only ever
exercised against a live database, so this compile-time check is the cheapest
place to catch the regression.
"""

from __future__ import annotations

import re

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql.elements import TextClause

from genql.repositories.semantic.ambiguity_example_repository import (
    _SEARCH as AMBIGUITY_SEARCH,  # noqa: PLC2701 - the statement under test
)
from genql.repositories.semantic.bm25_retriever_repository import (
    _SEARCH as BM25_SEARCH,  # noqa: PLC2701 - the statement under test
)
from genql.repositories.semantic.dense_retriever_repository import (
    _SEARCH as DENSE_SEARCH,  # noqa: PLC2701 - the statement under test
)
from genql.repositories.semantic.hybrid_rrf_retriever_repository import (
    _SEARCH as HYBRID_SEARCH,  # noqa: PLC2701 - the statement under test
)

STATEMENTS = {
    "ambiguity_example": AMBIGUITY_SEARCH,
    "bm25": BM25_SEARCH,
    "dense": DENSE_SEARCH,
    "hybrid_rrf": HYBRID_SEARCH,
}
_UNBOUND_MARKER = re.compile(r":[A-Za-z_]\w*")


@pytest.mark.parametrize("name", sorted(STATEMENTS))
def test_no_parameter_marker_survives_compilation(name: str) -> None:
    compiled = str(STATEMENTS[name].compile(dialect=postgresql.dialect()))

    assert _UNBOUND_MARKER.search(compiled) is None, (
        f"{name} leaks an uncompiled parameter marker: {compiled}"
    )


@pytest.mark.parametrize("name", sorted(STATEMENTS))
def test_domain_id_is_bound_exactly_once(name: str) -> None:
    statement: TextClause = STATEMENTS[name]

    assert "domain_id" in statement.compile(dialect=postgresql.dialect()).params


def test_a_scoped_ambiguity_search_still_returns_unscoped_examples() -> None:
    """0008's ON DELETE SET NULL keeps an orphaned example as a valid general
    exemplar, so the scoped predicate must not filter `domain_id IS NULL` out."""
    assert "OR domain_id IS NULL" in str(AMBIGUITY_SEARCH)
